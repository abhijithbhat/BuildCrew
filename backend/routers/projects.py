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
from schemas.contribution import (
    ContributionResponse,
    ContributionsListResponse,
    DraftGenerationResponse,
)
from services import github_service



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
DEV_CONTRIBUTIONS_DB: list[dict] = []



def _is_dev_fallback_error(err_msg: str) -> bool:
    err_lower = err_msg.lower()
    return any(
        s in err_lower
        for s in (
            "nodename nor servname provided",
            "gai_error",
            "name or service not known",
            "supabase_url",
            "environment variables",
            "failed to connect",
            "client disconnected",
            "connection",
            "connect",
            "timeout",
            "network",
            "invalid api key",
            "unauthorized",
            "pgrst",
            "postgrest",
            "mock",
            "invalid input syntax for type uuid",
            "22p02",
            "violates foreign key constraint",
            "foreign key",
            "23503",
            "is not present in table",
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

        # Merge local dev projects
        member_project_roles = {
            m["project_id"]: m.get("role", "member")
            for m in DEV_PROJECT_MEMBERS_DB
            if m.get("user_id") == user_id
        }
        for p_id, p_data in DEV_PROJECTS_DB.items():
            if p_id not in seen_project_ids and (
                p_id in member_project_roles or p_data.get("created_by") == user_id
            ):
                seen_project_ids.add(p_id)
                p_copy = dict(p_data)
                role = member_project_roles.get(p_id, "owner")
                p_copy["role"] = role
                p_copy["my_role"] = role
                projects_list.append(p_copy)

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


def _extract_username_from_noreply(email: Optional[str]) -> Optional[str]:
    """Extract GitHub username from noreply email formats like 12345+username@users.noreply.github.com or username@users.noreply.github.com."""
    if not email:
        return None
    email_clean = email.lower().strip()
    if "@users.noreply.github.com" in email_clean:
        local_part = email_clean.split("@")[0]
        if "+" in local_part:
            return local_part.split("+", 1)[1]
        return local_part
    return None


def _match_author_to_member(
    author_login: Optional[str],
    author_email: Optional[str],
    author_name: Optional[str],
    members: list[dict],
    fallback_user_id: str,
) -> str:
    """Match a GitHub commit, PR, or issue author to an app project member.
    
    Priority matching order:
    1. Exact GitHub username match (case-insensitive)
    2. GitHub Noreply email parsed username match against member's github_username, email, or display_name
    3. Exact email match (case-insensitive)
    4. Exact full name / display_name match (case-insensitive)
    5. Clean email username (local-part before @) matching member's github_username or email local-part
    6. Sanitized alphanumeric name/login match
    7. Fallback to fallback_user_id (current acting user or project owner)
    """
    norm_login = (author_login or "").strip().lower()
    norm_email = (author_email or "").strip().lower()
    norm_name = (author_name or "").strip().lower()
    noreply_user = _extract_username_from_noreply(norm_email)

    # 1. Exact match by GitHub username
    if norm_login:
        for m in members:
            gh_user = (m.get("github_username") or "").strip().lower()
            if gh_user and gh_user == norm_login:
                return m["user_id"]

    # 2. Match GitHub Noreply email parsed username
    if noreply_user:
        for m in members:
            gh_user = (m.get("github_username") or "").strip().lower()
            mem_email = (m.get("email") or "").strip().lower()
            mem_name = (m.get("display_name") or "").strip().lower()
            if gh_user and gh_user == noreply_user:
                return m["user_id"]
            if mem_email and mem_email.split("@")[0] == noreply_user:
                return m["user_id"]
            if mem_name and mem_name == noreply_user:
                return m["user_id"]

    # 3. Exact match by Email
    if norm_email:
        for m in members:
            mem_email = (m.get("email") or "").strip().lower()
            if mem_email and mem_email == norm_email:
                return m["user_id"]

    # 4. Exact match by Name / Display Name
    if norm_name:
        for m in members:
            mem_name = (m.get("display_name") or "").strip().lower()
            if mem_name and (mem_name == norm_name or norm_name in mem_name):
                return m["user_id"]

    # 5. Clean email username (local-part before @) matching
    if norm_email and "@" in norm_email:
        email_prefix = norm_email.split("@")[0]
        if email_prefix:
            for m in members:
                gh_user = (m.get("github_username") or "").strip().lower()
                mem_email = (m.get("email") or "").strip().lower()
                mem_prefix = mem_email.split("@")[0] if "@" in mem_email else ""
                if gh_user and gh_user == email_prefix:
                    return m["user_id"]
                if mem_prefix and mem_prefix == email_prefix:
                    return m["user_id"]

    # 6. Sanitized alphanumeric match
    if norm_login or norm_name:
        clean_author = "".join(c for c in (norm_login or norm_name) if c.isalnum())
        if clean_author:
            for m in members:
                clean_gh = "".join(c for c in (m.get("github_username") or "").lower() if c.isalnum())
                clean_mem = "".join(c for c in (m.get("display_name") or "").lower() if c.isalnum())
                if clean_gh and clean_gh == clean_author:
                    return m["user_id"]
                if clean_mem and clean_mem == clean_author:
                    return m["user_id"]

    # 7. Fallback to current acting user / lead
    return fallback_user_id


@router.post(
    "/{project_id}/generate-draft",
    response_model=DraftGenerationResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{project_id}/generate-draft/",
    response_model=DraftGenerationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def generate_draft_contributions(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Pull GitHub activity since the last milestone/sync and generate draft contribution records with status 'source-verified'."""
    user_id = _get_user_id(current_user)
    now_iso = datetime.now(timezone.utc).isoformat()

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

        # 2. Check project membership
        is_lead = project_data.get("created_by") == user_id
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not is_lead and not (member_res.data and len(member_res.data) > 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to generate contribution drafts.",
            )

        # 3. Check GitHub installation
        installation = github_service.get_project_installation(project_id)
        if not installation or not installation.get("repo_full_name"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project is not connected to a GitHub repository. Please link a repository first.",
            )

        repo_full_name = installation["repo_full_name"]
        installation_id = str(installation.get("installation_id", ""))
        last_generated_at = installation.get("last_generated_at") or installation.get("connected_at")

        # 4. Fetch all project members and profiles for Author Matching Engine
        members_res = (
            supabase.table("project_members")
            .select("user_id, profiles(*)")
            .eq("project_id", project_id)
            .execute()
        )
        members_raw = members_res.data or []
        seen_user_ids = set()
        members_lookup = []

        for m in members_raw:
            uid = m.get("user_id")
            if not uid or uid in seen_user_ids:
                continue
            seen_user_ids.add(uid)
            prof = m.get("profiles") or {}
            members_lookup.append({
                "user_id": uid,
                "email": prof.get("email") or "",
                "display_name": prof.get("display_name") or "",
                "github_username": prof.get("github_username") or "",
                "avatar_url": prof.get("avatar_url") or "",
            })

        # Ensure project creator is in lookup
        creator_id = project_data.get("created_by")
        if creator_id and creator_id not in seen_user_ids:
            creator_prof_res = supabase.table("profiles").select("*").eq("id", creator_id).execute()
            c_prof = creator_prof_res.data[0] if creator_prof_res.data else {}
            members_lookup.insert(0, {
                "user_id": creator_id,
                "email": c_prof.get("email") or "",
                "display_name": c_prof.get("display_name") or "",
                "github_username": c_prof.get("github_username") or "",
                "avatar_url": c_prof.get("avatar_url") or "",
            })

        # 5. Fetch existing contributions to avoid duplicate draft creation
        c_res = (
            supabase.table("contributions")
            .select("evidence_link, title")
            .eq("project", project_id)
            .execute()
        )
        existing_evidence = {
            c.get("evidence_link") for c in (c_res.data or []) if c.get("evidence_link")
        }

        # 6. Fetch live GitHub activity
        commits = await github_service.fetch_repository_commits(
            repo_full_name=repo_full_name,
            installation_id=installation_id,
            per_page=50,
            since=last_generated_at,
        )
        pulls = await github_service.fetch_repository_pulls(
            repo_full_name=repo_full_name,
            installation_id=installation_id,
            state="all",
            per_page=30,
        )
        issues = await github_service.fetch_repository_issues(
            repo_full_name=repo_full_name,
            installation_id=installation_id,
            state="all",
            per_page=30,
        )

        new_drafts = []

        # Process Commits
        for commit in commits:
            commit_url = commit.get("url")
            if commit_url and commit_url in existing_evidence:
                continue

            matched_uid = _match_author_to_member(
                author_login=commit.get("author_login") or commit.get("author"),
                author_email=commit.get("author_email"),
                author_name=commit.get("author_name") or commit.get("author"),
                members=members_lookup,
                fallback_user_id=user_id,
            )

            draft_item = {
                "id": str(uuid.uuid4()),
                "contributor": matched_uid,
                "project": project_id,
                "title": commit.get("message") or f"Commit {commit.get('sha', '')[:7]}",
                "category": "code",
                "description": f"Git commit {commit.get('sha', '')[:7]} by {commit.get('author', 'Unknown')}",
                "date_range": commit.get("date"),
                "source_type": "github_commit",
                "evidence_link": commit_url,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            new_drafts.append(draft_item)
            if commit_url:
                existing_evidence.add(commit_url)

        # Process Pull Requests
        for pr in pulls:
            pr_url = pr.get("url")
            if pr_url and pr_url in existing_evidence:
                continue

            matched_uid = _match_author_to_member(
                author_login=pr.get("user"),
                author_email=None,
                author_name=None,
                members=members_lookup,
                fallback_user_id=user_id,
            )

            draft_item = {
                "id": str(uuid.uuid4()),
                "contributor": matched_uid,
                "project": project_id,
                "title": pr.get("title") or f"Pull Request #{pr.get('number')}",
                "category": "pull_request",
                "description": f"Pull Request #{pr.get('number')} ({pr.get('state')}) on branch {pr.get('head_branch', 'main')}",
                "date_range": pr.get("created_at"),
                "source_type": "github_pr",
                "evidence_link": pr_url,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            new_drafts.append(draft_item)
            if pr_url:
                existing_evidence.add(pr_url)

        # Process Issues
        for issue in issues:
            issue_url = issue.get("url")
            if issue_url and issue_url in existing_evidence:
                continue

            matched_uid = _match_author_to_member(
                author_login=issue.get("user"),
                author_email=None,
                author_name=None,
                members=members_lookup,
                fallback_user_id=user_id,
            )

            draft_item = {
                "id": str(uuid.uuid4()),
                "contributor": matched_uid,
                "project": project_id,
                "title": issue.get("title") or f"Issue #{issue.get('number')}",
                "category": "issue",
                "description": f"GitHub Issue #{issue.get('number')} ({issue.get('state')})",
                "date_range": issue.get("created_at"),
                "source_type": "github_issue",
                "evidence_link": issue_url,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            new_drafts.append(draft_item)
            if issue_url:
                existing_evidence.add(issue_url)

        # 7. Persist to Supabase if any new drafts
        saved_drafts = []
        if new_drafts:
            ins_res = supabase.table("contributions").insert(new_drafts).execute()
            saved_drafts = ins_res.data if ins_res.data else new_drafts
        else:
            # Fetch existing drafts for display
            all_c = (
                supabase.table("contributions")
                .select("*")
                .eq("project", project_id)
                .execute()
            )
            saved_drafts = all_c.data or []

        # Update last_generated_at in installation
        try:
            supabase.table("github_installations").update({
                "last_generated_at": now_iso
            }).eq("project_id", project_id).execute()
        except Exception:
            pass

        # Build profile lookup dictionary for response enrichment
        prof_dict = {m["user_id"]: m for m in members_lookup}
        for d in saved_drafts:
            cid = d.get("contributor")
            if cid in prof_dict:
                d["contributor_name"] = prof_dict[cid].get("display_name") or prof_dict[cid].get("email")
                d["contributor_profile"] = prof_dict[cid]

        return {
            "message": f"Successfully generated {len(new_drafts)} draft contribution(s) from GitHub.",
            "project_id": project_id,
            "generated_count": len(new_drafts),
            "contributions": saved_drafts,
            "last_generated_at": now_iso,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode Fallback
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )
            project_data = DEV_PROJECTS_DB[project_id]

            is_lead = project_data.get("created_by") == user_id
            is_member = is_lead or any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to generate contribution drafts.",
                )

            installation = github_service.get_project_installation(project_id)
            if not installation or not installation.get("repo_full_name"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Project is not connected to a GitHub repository. Please link a repository first.",
                )

            repo_full_name = installation["repo_full_name"]
            installation_id = str(installation.get("installation_id", ""))
            last_generated_at = installation.get("last_generated_at") or installation.get("connected_at")

            # Build dev members lookup
            dev_members_lookup = []
            dev_seen_ids = set()

            if project_data.get("created_by"):
                cid = project_data.get("created_by")
                dev_seen_ids.add(cid)
                dev_members_lookup.append({
                    "user_id": cid,
                    "email": f"{cid}@buildcrew.io",
                    "display_name": f"Lead {cid}",
                    "github_username": "buildcrew-dev",
                })

            for m in DEV_PROJECT_MEMBERS_DB:
                uid = m.get("user_id")
                if uid and uid not in dev_seen_ids:
                    dev_seen_ids.add(uid)
                    dev_members_lookup.append({
                        "user_id": uid,
                        "email": f"{uid}@buildcrew.io",
                        "display_name": f"Member {uid}",
                        "github_username": "buildcrew-team",
                    })

            # Check existing dev contributions
            existing_evidence = {
                c.get("evidence_link")
                for c in DEV_CONTRIBUTIONS_DB
                if c.get("project") == project_id and c.get("evidence_link")
            }

            commits = await github_service.fetch_repository_commits(
                repo_full_name=repo_full_name,
                installation_id=installation_id,
                per_page=50,
                since=last_generated_at,
            )
            pulls = await github_service.fetch_repository_pulls(
                repo_full_name=repo_full_name,
                installation_id=installation_id,
                state="all",
                per_page=30,
            )
            issues = await github_service.fetch_repository_issues(
                repo_full_name=repo_full_name,
                installation_id=installation_id,
                state="all",
                per_page=30,
            )

            new_dev_drafts = []

            for commit in commits:
                curl = commit.get("url")
                if curl and curl in existing_evidence:
                    continue

                matched_uid = _match_author_to_member(
                    author_login=commit.get("author_login") or commit.get("author"),
                    author_email=commit.get("author_email"),
                    author_name=commit.get("author_name") or commit.get("author"),
                    members=dev_members_lookup,
                    fallback_user_id=user_id,
                )

                draft_item = {
                    "id": str(uuid.uuid4()),
                    "contributor": matched_uid,
                    "project": project_id,
                    "title": commit.get("message") or f"Commit {commit.get('sha', '')[:7]}",
                    "category": "code",
                    "description": f"Git commit {commit.get('sha', '')[:7]} by {commit.get('author', 'Unknown')}",
                    "date_range": commit.get("date"),
                    "source_type": "github_commit",
                    "evidence_link": curl,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "public",
                    "dispute_state": "none",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                new_dev_drafts.append(draft_item)
                if curl:
                    existing_evidence.add(curl)

            for pr in pulls:
                purl = pr.get("url")
                if purl and purl in existing_evidence:
                    continue

                matched_uid = _match_author_to_member(
                    author_login=pr.get("user"),
                    author_email=None,
                    author_name=None,
                    members=dev_members_lookup,
                    fallback_user_id=user_id,
                )

                draft_item = {
                    "id": str(uuid.uuid4()),
                    "contributor": matched_uid,
                    "project": project_id,
                    "title": pr.get("title") or f"Pull Request #{pr.get('number')}",
                    "category": "pull_request",
                    "description": f"Pull Request #{pr.get('number')} ({pr.get('state')}) on branch {pr.get('head_branch', 'main')}",
                    "date_range": pr.get("created_at"),
                    "source_type": "github_pr",
                    "evidence_link": purl,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "public",
                    "dispute_state": "none",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                new_dev_drafts.append(draft_item)
                if purl:
                    existing_evidence.add(purl)

            for issue in issues:
                iurl = issue.get("url")
                if iurl and iurl in existing_evidence:
                    continue

                matched_uid = _match_author_to_member(
                    author_login=issue.get("user"),
                    author_email=None,
                    author_name=None,
                    members=dev_members_lookup,
                    fallback_user_id=user_id,
                )

                draft_item = {
                    "id": str(uuid.uuid4()),
                    "contributor": matched_uid,
                    "project": project_id,
                    "title": issue.get("title") or f"Issue #{issue.get('number')}",
                    "category": "issue",
                    "description": f"GitHub Issue #{issue.get('number')} ({issue.get('state')})",
                    "date_range": issue.get("created_at"),
                    "source_type": "github_issue",
                    "evidence_link": iurl,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "public",
                    "dispute_state": "none",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                new_dev_drafts.append(draft_item)
                if iurl:
                    existing_evidence.add(iurl)

            DEV_CONTRIBUTIONS_DB.extend(new_dev_drafts)
            if installation:
                installation["last_generated_at"] = now_iso

            all_dev_project_contribs = [
                c for c in DEV_CONTRIBUTIONS_DB if c.get("project") == project_id
            ]

            dev_prof_dict = {m["user_id"]: m for m in dev_members_lookup}
            for d in all_dev_project_contribs:
                cid = d.get("contributor")
                if cid in dev_prof_dict:
                    d["contributor_name"] = dev_prof_dict[cid].get("display_name") or dev_prof_dict[cid].get("email")
                    d["contributor_profile"] = dev_prof_dict[cid]

            return {
                "message": f"Successfully generated {len(new_dev_drafts)} draft contribution(s) from GitHub (Local Dev Mode).",
                "project_id": project_id,
                "generated_count": len(new_dev_drafts),
                "contributions": all_dev_project_contribs,
                "last_generated_at": now_iso,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate draft contributions: {err_msg}",
        )


@router.get(
    "/{project_id}/contributions",
    response_model=ContributionsListResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/{project_id}/contributions/",
    response_model=ContributionsListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_project_contributions(
    project_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    contributor_filter: Optional[str] = Query(None, alias="contributor"),
    category_filter: Optional[str] = Query(None, alias="category"),
    current_user: Any = Depends(get_current_user),
):
    """List all contribution records (drafts and confirmed) for a project with optional status, contributor, and category filtering."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()

        # 1. Verify project exists
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

        # 2. Verify membership
        is_lead = project_data.get("created_by") == user_id
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not is_lead and not (member_res.data and len(member_res.data) > 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to view contributions.",
            )

        # 3. Fetch contributions
        query = (
            supabase.table("contributions")
            .select("*")
            .eq("project", project_id)
        )
        if status_filter and status_filter.strip():
            query = query.eq("verification_status", status_filter.strip().lower())
        if contributor_filter and contributor_filter.strip():
            query = query.eq("contributor", contributor_filter.strip())
        if category_filter and category_filter.strip():
            query = query.eq("category", category_filter.strip().lower())

        c_res = query.order("created_at", desc=True).execute()
        contribs = c_res.data or []

        # Fetch profile metadata for all contributors
        contributor_ids = list({c.get("contributor") for c in contribs if c.get("contributor")})
        profiles_map = {}
        if contributor_ids:
            try:
                p_res = supabase.table("profiles").select("*").in_("id", contributor_ids).execute()
                for p in (p_res.data or []):
                    profiles_map[p.get("id")] = p
            except Exception:
                pass

        # Count drafts vs confirmed across all project contributions
        all_c_res = (
            supabase.table("contributions")
            .select("verification_status")
            .eq("project", project_id)
            .execute()
        )
        all_items = all_c_res.data or []
        draft_count = sum(1 for c in all_items if c.get("verification_status") in ("source-verified", "pending", "draft"))
        confirmed_count = sum(1 for c in all_items if c.get("verification_status") == "confirmed")

        for c in contribs:
            cid = c.get("contributor")
            prof = profiles_map.get(cid) or c.get("profiles") or {}
            c["contributor_name"] = prof.get("display_name") or prof.get("email") or c.get("contributor_name") or (f"User {cid[:8]}" if cid else "Contributor")
            c["contributor_profile"] = prof or None

        return {
            "project_id": project_id,
            "total_count": len(contribs),
            "draft_count": draft_count,
            "confirmed_count": confirmed_count,
            "contributions": contribs,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Mode Fallback
            if project_id in DEV_PROJECTS_DB:
                project_data = DEV_PROJECTS_DB[project_id]

                is_lead = project_data.get("created_by") == user_id
                is_member = is_lead or any(
                    m.get("project_id") == project_id and m.get("user_id") == user_id
                    for m in DEV_PROJECT_MEMBERS_DB
                )
                if not is_member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You must be a member of this project to view contributions.",
                    )
            elif any(c.get("project") == project_id for c in DEV_CONTRIBUTIONS_DB):
                pass
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )
            project_data = DEV_PROJECTS_DB[project_id]

            is_lead = project_data.get("created_by") == user_id
            is_member = is_lead or any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to view contributions.",
                )

            dev_contribs = [
                c for c in DEV_CONTRIBUTIONS_DB if c.get("project") == project_id
            ]

            draft_count = sum(1 for c in dev_contribs if c.get("verification_status") in ("source-verified", "pending", "draft"))
            confirmed_count = sum(1 for c in dev_contribs if c.get("verification_status") == "confirmed")

            # Apply filters if provided
            filtered_contribs = dev_contribs
            if status_filter and status_filter.strip():
                sf = status_filter.strip().lower()
                filtered_contribs = [c for c in filtered_contribs if c.get("verification_status", "").lower() == sf]
            if contributor_filter and contributor_filter.strip():
                cf = contributor_filter.strip()
                filtered_contribs = [c for c in filtered_contribs if c.get("contributor") == cf]
            if category_filter and category_filter.strip():
                cat_f = category_filter.strip().lower()
                filtered_contribs = [c for c in filtered_contribs if c.get("category", "").lower() == cat_f]

            for c in filtered_contribs:
                cid = c.get("contributor")
                if cid and not c.get("contributor_profile"):
                    c["contributor_name"] = c.get("contributor_name") or f"Member {cid}"
                    c["contributor_profile"] = {
                        "user_id": cid,
                        "display_name": c["contributor_name"],
                        "email": f"{cid}@buildcrew.io",
                    }

            return {
                "project_id": project_id,
                "total_count": len(filtered_contribs),
                "draft_count": draft_count,
                "confirmed_count": confirmed_count,
                "contributions": filtered_contribs,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list contributions: {err_msg}",
        )







