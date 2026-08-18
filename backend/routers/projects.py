import json
import os
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from schemas.role_agreement import (
    RoleAgreementResponse,
    RoleAgreementsListResponse,
    RoleDeclarationResponse,
    RoleDeclareRequest,
)



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
DEV_ROLE_AGREEMENTS_DB: list[dict] = []



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


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Permanently delete / dismantle a project (Team Lead / Creator only)."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()
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
                detail="Project not found",
            )

        project_data = proj_res.data
        if project_data.get("created_by") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Team Lead (Project Creator) can dismantle this project.",
            )

        # Delete cascades across members, roles, installations in Supabase
        supabase.table("projects").delete().eq("id", project_id).execute()

        # Clean local cache/memory state
        DEV_PROJECTS_DB.pop(project_id, None)
        DEV_PROJECT_MEMBERS_DB[:] = [
            m for m in DEV_PROJECT_MEMBERS_DB if m.get("project_id") != project_id
        ]
        DEV_ROLE_AGREEMENTS_DB[:] = [
            r for r in DEV_ROLE_AGREEMENTS_DB if r.get("project_id") != project_id
        ]
        for c, inf in list(DEV_PROJECT_INVITES_DB.items()):
            if inf.get("project_id") == project_id:
                DEV_PROJECT_INVITES_DB.pop(c, None)
        _save_invites(DEV_PROJECT_INVITES_DB)

        return {
            "message": "Project dismantled successfully",
            "project_id": project_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found",
                )

            project_data = DEV_PROJECTS_DB[project_id]
            if project_data.get("created_by") != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Team Lead (Project Creator) can dismantle this project.",
                )

            DEV_PROJECTS_DB.pop(project_id, None)
            DEV_PROJECT_MEMBERS_DB[:] = [
                m for m in DEV_PROJECT_MEMBERS_DB if m.get("project_id") != project_id
            ]
            DEV_ROLE_AGREEMENTS_DB[:] = [
                r for r in DEV_ROLE_AGREEMENTS_DB if r.get("project_id") != project_id
            ]
            for c, inf in list(DEV_PROJECT_INVITES_DB.items()):
                if inf.get("project_id") == project_id:
                    DEV_PROJECT_INVITES_DB.pop(c, None)
            _save_invites(DEV_PROJECT_INVITES_DB)

            return {
                "message": "Project dismantled successfully (Local Dev Mode)",
                "project_id": project_id,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete project: {err_msg}",
        )


@router.post("/{project_id}/leave", status_code=status.HTTP_200_OK)
@router.delete("/{project_id}/leave", status_code=status.HTTP_200_OK)
async def leave_project(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Leave a project (Teammate only). Team Leads must dismantle the project instead."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()
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
                detail="Project not found",
            )

        project_data = proj_res.data
        if project_data.get("created_by") == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The Team Lead cannot leave the project. Please dismantle the project to close it.",
            )

        # Check membership
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not member_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not a member of this project.",
            )

        # Delete membership and declared role
        supabase.table("project_members").delete().eq("project_id", project_id).eq("user_id", user_id).execute()
        supabase.table("role_agreements").delete().eq("project_id", project_id).eq("user_id", user_id).execute()

        # Clean local cache/memory
        DEV_PROJECT_MEMBERS_DB[:] = [
            m for m in DEV_PROJECT_MEMBERS_DB
            if not (m.get("project_id") == project_id and m.get("user_id") == user_id)
        ]
        DEV_ROLE_AGREEMENTS_DB[:] = [
            r for r in DEV_ROLE_AGREEMENTS_DB
            if not (r.get("project_id") == project_id and r.get("user_id") == user_id)
        ]

        return {
            "message": "Successfully left the project",
            "project_id": project_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found",
                )

            project_data = DEV_PROJECTS_DB[project_id]
            if project_data.get("created_by") == user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The Team Lead cannot leave the project. Please dismantle the project to close it.",
                )

            is_member = any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="You are not a member of this project.",
                )

            DEV_PROJECT_MEMBERS_DB[:] = [
                m for m in DEV_PROJECT_MEMBERS_DB
                if not (m.get("project_id") == project_id and m.get("user_id") == user_id)
            ]
            DEV_ROLE_AGREEMENTS_DB[:] = [
                r for r in DEV_ROLE_AGREEMENTS_DB
                if not (r.get("project_id") == project_id and r.get("user_id") == user_id)
            ]

            return {
                "message": "Successfully left the project (Local Dev Mode)",
                "project_id": project_id,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to leave project: {err_msg}",
        )


@router.delete("/{project_id}/members/{member_user_id}", status_code=status.HTTP_200_OK)
async def remove_project_member(
    project_id: str,
    member_user_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Remove a teammate from a project (Team Lead only)."""
    user_id = _get_user_id(current_user)

    if member_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove yourself as Team Lead. Use dismantle project instead.",
        )

    try:
        supabase = get_supabase_client()
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
                detail="Project not found",
            )

        project_data = proj_res.data
        if project_data.get("created_by") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Team Lead can remove teammates.",
            )

        # Delete membership and declared role for the target member
        supabase.table("project_members").delete().eq("project_id", project_id).eq("user_id", member_user_id).execute()
        supabase.table("role_agreements").delete().eq("project_id", project_id).eq("user_id", member_user_id).execute()

        # Clean local cache/memory
        DEV_PROJECT_MEMBERS_DB[:] = [
            m for m in DEV_PROJECT_MEMBERS_DB
            if not (m.get("project_id") == project_id and m.get("user_id") == member_user_id)
        ]
        DEV_ROLE_AGREEMENTS_DB[:] = [
            r for r in DEV_ROLE_AGREEMENTS_DB
            if not (r.get("project_id") == project_id and r.get("user_id") == member_user_id)
        ]

        return {
            "message": "Member removed successfully",
            "project_id": project_id,
            "user_id": member_user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found",
                )

            project_data = DEV_PROJECTS_DB[project_id]
            if project_data.get("created_by") != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Team Lead can remove teammates.",
                )

            DEV_PROJECT_MEMBERS_DB[:] = [
                m for m in DEV_PROJECT_MEMBERS_DB
                if not (m.get("project_id") == project_id and m.get("user_id") == member_user_id)
            ]
            DEV_ROLE_AGREEMENTS_DB[:] = [
                r for r in DEV_ROLE_AGREEMENTS_DB
                if not (r.get("project_id") == project_id and r.get("user_id") == member_user_id)
            ]

            return {
                "message": "Member removed successfully (Local Dev Mode)",
                "project_id": project_id,
                "user_id": member_user_id,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to remove member: {err_msg}",
        )



@router.post("/{project_id}/invite", response_model=ProjectInviteResponse, status_code=status.HTTP_200_OK)
@router.get("/{project_id}/invite", response_model=ProjectInviteResponse, status_code=status.HTTP_200_OK)
async def generate_project_invite(
    project_id: str,
    regenerate: bool = Query(False),
    current_user: Any = Depends(get_current_user),
):
    """Get the permanent shareable invite code for a project, or regenerate a new one (Team Lead only)."""
    user_id = _get_user_id(current_user)
    now = datetime.now(timezone.utc)
    # Permanent invite code with a 10-year horizon
    expires_at = now + timedelta(days=365 * 10)

    # Check if a permanent invite code already exists for this project in local cache
    existing_invite = None
    if not regenerate:
        for code, info in list(DEV_PROJECT_INVITES_DB.items()):
            if info.get("project_id") == project_id:
                existing_invite = info
                break

    if existing_invite:
        invite_code = existing_invite["invite_code"]
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
        is_lead = (project_data.get("created_by") == user_id)

        # 2. Check membership
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        is_member = bool(member_res.data) or is_lead

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to view or generate invite codes.",
            )

        if regenerate and not is_lead:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the Team Lead (Project Creator) can regenerate the invite code.",
            )

        # If regenerating, clean out previous codes for this project
        if regenerate:
            for old_code, old_info in list(DEV_PROJECT_INVITES_DB.items()):
                if old_info.get("project_id") == project_id:
                    DEV_PROJECT_INVITES_DB.pop(old_code, None)

        invite_data = {
            "invite_code": invite_code,
            "project_id": project_id,
            "project_name": project_data.get("name"),
            "created_by": user_id,
            "invite_url": f"https://buildcrew.app/join/{invite_code}",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "message": "New invite code generated successfully" if regenerate else "Permanent invite code retrieved successfully",
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
            is_lead = (project_data.get("created_by") == user_id)
            is_member = is_lead or any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )

            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to view or generate invite codes.",
                )

            if regenerate and not is_lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Team Lead (Project Creator) can regenerate the invite code.",
                )

            if regenerate:
                for old_code, old_info in list(DEV_PROJECT_INVITES_DB.items()):
                    if old_info.get("project_id") == project_id:
                        DEV_PROJECT_INVITES_DB.pop(old_code, None)

            invite_data = {
                "invite_code": invite_code,
                "project_id": project_id,
                "project_name": project_data.get("name"),
                "created_by": user_id,
                "invite_url": f"https://buildcrew.app/join/{invite_code}",
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "message": "New invite code generated successfully (Local Dev Mode)" if regenerate else "Permanent invite code retrieved successfully (Local Dev Mode)",
            }
            DEV_PROJECT_INVITES_DB[invite_code] = invite_data
            _save_invites(DEV_PROJECT_INVITES_DB)
            return invite_data

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate invite code: {err_msg}",
        )


@router.post("/{project_id}/invite/regenerate", response_model=ProjectInviteResponse, status_code=status.HTTP_200_OK)
async def regenerate_project_invite_endpoint(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Regenerate a new invite code for a project (Team Lead only). Revokes previous invite codes."""
    return await generate_project_invite(
        project_id=project_id,
        regenerate=True,
        current_user=current_user,
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


@router.post(
    "/{project_id}/role",
    response_model=RoleDeclarationResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{project_id}/role/",
    response_model=RoleDeclarationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def declare_or_update_project_role(
    project_id: str,
    payload: RoleDeclareRequest,
    current_user: Any = Depends(get_current_user),
):
    """Declare or update your role and responsibilities on a project."""
    user_id = _get_user_id(current_user)

    role_name = (payload.declared_role or payload.role or "").strip()
    if not role_name:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Declared role cannot be empty.",
        )

    clean_responsibilities = (
        payload.responsibilities.strip()
        if payload.responsibilities and payload.responsibilities.strip()
        else None
    )
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    deadline_val = payload.deadline.isoformat() if payload.deadline else None

    try:
        supabase = get_supabase_client()

        # 1. Fetch project to ensure it exists
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

        # 2. Verify membership (must be member or owner)
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
                detail="You must be a member of this project to declare or update a role.",
            )

        # 3. Check for existing role agreement
        existing_res = (
            supabase.table("role_agreements")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )

        if existing_res.data and len(existing_res.data) > 0:
            existing_id = existing_res.data[0]["id"]
            update_data = {
                "declared_role": role_name,
                "responsibilities": clean_responsibilities,
                "deadline": deadline_val,
                "updated_at": now_iso,
            }
            update_res = (
                supabase.table("role_agreements")
                .update(update_data)
                .eq("id", existing_id)
                .execute()
            )
            saved_role = (
                update_res.data[0]
                if update_res.data
                else {**existing_res.data[0], **update_data}
            )
            msg = "Role agreement updated successfully"
        else:
            new_id = str(uuid.uuid4())
            insert_data = {
                "id": new_id,
                "project_id": project_id,
                "user_id": user_id,
                "declared_role": role_name,
                "responsibilities": clean_responsibilities,
                "deadline": deadline_val,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            insert_res = (
                supabase.table("role_agreements")
                .insert(insert_data)
                .execute()
            )
            saved_role = insert_res.data[0] if insert_res.data else insert_data
            msg = "Role declared successfully"

        return {
            "message": msg,
            "role_agreement": saved_role,
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
                    detail="You must be a member of this project to declare or update a role.",
                )

            existing = None
            for item in DEV_ROLE_AGREEMENTS_DB:
                if item.get("project_id") == project_id and item.get("user_id") == user_id:
                    existing = item
                    break

            if existing:
                existing["declared_role"] = role_name
                existing["responsibilities"] = clean_responsibilities
                existing["deadline"] = deadline_val
                existing["updated_at"] = now_iso
                saved_role = existing
                msg = "Role agreement updated successfully (Local Dev Mode)"
            else:
                saved_role = {
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "user_id": user_id,
                    "declared_role": role_name,
                    "responsibilities": clean_responsibilities,
                    "deadline": deadline_val,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                DEV_ROLE_AGREEMENTS_DB.append(saved_role)
                msg = "Role declared successfully (Local Dev Mode)"

            return {
                "message": msg,
                "role_agreement": saved_role,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to save role agreement: {err_msg}",
        )


@router.get(
    "/{project_id}/roles",
    response_model=RoleAgreementsListResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/{project_id}/roles/",
    response_model=RoleAgreementsListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_project_roles(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Retrieve all declared role agreements and responsibilities for members of a project."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()

        # 1. Fetch project to ensure it exists
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

        # 2. Check membership
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
                detail="You must be a member of this project to view declared roles.",
            )

        # 3. Fetch all members with profiles for this project
        members_res = (
            supabase.table("project_members")
            .select("user_id, role, joined_at, profiles(*)")
            .eq("project_id", project_id)
            .execute()
        )
        members_list = members_res.data if members_res.data else []

        # 4. Fetch all declared role agreements
        roles_res = (
            supabase.table("role_agreements")
            .select("*, profiles(*)")
            .eq("project_id", project_id)
            .execute()
        )
        declared_roles = roles_res.data if roles_res.data else []
        declared_map = {r.get("user_id"): r for r in declared_roles if r.get("user_id")}

        # Ensure creator is in members_list
        seen_user_ids = {m.get("user_id") for m in members_list if m.get("user_id")}
        if project_data.get("created_by") and project_data.get("created_by") not in seen_user_ids:
            # Fetch creator profile
            creator_id = project_data.get("created_by")
            creator_prof = supabase.table("profiles").select("*").eq("id", creator_id).single().execute()
            members_list.insert(0, {
                "user_id": creator_id,
                "role": "owner",
                "joined_at": project_data.get("created_at"),
                "profiles": creator_prof.data if creator_prof.data else None,
            })
            seen_user_ids.add(creator_id)

        # Build full team roster
        team_roster = []
        for m in members_list:
            uid = m.get("user_id")
            if not uid:
                continue
            if uid in declared_map:
                role_item = dict(declared_map[uid])
                role_item["is_declared"] = True
                team_roster.append(role_item)
            else:
                team_roster.append({
                    "id": f"pending-{uid}",
                    "project_id": project_id,
                    "user_id": uid,
                    "declared_role": "Pending Role Declaration",
                    "responsibilities": None,
                    "deadline": None,
                    "created_at": m.get("joined_at"),
                    "updated_at": m.get("joined_at"),
                    "profile": m.get("profiles") or m.get("profile") or {"display_name": None, "email": None},
                    "is_declared": False,
                })

        # Include any orphaned role agreements if any
        for r in declared_roles:
            uid = r.get("user_id")
            if uid and uid not in seen_user_ids:
                role_item = dict(r)
                role_item["is_declared"] = True
                team_roster.append(role_item)
                seen_user_ids.add(uid)

        total_members_count = max(len(team_roster), 1)

        return {
            "roles": team_roster,
            "role_agreements": team_roster,
            "project_id": project_id,
            "created_by": project_data.get("created_by"),
            "lead_user_id": project_data.get("created_by"),
            "total_members": total_members_count,
            "declared_count": len(declared_roles),
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
                    detail="You must be a member of this project to view declared roles.",
                )

            project_roles = [
                r for r in DEV_ROLE_AGREEMENTS_DB
                if r.get("project_id") == project_id
            ]
            dev_declared_map = {r.get("user_id"): r for r in project_roles if r.get("user_id")}

            dev_members = [
                m for m in DEV_PROJECT_MEMBERS_DB
                if m.get("project_id") == project_id and m.get("user_id")
            ]
            seen_dev_users = {m.get("user_id") for m in dev_members}
            if project_data.get("created_by") and project_data.get("created_by") not in seen_dev_users:
                dev_members.insert(0, {
                    "project_id": project_id,
                    "user_id": project_data.get("created_by"),
                    "role": "owner",
                })
                seen_dev_users.add(project_data.get("created_by"))

            dev_roster = []
            for m in dev_members:
                uid = m.get("user_id")
                if not uid:
                    continue
                if uid in dev_declared_map:
                    role_item = dict(dev_declared_map[uid])
                    role_item["is_declared"] = True
                    dev_roster.append(role_item)
                else:
                    dev_roster.append({
                        "id": f"pending-{uid}",
                        "project_id": project_id,
                        "user_id": uid,
                        "declared_role": "Pending Role Declaration",
                        "responsibilities": None,
                        "deadline": None,
                        "created_at": None,
                        "updated_at": None,
                        "profile": {"display_name": uid, "email": f"{uid}@buildcrew.io"},
                        "is_declared": False,
                    })

            # Include any other declared roles
            for r in project_roles:
                uid = r.get("user_id")
                if uid and uid not in seen_dev_users:
                    role_item = dict(r)
                    role_item["is_declared"] = True
                    dev_roster.append(role_item)
                    seen_dev_users.add(uid)

            dev_total_members = max(len(dev_roster), 1)

            return {
                "roles": dev_roster,
                "role_agreements": dev_roster,
                "project_id": project_id,
                "created_by": project_data.get("created_by"),
                "lead_user_id": project_data.get("created_by"),
                "total_members": dev_total_members,
                "declared_count": len(project_roles),
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch declared roles: {err_msg}",
        )






