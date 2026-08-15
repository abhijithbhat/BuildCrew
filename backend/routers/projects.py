import json
import os
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from core.database import get_supabase_client
from core.dependencies import get_current_user
from schemas.project import (
    ProjectCreate,
    ProjectInviteResponse,
    ProjectJoinRequest,
    ProjectJoinResponse,
    ProjectResponse,
    ProjectUpdate,
)
from schemas.project_member import ProjectMemberResponse


router = APIRouter(prefix="/projects", tags=["Projects"])

INVITES_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", ".invites_cache.json"
)


def _load_invites() -> dict:
    if os.path.exists(INVITES_CACHE_FILE):
        try:
            with open(INVITES_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_invites(invites: dict) -> None:
    try:
        with open(INVITES_CACHE_FILE, "w") as f:
            json.dump(invites, f, indent=2)
    except Exception:
        pass


# In-memory storage with file cache for server reloads
DEV_PROJECTS_DB: dict[str, dict] = {}
DEV_PROJECT_MEMBERS_DB: list[dict] = []
DEV_PROJECT_INVITES_DB: dict[str, dict] = _load_invites()



def _is_dev_fallback_error(err_msg: str) -> bool:
    return any(
        s in err_msg
        for s in (
            "nodename nor servname provided",
            "gai_error",
            "Name or service not known",
            "SUPABASE_URL",
            "environment variables",
            "Failed to connect",
            "Client disconnected",
        )
    )


def generate_invite_code(prefix: str = "BC") -> str:

    """Generate a 6-character clean alphanumeric invite code like BC-A7K29X."""
    alphabet = (
        string.ascii_uppercase
        + string.digits.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    )
    random_part = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"{prefix}-{random_part}"



def _get_user_id(current_user: Any) -> str:
    """Helper to extract user id from current_user object or dict."""
    user_id = getattr(current_user, "id", None)
    if not user_id and isinstance(current_user, dict):
        user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID could not be identified from token",
        )
    return str(user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_project(
    payload: ProjectCreate,
    current_user: Any = Depends(get_current_user),
):
    """Create a new project and automatically add the creator as an owner member."""
    user_id = _get_user_id(current_user)

    if not payload.name or not payload.name.strip():
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Project name cannot be empty.",
        )



    clean_name = payload.name.strip()
    clean_description = (
        payload.description.strip() if payload.description else None
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    project_id = str(uuid.uuid4())

    try:
        supabase = get_supabase_client()
        project_insert_data = {
            "name": clean_name,
            "description": clean_description,
            "created_by": user_id,
        }
        project_res = (
            supabase.table("projects")
            .insert(project_insert_data)
            .execute()
        )

        if not project_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database failed to create project record.",
            )

        created_project = project_res.data[0]
        actual_project_id = created_project.get("id", project_id)

        # Automatically add creator as owner in project_members
        member_insert_data = {
            "project_id": actual_project_id,
            "user_id": user_id,
            "role": "owner",
        }
        member_res = (
            supabase.table("project_members")
            .insert(member_insert_data)
            .execute()
        )

        created_member = (
            member_res.data[0] if member_res.data else member_insert_data
        )

        return {
            "message": "Project created successfully",
            "project": created_project,
            "member": created_member,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode fallback
            dev_project = {
                "id": project_id,
                "name": clean_name,
                "description": clean_description,
                "created_by": user_id,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            DEV_PROJECTS_DB[project_id] = dev_project

            dev_member = {
                "project_id": project_id,
                "user_id": user_id,
                "role": "owner",
                "joined_at": now_iso,
            }
            DEV_PROJECT_MEMBERS_DB.append(dev_member)

            return {
                "message": "Project created successfully (Local Dev Mode)",
                "project": dev_project,
                "member": dev_member,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create project: {err_msg}",
        )


@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK, include_in_schema=False)
async def list_projects(current_user: Any = Depends(get_current_user)):
    """List all projects the authenticated current user belongs to."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()
        # Query project_members for this user with joined project data
        res = (
            supabase.table("project_members")
            .select("role, joined_at, projects(*)")
            .eq("user_id", user_id)
            .execute()
        )

        projects_list = []
        seen_project_ids = set()

        if res.data:
            for item in res.data:
                proj = item.get("projects")
                if proj and isinstance(proj, dict):
                    proj_id = proj.get("id")
                    if proj_id and proj_id not in seen_project_ids:
                        seen_project_ids.add(proj_id)
                        project_data = dict(proj)
                        project_data["role"] = item.get("role", "member")
                        project_data["my_role"] = item.get("role", "member")
                        project_data["joined_at"] = item.get("joined_at")
                        projects_list.append(project_data)

        # Fallback check for projects created by this user that might have missed membership
        created_res = (
            supabase.table("projects")
            .select("*")
            .eq("created_by", user_id)
            .execute()
        )
        if created_res.data:
            for proj in created_res.data:
                proj_id = proj.get("id")
                if proj_id and proj_id not in seen_project_ids:
                    seen_project_ids.add(proj_id)
                    project_data = dict(proj)
                    project_data["role"] = "owner"
                    project_data["my_role"] = "owner"
                    projects_list.append(project_data)

        return {
            "projects": projects_list,
        }
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode fallback: Filter in-memory projects by user membership
            member_project_roles = {
                m["project_id"]: m.get("role", "member")
                for m in DEV_PROJECT_MEMBERS_DB
                if m.get("user_id") == user_id
            }

            user_projects = []
            for p_id, p_data in DEV_PROJECTS_DB.items():
                if p_id in member_project_roles or p_data.get("created_by") == user_id:
                    p_copy = dict(p_data)
                    role = member_project_roles.get(p_id, "owner")
                    p_copy["role"] = role
                    p_copy["my_role"] = role
                    user_projects.append(p_copy)

            return {
                "projects": user_projects,
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch projects: {err_msg}",
        )



@router.get("/{project_id}", status_code=status.HTTP_200_OK)
async def get_project_details(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Retrieve details for a specific project including members."""
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("projects")
            .select("*, project_members(*, profiles(*))")
            .eq("id", project_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        return {
            "project": res.data,
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            if project_id in DEV_PROJECTS_DB:
                members = [
                    m
                    for m in DEV_PROJECT_MEMBERS_DB
                    if m.get("project_id") == project_id
                ]
                proj = dict(DEV_PROJECTS_DB[project_id])
                proj["project_members"] = members
                return {"project": proj}
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch project details: {err_msg}",
        )


@router.post("/{project_id}/invite", response_model=ProjectInviteResponse, status_code=status.HTTP_200_OK)
@router.get("/{project_id}/invite", response_model=ProjectInviteResponse, status_code=status.HTTP_200_OK)
async def generate_project_invite(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Generate or retrieve a shareable invite code for the specified project. Requires membership."""
    user_id = _get_user_id(current_user)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    # Check if a valid, unexpired invite already exists for this project in local cache
    existing_invite = None
    for code, info in list(DEV_PROJECT_INVITES_DB.items()):
        if info.get("project_id") == project_id:
            exp_str = info.get("expires_at")
            if exp_str:
                try:
                    if datetime.fromisoformat(exp_str) > now:
                        existing_invite = info
                        break
                except Exception:
                    pass
            else:
                existing_invite = info
                break

    if existing_invite:
        invite_code = existing_invite["invite_code"]
        if existing_invite.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(existing_invite["expires_at"])
            except Exception:
                pass
    else:
        invite_code = generate_invite_code()


    try:
        supabase = get_supabase_client()

        # 1. Fetch project
        proj_res = (
            supabase.table("projects")
            .select("*")
            .eq("id", project_id)
            .single()
            .execute()
        )
        if not proj_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        project_data = proj_res.data

        # 2. Check if current user is owner or member of this project
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        is_member = bool(member_res.data) or (project_data.get("created_by") == user_id)

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to generate an invite code.",
            )

        invite_data = {
            "invite_code": invite_code,
            "project_id": project_id,
            "project_name": project_data.get("name"),
            "created_by": user_id,
            "invite_url": f"https://buildcrew.app/join/{invite_code}",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "message": "Invite code generated successfully",
        }
        DEV_PROJECT_INVITES_DB[invite_code] = invite_data
        _save_invites(DEV_PROJECT_INVITES_DB)

        return invite_data

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode fallback
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )

            project_data = DEV_PROJECTS_DB[project_id]
            is_member = (project_data.get("created_by") == user_id) or any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )

            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to generate an invite code.",
                )

            invite_data = {
                "invite_code": invite_code,
                "project_id": project_id,
                "project_name": project_data.get("name"),
                "created_by": user_id,
                "invite_url": f"https://buildcrew.app/join/{invite_code}",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "message": "Invite code generated successfully (Local Dev Mode)",
            }
            DEV_PROJECT_INVITES_DB[invite_code] = invite_data
            _save_invites(DEV_PROJECT_INVITES_DB)
            return invite_data

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate invite code: {err_msg}",
        )


@router.post("/join", response_model=ProjectJoinResponse, status_code=status.HTTP_200_OK)
async def join_project_by_invite(
    payload: ProjectJoinRequest,
    current_user: Any = Depends(get_current_user),
):
    """Join a project using a valid shareable invite code."""
    user_id = _get_user_id(current_user)

    if not payload.invite_code or not payload.invite_code.strip():
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Invite code cannot be empty.",
        )

    clean_code = payload.invite_code.strip().upper()

    # Refresh from persistent cache if not in memory
    if clean_code not in DEV_PROJECT_INVITES_DB:
        DEV_PROJECT_INVITES_DB.update(_load_invites())

    invite_info = DEV_PROJECT_INVITES_DB.get(clean_code)
    if not invite_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invite code.",
        )


    # Check expiration
    expires_at_str = invite_info.get("expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invite code has expired.",
                )
        except (ValueError, TypeError):
            pass

    project_id = invite_info.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invite code: project not specified.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        supabase = get_supabase_client()

        # Check project existence in Supabase
        proj_res = (
            supabase.table("projects")
            .select("*")
            .eq("id", project_id)
            .single()
            .execute()
        )
        if not proj_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The project associated with this invite code was not found.",
            )

        project_data = proj_res.data

        # Check if user is already a member
        member_check = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if member_check.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already a member of this project.",
            )

        # Add user to project_members
        member_data = {
            "project_id": project_id,
            "user_id": user_id,
            "role": "member",
        }
        member_res = (
            supabase.table("project_members")
            .insert(member_data)
            .execute()
        )
        created_member = member_res.data[0] if member_res.data else member_data

        return {
            "message": "Successfully joined project",
            "project": project_data,
            "member": created_member,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode fallback
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="The project associated with this invite code was not found.",
                )

            project_data = DEV_PROJECTS_DB[project_id]

            already_member = any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            ) or (project_data.get("created_by") == user_id)

            if already_member:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You are already a member of this project.",
                )

            dev_member = {
                "project_id": project_id,
                "user_id": user_id,
                "role": "member",
                "joined_at": now_iso,
            }
            DEV_PROJECT_MEMBERS_DB.append(dev_member)

            return {
                "message": "Successfully joined project (Local Dev Mode)",
                "project": project_data,
                "member": dev_member,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to join project: {err_msg}",
        )


