import json
import os
import secrets
import string
import time
import uuid
from datetime import datetime, timedelta, timezone

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from core.database import get_supabase_client, _is_dev_fallback_error, is_dev_mode
from core.dependencies import get_current_user
from core.logging import logger
from core.errors import handle_route_error
from core.rate_limit import limiter, get_user_key
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
    ConfirmationVoteInfo,
    ContributionResponse,
    ContributionsListResponse,
    DraftGenerationResponse,
    LedgerEntryResponse,
    ManualContributionCreate,
)
from services import github_service



router = APIRouter(prefix="/projects", tags=["Projects"])

INVITES_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", ".invites_cache.json"
)


def _load_invites() -> dict:
    if not is_dev_mode():
        return {}
    if os.path.exists(INVITES_CACHE_FILE):
        try:
            with open(INVITES_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_invites(invites: dict) -> None:
    if not is_dev_mode():
        return
    try:
        with open(INVITES_CACHE_FILE, "w") as f:
            json.dump(invites, f, indent=2)
    except Exception:
        pass


DEV_DATA_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", ".dev_data_cache.json"
)


def _load_dev_data() -> dict:
    if not is_dev_mode() or os.environ.get("PYTEST_CURRENT_TEST"):
        return {}
    if os.path.exists(DEV_DATA_CACHE_FILE):
        try:
            with open(DEV_DATA_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_dev_data() -> None:
    if not is_dev_mode() or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        with open(DEV_DATA_CACHE_FILE, "w") as f:
            json.dump(
                {
                    "projects": DEV_PROJECTS_DB,
                    "members": DEV_PROJECT_MEMBERS_DB,
                    "roles": DEV_ROLE_AGREEMENTS_DB,
                    "contributions": DEV_CONTRIBUTIONS_DB,
                    "confirmation_requests": DEV_CONFIRMATION_REQUESTS_DB,
                    "confirmations": DEV_CONFIRMATIONS_DB,
                    "github_identities": DEV_GITHUB_IDENTITIES_DB,
                },
                f,
                indent=2,
            )
    except Exception:
        pass


# In-memory storage with file cache for server reloads
_dev_cache = _load_dev_data()
DEV_PROJECTS_DB: dict[str, dict] = _dev_cache.get("projects", {})
DEV_PROJECT_MEMBERS_DB: list[dict] = _dev_cache.get("members", [])
DEV_PROJECT_INVITES_DB: dict[str, dict] = _load_invites()
DEV_ROLE_AGREEMENTS_DB: list[dict] = _dev_cache.get("roles", [])
DEV_CONTRIBUTIONS_DB: list[dict] = _dev_cache.get("contributions", [])
DEV_CONFIRMATION_REQUESTS_DB: list[dict] = _dev_cache.get("confirmation_requests", [])
DEV_CONFIRMATIONS_DB: list[dict] = _dev_cache.get("confirmations", [])
DEV_GITHUB_IDENTITIES_DB: dict[str, str] = _dev_cache.get("github_identities", {})





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
        try:
            member_res = (
                supabase.table("project_members")
                .insert(member_insert_data)
                .execute()
            )
            if not member_res.data:
                raise RuntimeError("Failed to insert owner member into project_members")
        except Exception as member_err:
            try:
                supabase.table("projects").delete().eq("id", actual_project_id).execute()
            except Exception as del_err:
                logger.error(
                    f"Failed to delete orphan project {actual_project_id} after member insert failure: {del_err}"
                )
            raise handle_route_error(
                member_err,
                generic_message="Failed to create project. Please try again.",
                log_message=f"Failed to insert owner member for project {actual_project_id}",
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
            try:
                DEV_PROJECT_MEMBERS_DB.append(dev_member)
            except Exception as dev_m_err:
                DEV_PROJECTS_DB.pop(project_id, None)
                raise handle_route_error(
                    dev_m_err,
                    generic_message="Failed to create project. Please try again.",
                    log_message=f"Failed to insert owner member for project {project_id}",
                )
            _save_dev_data()

            return {
                "message": "Project created successfully (Local Dev Mode)",
                "project": dev_project,
                "member": dev_member,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to create project. Please try again.",
            log_message="Failed to create project",
        )


@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK, include_in_schema=False)
async def list_projects(
    include_archived: bool = False,
    current_user: Any = Depends(get_current_user),
):
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
                        if not include_archived and proj.get("archived_at"):
                            continue
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
                    if not include_archived and proj.get("archived_at"):
                        continue
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
                if not include_archived and p_data.get("archived_at"):
                    continue
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
                    if not include_archived and p_data.get("archived_at"):
                        continue
                    p_copy = dict(p_data)
                    role = member_project_roles.get(p_id, "owner")
                    p_copy["role"] = role
                    p_copy["my_role"] = role
                    user_projects.append(p_copy)

            return {
                "projects": user_projects,
            }
        raise handle_route_error(
            e,
            generic_message="Failed to fetch projects. Please try again.",
            log_message="Failed to fetch projects",
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
        raise handle_route_error(
            e,
            generic_message="Failed to fetch project details. Please try again.",
            log_message="Failed to fetch project details",
        )


def is_project_archived(project_id: str, supabase: Any = None) -> bool:
    """Check if a project is archived (has archived_at timestamp)."""
    # 1. Check DEV_PROJECTS_DB first
    if project_id in DEV_PROJECTS_DB:
        val = DEV_PROJECTS_DB[project_id].get("archived_at")
        if val and not hasattr(val, "_mock_return_value"):
            return bool(val)

    # 2. Check Supabase
    try:
        if supabase is None:
            supabase = get_supabase_client()
        res = (
            supabase.table("projects")
            .select("archived_at")
            .eq("id", project_id)
            .single()
            .execute()
        )
        if res and hasattr(res, "data") and isinstance(res.data, dict):
            archived_val = res.data.get("archived_at")
            if archived_val and not hasattr(archived_val, "_mock_return_value"):
                return bool(archived_val)
    except Exception:
        pass

    return False


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Permanently delete / dismantle a project (solo lead), or archive if other members exist."""
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

        # Check for other members
        members_res = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", project_id)
            .execute()
        )
        members = members_res.data or []
        other_members = [m for m in members if m.get("user_id") != user_id]

        dev_other = [
            m for m in DEV_PROJECT_MEMBERS_DB
            if m.get("project_id") == project_id and m.get("user_id") != user_id
        ]
        has_other_members = bool(other_members or dev_other)

        if has_other_members:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                supabase.table("projects").update({"archived_at": now_iso}).eq("id", project_id).execute()
            except Exception as upd_err:
                if not _is_dev_fallback_error(str(upd_err)):
                    raise
            if project_id in DEV_PROJECTS_DB:
                DEV_PROJECTS_DB[project_id]["archived_at"] = now_iso
                _save_dev_data()
            return {
                "message": "Project archived successfully",
                "project_id": project_id,
                "archived": True,
            }

        # Solo delete: delete cascades across members, roles, installations in Supabase
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
            "archived": False,
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

            other_members = [
                m for m in DEV_PROJECT_MEMBERS_DB
                if m.get("project_id") == project_id and m.get("user_id") != user_id
            ]

            if other_members:
                now_iso = datetime.now(timezone.utc).isoformat()
                project_data["archived_at"] = now_iso
                _save_dev_data()
                return {
                    "message": "Project archived successfully (Local Dev Mode)",
                    "project_id": project_id,
                    "archived": True,
                }

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
                "archived": False,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to delete project. Please try again.",
            log_message="Failed to delete project",
        )


def _recompute_project_contributions(project_id: str, supabase: Any = None) -> None:
    """Recompute verification statuses for all contributions in a project following membership changes."""
    from routers.contributions import _recompute_contribution_status
    if supabase is not None:
        try:
            c_res = (
                supabase.table("contributions")
                .select("*")
                .eq("project", project_id)
                .execute()
            )
            for c in (c_res.data or []):
                _recompute_contribution_status(supabase, c)
        except Exception:
            pass

    for dev_c in DEV_CONTRIBUTIONS_DB:
        if dev_c.get("project") == project_id or dev_c.get("project_id") == project_id:
            _recompute_contribution_status(supabase, dev_c)


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
        _recompute_project_contributions(project_id, supabase)

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
            _recompute_project_contributions(project_id, None)

            return {
                "message": "Successfully left the project (Local Dev Mode)",
                "project_id": project_id,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to leave project. Please try again.",
            log_message="Failed to leave project",
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
        _recompute_project_contributions(project_id, supabase)

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
            _recompute_project_contributions(project_id, None)

            return {
                "message": "Member removed successfully (Local Dev Mode)",
                "project_id": project_id,
                "user_id": member_user_id,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to remove member. Please try again.",
            log_message="Failed to remove member",
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
        if project_data.get("archived_at") or is_project_archived(project_id, supabase):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project is archived.",
            )
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

        # 3. Permanent invite code: return existing if set; otherwise generate & store (retry up to 5 times)
        if not regenerate and project_data.get("invite_code"):
            invite_code = project_data["invite_code"]
        else:
            stored = False
            for attempt in range(5):
                code_candidate = generate_invite_code()
                try:
                    supabase.table("projects").update({
                        "invite_code": code_candidate
                    }).eq("id", project_id).execute()
                    invite_code = code_candidate
                    stored = True
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if (
                        "unique" in err_str
                        or "duplicate" in err_str
                        or "23505" in err_str
                        or "projects_invite_code_key" in err_str
                    ):
                        logger.warning(
                            f"Invite code collision '{code_candidate}' (attempt {attempt + 1}/5): {e}"
                        )
                        continue
                    raise
            if not stored:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate a unique invite code after multiple attempts.",
                )

        return {
            "invite_code": invite_code,
            "project_id": project_id,
            "project_name": project_data.get("name"),
            "created_by": project_data.get("created_by") or user_id,
            "invite_url": None,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "message": "New invite code generated successfully" if regenerate else "Permanent invite code retrieved successfully",
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
            if project_data.get("archived_at"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Project is archived.",
                )
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

            if not regenerate and project_data.get("invite_code"):
                invite_code = project_data["invite_code"]
            else:
                invite_code = generate_invite_code()
                project_data["invite_code"] = invite_code
                _save_dev_data()

            invite_data = {
                "invite_code": invite_code,
                "project_id": project_id,
                "project_name": project_data.get("name"),
                "created_by": project_data.get("created_by") or user_id,
                "invite_url": None,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "message": "New invite code generated successfully (Local Dev Mode)" if regenerate else "Permanent invite code retrieved successfully (Local Dev Mode)",
            }
            DEV_PROJECT_INVITES_DB[invite_code] = invite_data
            _save_invites(DEV_PROJECT_INVITES_DB)
            return invite_data

        raise handle_route_error(
            e,
            generic_message="Failed to generate invite code. Please try again.",
            log_message="Failed to generate invite code",
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


_join_rate_limits: dict[str, list[float]] = {}


def _check_join_rate_limit(user_id: str, limit: int = 10, window_seconds: float = 60.0) -> None:
    now = time.monotonic()
    user_times = _join_rate_limits.setdefault(user_id, [])
    cutoff = now - window_seconds
    user_times[:] = [t for t in user_times if t > cutoff]
    if len(user_times) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many join attempts. Please try again later.",
        )
    user_times.append(now)


def reset_join_rate_limiter() -> None:
    _join_rate_limits.clear()
    limiter.reset()


@router.post("/join", response_model=ProjectJoinResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute", key_func=get_user_key)
async def join_project_by_invite(
    request: Request,
    payload: ProjectJoinRequest,
    current_user: Any = Depends(get_current_user),
):
    """Join a project using a valid shareable invite code."""
    user_id = _get_user_id(current_user)

    # Rate-limit POST /projects/join to 10/minute per user
    _check_join_rate_limit(user_id)

    raw_code = (payload.invite_code or "").strip()
    if not raw_code:
        raise HTTPException(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            detail="Invite code cannot be empty.",
        )

    # Normalize the code: strip spaces, convert en/em dashes to '-'
    clean_code = "".join(raw_code.split()).replace("\u2013", "-").replace("\u2014", "-")
    # If it is exactly 6 alphanumerics, prepend 'BC-'
    if len(clean_code) == 6 and clean_code.isalnum():
        clean_code = f"BC-{clean_code.upper()}"

    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        supabase = get_supabase_client()

        # Look up projects where upper(invite_code) = upper(submitted code)
        safe_code = clean_code.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        proj_res = (
            supabase.table("projects")
            .select("*")
            .ilike("invite_code", safe_code)
            .execute()
        )
        if not proj_res.data:
            clean_upper = clean_code.upper()
            dev_found = False
            for p in DEV_PROJECTS_DB.values():
                if (p.get("invite_code") or "").strip().upper() == clean_upper:
                    dev_found = True
                    break
            if not dev_found and clean_upper in DEV_PROJECT_INVITES_DB:
                dev_found = True
            if dev_found:
                raise RuntimeError("PGRST116: Local Dev Store fallback")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invite code",
            )

        project_data = proj_res.data[0]
        if (project_data.get("invite_code") or "").strip().upper() != clean_code.upper():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid invite code",
            )

        project_id = project_data["id"]
        if project_data.get("archived_at") or is_project_archived(project_id, supabase):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project is archived.",
            )

        # Check if user is already a member or creator
        is_creator = (project_data.get("created_by") == user_id)
        member_check = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if is_creator or member_check.data:
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
            project_data = None
            clean_upper = clean_code.upper()
            for p in DEV_PROJECTS_DB.values():
                if (p.get("invite_code") or "").strip().upper() == clean_upper:
                    project_data = p
                    break
            if not project_data:
                inv_info = DEV_PROJECT_INVITES_DB.get(clean_upper)
                if inv_info and inv_info.get("project_id") in DEV_PROJECTS_DB:
                    project_data = DEV_PROJECTS_DB[inv_info["project_id"]]

            if not project_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Invalid invite code",
                )

            if project_data.get("archived_at"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Project is archived.",
                )

            project_id = project_data["id"]

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
            _save_dev_data()

            return {
                "message": "Successfully joined project (Local Dev Mode)",
                "project": project_data,
                "member": dev_member,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to join project. Please try again.",
            log_message="Failed to join project",
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
        if project_data.get("archived_at") or is_project_archived(project_id, supabase):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project is archived.",
            )

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
            if project_data.get("archived_at"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Project is archived.",
                )
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
            _save_dev_data()

            return {
                "message": msg,
                "role_agreement": saved_role,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to save role agreement. Please try again.",
            log_message="Failed to save role agreement",
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

        raise handle_route_error(
            e,
            generic_message="Failed to fetch declared roles. Please try again.",
            log_message="Failed to fetch declared roles",
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


def _verified_github_logins(members: list[Any], supabase: Any = None) -> dict[str, str]:
    """
    Build a map of {verified_github_login_lowercase: user_id} for the given project members.
    A member counts ONLY if one of their auth identities in Supabase has provider == 'github'.
    Uses identity_data['user_name'] lowercased.
    profiles.github_username alone is NOT trusted.
    """
    verified_map: dict[str, str] = {}
    if supabase is None:
        try:
            supabase = get_supabase_client()
        except Exception:
            supabase = None

    for m in members:
        uid = m.get("user_id") or m.get("id") if isinstance(m, dict) else str(m)
        if not uid:
            continue

        # In dev mode / tests or when mock identities are provided directly:
        if isinstance(m, dict) and m.get("verified_github_identity"):
            gh_user = m.get("verified_github_identity")
            if gh_user:
                verified_map[str(gh_user).strip().lower()] = uid
                continue

        dev_gh = DEV_GITHUB_IDENTITIES_DB.get(uid)
        if dev_gh:
            verified_map[str(dev_gh).strip().lower()] = uid
            continue

        if supabase is not None:
            try:
                user_res = supabase.auth.admin.get_user_by_id(uid)
                user = getattr(user_res, "user", user_res)
                identities = getattr(user, "identities", None)
                if identities is None and isinstance(user, dict):
                    identities = user.get("identities", [])

                for identity in (identities or []):
                    provider = getattr(identity, "provider", None)
                    if provider is None and isinstance(identity, dict):
                        provider = identity.get("provider")

                    if provider == "github":
                        idata = getattr(identity, "identity_data", None)
                        if idata is None and isinstance(identity, dict):
                            idata = identity.get("identity_data", {})

                        gh_user = idata.get("user_name") if isinstance(idata, dict) else getattr(idata, "user_name", None)
                        if gh_user and str(gh_user).strip():
                            verified_map[str(gh_user).strip().lower()] = uid
                            break
            except Exception as e:
                logger.debug(f"Could not retrieve auth identities for user {uid}: {e}")

    return verified_map


def _match_author_to_member(
    author_login: Optional[str],
    author_email: Optional[str],
    verified_map: dict[str, str],
) -> Optional[str]:
    """Match a GitHub commit or PR author to an app project member using verified GitHub logins only.
    
    (a) Exact case-insensitive match of author_login against verified_map.
    (b) Parse '<id>+<login>@users.noreply.github.com' or '<login>@users.noreply.github.com' and match the same map.
    Delete the name, email, local-part, substring, alphanumeric and fallback_user_id rules.
    Return None when unmatched.
    Treat logins ending in '[bot]' as bots.
    """
    norm_login = (author_login or "").strip().lower()

    # Treat logins ending in '[bot]' as bots
    if norm_login.endswith("[bot]"):
        return None

    # (a) Exact case-insensitive match of author_login against verified_map
    if norm_login and norm_login in verified_map:
        return verified_map[norm_login]

    # (b) Parse noreply email
    if author_email:
        norm_email = author_email.strip().lower()
        if "@users.noreply.github.com" in norm_email:
            local_part = norm_email.split("@users.noreply.github.com")[0]
            if "+" in local_part:
                noreply_login = local_part.split("+", 1)[1]
            else:
                noreply_login = local_part

            noreply_login = noreply_login.strip()
            if noreply_login.endswith("[bot]"):
                return None
            if noreply_login and noreply_login in verified_map:
                return verified_map[noreply_login]

    return None


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
                "avatar_url": c_prof.get("avatar_url") or "",
            })

        # Build verified GitHub logins map
        verified_map = _verified_github_logins(members_lookup, supabase)

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

        new_drafts = []
        unmatched_counts: dict[str, int] = {}
        skipped_bots = 0

        # Process Commits
        for commit in commits:
            commit_url = commit.get("url")
            if commit_url and commit_url in existing_evidence:
                continue

            author_login = commit.get("author_login") or commit.get("author") or ""
            author_email = commit.get("author_email")

            norm_login = str(author_login).strip().lower()
            norm_email = str(author_email or "").strip().lower()

            # Check bot
            if norm_login.endswith("[bot]") or (norm_email.endswith("@users.noreply.github.com") and norm_email.split("@users.noreply.github.com")[0].split("+")[-1].endswith("[bot]")):
                skipped_bots += 1
                continue

            matched_uid = _match_author_to_member(
                author_login=author_login,
                author_email=author_email,
                verified_map=verified_map,
            )

            if not matched_uid:
                raw_key = author_login or _extract_username_from_noreply(author_email) or author_email or "unknown"
                unmatched_counts[raw_key] = unmatched_counts.get(raw_key, 0) + 1
                continue

            draft_item = {
                "id": str(uuid.uuid4()),
                "contributor": matched_uid,
                "project": project_id,
                "title": commit.get("message") or f"Commit {commit.get('sha', '')[:7]}",
                "category": "code",
                "description": f"Git commit {commit.get('sha', '')[:7]} by {author_login or commit.get('author', 'Unknown')}",
                "date_range": commit.get("date"),
                "source_type": "github_commit",
                "evidence_link": commit_url,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "private",
                "dispute_state": "none",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            new_drafts.append(draft_item)
            if commit_url:
                existing_evidence.add(commit_url)

        # Process Pull Requests (merged PRs only)
        for pr in pulls:
            if not pr.get("merged_at"):
                continue

            pr_url = pr.get("url")
            if pr_url and pr_url in existing_evidence:
                continue

            pr_user = pr.get("user") or ""
            norm_pr_user = str(pr_user).strip().lower()

            if norm_pr_user.endswith("[bot]"):
                skipped_bots += 1
                continue

            matched_uid = _match_author_to_member(
                author_login=pr_user,
                author_email=None,
                verified_map=verified_map,
            )

            if not matched_uid:
                unmatched_counts[pr_user] = unmatched_counts.get(pr_user, 0) + 1
                continue

            draft_item = {
                "id": str(uuid.uuid4()),
                "contributor": matched_uid,
                "project": project_id,
                "title": pr.get("title") or f"Pull Request #{pr.get('number')}",
                "category": "pull_request",
                "description": f"Pull Request #{pr.get('number')} (merged) on branch {pr.get('head_branch', 'main')}",
                "date_range": pr.get("merged_at") or pr.get("created_at"),
                "source_type": "github_pr",
                "evidence_link": pr_url,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "private",
                "dispute_state": "none",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            new_drafts.append(draft_item)
            if pr_url:
                existing_evidence.add(pr_url)

        # 7. Persist to Supabase if any new drafts
        saved_drafts = []
        if new_drafts:
            ins_res = supabase.table("contributions").insert(new_drafts).execute()
            saved_drafts = ins_res.data if ins_res.data else new_drafts
        else:
            all_c = (
                supabase.table("contributions")
                .select("*")
                .eq("project", project_id)
                .execute()
            )
            saved_drafts = all_c.data or []

        # Update last_generated_at in installation
        supabase.table("github_installations").update({
            "last_generated_at": now_iso
        }).eq("project_id", project_id).execute()

        prof_dict = {m["user_id"]: m for m in members_lookup}
        from routers.contributions import _enrich_contribution_metadata
        for d in saved_drafts:
            cid = d.get("contributor")
            if cid in prof_dict:
                d["contributor_name"] = prof_dict[cid].get("display_name") or prof_dict[cid].get("email")
                d["contributor_profile"] = prof_dict[cid]
            _enrich_contribution_metadata(d, caller_user_id=user_id, supabase=supabase)

        unmatched_list = [{"login": k, "count": v} for k, v in sorted(unmatched_counts.items())]
        return {
            "message": f"Successfully generated {len(new_drafts)} draft contribution(s) from GitHub.",
            "project_id": project_id,
            "generated_count": len(new_drafts),
            "contributions": saved_drafts,
            "last_generated_at": now_iso,
            "unmatched": unmatched_list,
            "skipped_bots": skipped_bots,
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
                    "verified_github_identity": DEV_GITHUB_IDENTITIES_DB.get(cid, "buildcrew-dev"),
                })

            for m in DEV_PROJECT_MEMBERS_DB:
                uid = m.get("user_id")
                if uid and uid not in dev_seen_ids:
                    dev_seen_ids.add(uid)
                    dev_members_lookup.append({
                        "user_id": uid,
                        "email": f"{uid}@buildcrew.io",
                        "display_name": f"Member {uid}",
                        "verified_github_identity": DEV_GITHUB_IDENTITIES_DB.get(uid, "buildcrew-team"),
                    })

            verified_map = _verified_github_logins(dev_members_lookup, None)

            # Check existing dev contributions
            existing_evidence = {
                c.get("evidence_link")
                for c in DEV_CONTRIBUTIONS_DB
                if (c.get("project") == project_id or c.get("project_id") == project_id) and c.get("evidence_link")
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

            new_dev_drafts = []
            unmatched_counts: dict[str, int] = {}
            skipped_bots = 0

            for commit in commits:
                curl = commit.get("url")
                if curl and curl in existing_evidence:
                    continue

                author_login = commit.get("author_login") or commit.get("author") or ""
                author_email = commit.get("author_email")

                norm_login = str(author_login).strip().lower()
                norm_email = str(author_email or "").strip().lower()

                if norm_login.endswith("[bot]") or (norm_email.endswith("@users.noreply.github.com") and norm_email.split("@users.noreply.github.com")[0].split("+")[-1].endswith("[bot]")):
                    skipped_bots += 1
                    continue

                matched_uid = _match_author_to_member(
                    author_login=author_login,
                    author_email=author_email,
                    verified_map=verified_map,
                )

                if not matched_uid:
                    raw_key = author_login or _extract_username_from_noreply(author_email) or author_email or "unknown"
                    unmatched_counts[raw_key] = unmatched_counts.get(raw_key, 0) + 1
                    continue

                draft_item = {
                    "id": str(uuid.uuid4()),
                    "contributor": matched_uid,
                    "project": project_id,
                    "title": commit.get("message") or f"Commit {commit.get('sha', '')[:7]}",
                    "category": "code",
                    "description": f"Git commit {commit.get('sha', '')[:7]} by {author_login or commit.get('author', 'Unknown')}",
                    "date_range": commit.get("date"),
                    "source_type": "github_commit",
                    "evidence_link": curl,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "private",
                    "dispute_state": "none",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                new_dev_drafts.append(draft_item)
                if curl:
                    existing_evidence.add(curl)

            for pr in pulls:
                if not pr.get("merged_at"):
                    continue

                purl = pr.get("url")
                if purl and purl in existing_evidence:
                    continue

                pr_user = pr.get("user") or ""
                norm_pr_user = str(pr_user).strip().lower()

                if norm_pr_user.endswith("[bot]"):
                    skipped_bots += 1
                    continue

                matched_uid = _match_author_to_member(
                    author_login=pr_user,
                    author_email=None,
                    verified_map=verified_map,
                )

                if not matched_uid:
                    unmatched_counts[pr_user] = unmatched_counts.get(pr_user, 0) + 1
                    continue

                draft_item = {
                    "id": str(uuid.uuid4()),
                    "contributor": matched_uid,
                    "project": project_id,
                    "title": pr.get("title") or f"Pull Request #{pr.get('number')}",
                    "category": "pull_request",
                    "description": f"Pull Request #{pr.get('number')} (merged) on branch {pr.get('head_branch', 'main')}",
                    "date_range": pr.get("merged_at") or pr.get("created_at"),
                    "source_type": "github_pr",
                    "evidence_link": purl,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "private",
                    "dispute_state": "none",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                new_dev_drafts.append(draft_item)
                if purl:
                    existing_evidence.add(purl)

            DEV_CONTRIBUTIONS_DB.extend(new_dev_drafts)
            _save_dev_data()
            if installation:
                installation["last_generated_at"] = now_iso

            all_dev_project_contribs = [
                c for c in DEV_CONTRIBUTIONS_DB if c.get("project") == project_id or c.get("project_id") == project_id
            ]

            dev_prof_dict = {m["user_id"]: m for m in dev_members_lookup}
            from routers.contributions import _enrich_contribution_metadata
            for d in all_dev_project_contribs:
                cid = d.get("contributor")
                if cid in dev_prof_dict:
                    d["contributor_name"] = dev_prof_dict[cid].get("display_name") or dev_prof_dict[cid].get("email")
                    d["contributor_profile"] = dev_prof_dict[cid]
                _enrich_contribution_metadata(d, caller_user_id=user_id, supabase=None)

            unmatched_list = [{"login": k, "count": v} for k, v in sorted(unmatched_counts.items())]
            return {
                "message": f"Successfully generated {len(new_dev_drafts)} draft contribution(s) from GitHub (Local Dev Mode).",
                "project_id": project_id,
                "generated_count": len(new_dev_drafts),
                "contributions": all_dev_project_contribs,
                "last_generated_at": now_iso,
                "unmatched": unmatched_list,
                "skipped_bots": skipped_bots,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to generate draft contributions. Please try again.",
            log_message="Failed to generate draft contributions",
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
    visibility_filter: Optional[str] = Query(None, alias="visibility"),
    current_user: Any = Depends(get_current_user),
):
    """
    List contribution records for a project with optional status, contributor, category, and visibility filtering.
    Guarantees that any contribution with status 'needs-review' or 'disputed' is excluded for all non-author callers
    and completely excluded from public views.
    """
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
        if visibility_filter and visibility_filter.strip():
            query = query.eq("visibility", visibility_filter.strip().lower())

        c_res = query.order("created_at", desc=True).execute()
        raw_contribs = c_res.data or []

        # Enforce legal-safety barrier: exclude needs-review / disputed / private items for non-authors
        is_public_view = bool(visibility_filter and visibility_filter.strip().lower() == "public")
        contribs = []
        for c in raw_contribs:
            is_author = c.get("contributor") == user_id
            is_disputed_or_review = (
                c.get("verification_status") == "needs-review"
                or c.get("dispute_state") == "disputed"
                or c.get("visibility") == "private"
            )
            # Exclude for non-authors
            if is_disputed_or_review and not is_author:
                continue
            # If public query, exclude needs-review/disputed unconditionally even for author
            if is_public_view and (c.get("verification_status") == "needs-review" or c.get("dispute_state") == "disputed"):
                continue
            contribs.append(c)

        # Fetch profile metadata for all visible contributors
        contributor_ids = list({c.get("contributor") for c in contribs if c.get("contributor")})
        profiles_map = {}
        if contributor_ids:
            try:
                p_res = supabase.table("profiles").select("*").in_("id", contributor_ids).execute()
                for p in (p_res.data or []):
                    profiles_map[p.get("id")] = p
            except Exception:
                pass

        # Count drafts vs confirmed across visible project contributions
        all_c_res = (
            supabase.table("contributions")
            .select("*")
            .eq("project", project_id)
            .execute()
        )
        all_raw_items = all_c_res.data or []
        visible_all_items = []
        for c in all_raw_items:
            is_author = c.get("contributor") == user_id
            is_disputed_or_review = (
                c.get("verification_status") == "needs-review"
                or c.get("dispute_state") == "disputed"
                or c.get("visibility") == "private"
            )
            if is_disputed_or_review and not is_author:
                continue
            if is_public_view and (c.get("verification_status") == "needs-review" or c.get("dispute_state") == "disputed"):
                continue
            visible_all_items.append(c)

        draft_count = sum(1 for c in visible_all_items if c.get("verification_status") in ("source-verified", "pending", "draft", "self-declared", "needs-review"))
        confirmed_count = sum(1 for c in visible_all_items if c.get("verification_status") in ("confirmed", "peer-confirmed"))

        from routers.contributions import _enrich_contribution_metadata

        for c in contribs:
            cid = c.get("contributor")
            prof = profiles_map.get(cid) or c.get("profiles") or {}
            c["contributor_name"] = prof.get("display_name") or prof.get("email") or c.get("contributor_name") or (f"User {cid[:8]}" if cid else "Contributor")
            c["contributor_profile"] = prof or None
            _enrich_contribution_metadata(c, caller_user_id=user_id, supabase=supabase)

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

            dev_contribs = [
                c for c in DEV_CONTRIBUTIONS_DB if c.get("project") == project_id
            ]

            # Apply legal-safety barrier: exclude needs-review / disputed / private items for non-authors
            is_public_view = bool(visibility_filter and visibility_filter.strip().lower() == "public")
            visible_dev_contribs = []
            for c in dev_contribs:
                is_author = c.get("contributor") == user_id
                is_disputed_or_review = (
                    c.get("verification_status") == "needs-review"
                    or c.get("dispute_state") == "disputed"
                    or c.get("visibility") == "private"
                )
                if is_disputed_or_review and not is_author:
                    continue
                if is_public_view and (c.get("verification_status") == "needs-review" or c.get("dispute_state") == "disputed"):
                    continue
                visible_dev_contribs.append(c)

            draft_count = sum(1 for c in visible_dev_contribs if c.get("verification_status") in ("source-verified", "pending", "draft", "self-declared", "needs-review"))
            confirmed_count = sum(1 for c in visible_dev_contribs if c.get("verification_status") in ("confirmed", "peer-confirmed"))

            # Apply filters if provided
            filtered_contribs = visible_dev_contribs
            if status_filter and status_filter.strip():
                sf = status_filter.strip().lower()
                filtered_contribs = [c for c in filtered_contribs if c.get("verification_status", "").lower() == sf]
            if contributor_filter and contributor_filter.strip():
                cf = contributor_filter.strip()
                filtered_contribs = [c for c in filtered_contribs if c.get("contributor") == cf]
            if category_filter and category_filter.strip():
                cat_f = category_filter.strip().lower()
                filtered_contribs = [c for c in filtered_contribs if c.get("category", "").lower() == cat_f]
            if visibility_filter and visibility_filter.strip():
                vis_f = visibility_filter.strip().lower()
                filtered_contribs = [c for c in filtered_contribs if c.get("visibility", "").lower() == vis_f]

            from routers.contributions import _enrich_contribution_metadata

            for c in filtered_contribs:
                cid = c.get("contributor")
                if cid and not c.get("contributor_profile"):
                    c["contributor_name"] = c.get("contributor_name") or f"Member {cid}"
                    c["contributor_profile"] = {
                        "user_id": cid,
                        "display_name": c["contributor_name"],
                        "email": f"{cid}@buildcrew.io",
                    }
                _enrich_contribution_metadata(c, caller_user_id=user_id, supabase=None)

            return {
                "project_id": project_id,
                "total_count": len(filtered_contribs),
                "draft_count": draft_count,
                "confirmed_count": confirmed_count,
                "contributions": filtered_contribs,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to list contributions. Please try again.",
            log_message="Failed to list contributions",
        )


@router.get(
    "/{project_id}/contributions/public",
    response_model=ContributionsListResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/{project_id}/contributions/public/",
    response_model=ContributionsListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_public_project_contributions(
    project_id: str,
    category_filter: Optional[str] = Query(None, alias="category"),
):
    """
    Publicly list verified & public contribution records for a project.
    Guarantees any contribution with status 'needs-review' or 'disputed' is 100% excluded.
    Does not require membership or authentication.
    """
    try:
        supabase = get_supabase_client()

        # Check project exists
        proj_res = supabase.table("projects").select("id, name").eq("id", project_id).single().execute()
        if not proj_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        query = (
            supabase.table("contributions")
            .select("*")
            .eq("project", project_id)
            .eq("visibility", "public")
            .neq("verification_status", "needs-review")
            .neq("dispute_state", "disputed")
        )
        if category_filter and category_filter.strip():
            query = query.eq("category", category_filter.strip().lower())

        c_res = query.order("created_at", desc=True).execute()
        raw_contribs = c_res.data or []

        # Extra guarantee: filter out any needs-review or disputed items
        contribs = [
            c for c in raw_contribs
            if c.get("verification_status") != "needs-review"
            and c.get("dispute_state") != "disputed"
            and c.get("visibility") == "public"
        ]

        contributor_ids = list({c.get("contributor") for c in contribs if c.get("contributor")})
        profiles_map = {}
        if contributor_ids:
            try:
                p_res = supabase.table("profiles").select("*").in_("id", contributor_ids).execute()
                for p in (p_res.data or []):
                    profiles_map[p.get("id")] = p
            except Exception:
                pass

        for c in contribs:
            cid = c.get("contributor")
            prof = profiles_map.get(cid) or c.get("profiles") or {}
            c["contributor_name"] = prof.get("display_name") or prof.get("email") or c.get("contributor_name") or (f"User {cid[:8]}" if cid else "Contributor")
            c["contributor_profile"] = prof or None

        confirmed_count = sum(1 for c in contribs if c.get("verification_status") in ("confirmed", "peer-confirmed"))
        draft_count = sum(1 for c in contribs if c.get("verification_status") not in ("confirmed", "peer-confirmed"))

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
            if project_id not in DEV_PROJECTS_DB and not any(c.get("project") == project_id for c in DEV_CONTRIBUTIONS_DB):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )

            dev_contribs = [
                c for c in DEV_CONTRIBUTIONS_DB
                if c.get("project") == project_id
                and c.get("verification_status") != "needs-review"
                and c.get("dispute_state") != "disputed"
                and c.get("visibility") == "public"
            ]

            if category_filter and category_filter.strip():
                cat_f = category_filter.strip().lower()
                dev_contribs = [c for c in dev_contribs if c.get("category", "").lower() == cat_f]

            for c in dev_contribs:
                cid = c.get("contributor")
                if cid and not c.get("contributor_profile"):
                    c["contributor_name"] = c.get("contributor_name") or f"Member {cid}"
                    c["contributor_profile"] = {
                        "user_id": cid,
                        "display_name": c["contributor_name"],
                        "email": f"{cid}@buildcrew.io",
                    }

            confirmed_count = sum(1 for c in dev_contribs if c.get("verification_status") in ("confirmed", "peer-confirmed"))
            draft_count = sum(1 for c in dev_contribs if c.get("verification_status") not in ("confirmed", "peer-confirmed"))

            return {
                "project_id": project_id,
                "total_count": len(dev_contribs),
                "draft_count": draft_count,
                "confirmed_count": confirmed_count,
                "contributions": dev_contribs,
            }

        raise handle_route_error(
            e,
            generic_message="Failed to list public contributions. Please try again.",
            log_message="Failed to list public contributions",
        )



@router.post(
    "/{project_id}/contributions",
    response_model=ContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{project_id}/contributions/",
    response_model=ContributionResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_project_contribution(
    project_id: str,
    payload: ManualContributionCreate,
    current_user: Any = Depends(get_current_user),
):
    """Manually log a non-code contribution for the specified project."""
    payload_dict = payload.model_dump()
    payload_dict["project_id"] = project_id
    from routers.contributions import create_manual_contribution

    return await create_manual_contribution(
        ManualContributionCreate(**payload_dict), current_user=current_user
    )


@router.delete(
    "/{project_id}/contributions/{contribution_id}",
    status_code=status.HTTP_200_OK,
)
@router.delete(
    "/{project_id}/contributions/{contribution_id}/",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def delete_project_contribution(
    project_id: str,
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Delete a logged contribution within a project."""
    from routers.contributions import delete_contribution

    return await delete_contribution(
        contribution_id=contribution_id, current_user=current_user
    )


@router.get(
    "/{project_id}/ledger",
    response_model=List[LedgerEntryResponse],
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/{project_id}/ledger/",
    response_model=List[LedgerEntryResponse],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_project_ledger(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """
    Project ledger: team members only (403 otherwise).
    Returns items ordered newest first.
    Excludes needs-review / disputed items that the caller neither authored nor disputed.
    Sets waiting_on_me: bool (caller != author, has not voted, not disputed).
    """
    user_id = _get_user_id(current_user)
    from routers.contributions import (
        _get_contribution_votes,
        _resolve_user_clean_name,
        _get_project_member_ids,
    )

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
        is_lead = project_data.get("created_by") == user_id

        # 2. Check caller is a project member
        is_member = is_lead
        if not is_member:
            member_res = (
                supabase.table("project_members")
                .select("id")
                .eq("project_id", project_id)
                .eq("user_id", user_id)
                .execute()
            )
            is_member = bool(member_res.data and len(member_res.data) > 0)

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to view the ledger.",
            )

        # 3. Fetch contributions newest first
        c_res = (
            supabase.table("contributions")
            .select("*")
            .eq("project", project_id)
            .order("created_at", desc=True)
            .execute()
        )
        raw_contribs = c_res.data or []

        # Current project members set for valid votes
        current_members = _get_project_member_ids(project_id, supabase)

        # Profiles cache
        contributor_ids = list({str(c.get("contributor") or "") for c in raw_contribs if c.get("contributor")})
        profiles_map = {}
        if contributor_ids:
            try:
                p_res = supabase.table("profiles").select("*").in_("id", contributor_ids).execute()
                for p in (p_res.data or []):
                    profiles_map[str(p.get("id"))] = p
            except Exception:
                pass

        ledger_entries: List[LedgerEntryResponse] = []
        for c in raw_contribs:
            cid = str(c.get("id"))
            author_id = str(c.get("contributor") or c.get("contributor_id") or "")
            is_author = (author_id == str(user_id))
            status_val = c.get("verification_status") or "self-declared"
            dispute_state = c.get("dispute_state") or "none"
            is_disputed = (status_val == "needs-review" or dispute_state == "disputed")

            votes = _get_contribution_votes(cid, supabase)
            valid_votes = [
                v for v in votes
                if str(v.get("confirmed_by_user_id")) in current_members
                and str(v.get("confirmed_by_user_id")) != author_id
            ]

            caller_disputed = any(
                str(v.get("confirmed_by_user_id")) == str(user_id) and v.get("action") == "dispute"
                for v in votes
            )

            # Hide needs-review items caller neither authored nor disputed
            if is_disputed and not is_author and not caller_disputed:
                continue

            has_caller_voted = any(
                str(v.get("confirmed_by_user_id")) == str(user_id)
                for v in votes
            )

            waiting_on_me = (not is_author) and (not has_caller_voted) and (not is_disputed)

            confirmations_list = []
            for cv in sorted([v for v in valid_votes if v.get("action") == "confirm"], key=lambda x: str(x.get("confirmed_at") or "")):
                voter_id = str(cv.get("confirmed_by_user_id"))
                confirmations_list.append(
                    ConfirmationVoteInfo(
                        name=_resolve_user_clean_name(voter_id, supabase),
                        at=cv.get("confirmed_at") or datetime.now(timezone.utc).isoformat(),
                    )
                )

            prof = profiles_map.get(author_id)
            author_clean_name = _resolve_user_clean_name(author_id, supabase) if not prof else (prof.get("display_name") or prof.get("full_name") or _resolve_user_clean_name(author_id, supabase))

            ledger_entries.append(
                LedgerEntryResponse(
                    id=cid,
                    contributor_id=author_id,
                    contributor_name=author_clean_name,
                    title=c.get("title") or "Untitled Deliverable",
                    category=c.get("category"),
                    description=c.get("description"),
                    evidence_link=c.get("evidence_link"),
                    verification_status=status_val,
                    confirmations=confirmations_list,
                    waiting_on_me=waiting_on_me,
                    created_at=c.get("created_at") or datetime.now(timezone.utc).isoformat(),
                )
            )

        return ledger_entries

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            if project_id not in DEV_PROJECTS_DB and not any(c.get("project") == project_id for c in DEV_CONTRIBUTIONS_DB):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )

            project_data = DEV_PROJECTS_DB.get(project_id, {})
            is_lead = project_data.get("created_by") == user_id
            is_member = is_lead or any(
                m.get("project_id") == project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to view the ledger.",
                )

            current_members = _get_project_member_ids(project_id, None)

            dev_items = [
                c for c in DEV_CONTRIBUTIONS_DB
                if c.get("project") == project_id or c.get("project_id") == project_id
            ]
            dev_items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

            ledger_entries = []
            for c in dev_items:
                cid = str(c.get("id"))
                author_id = str(c.get("contributor") or c.get("contributor_id") or "")
                is_author = (author_id == str(user_id))
                status_val = c.get("verification_status") or "self-declared"
                dispute_state = c.get("dispute_state") or "none"
                is_disputed = (status_val == "needs-review" or dispute_state == "disputed")

                votes = _get_contribution_votes(cid, None)
                valid_votes = [
                    v for v in votes
                    if str(v.get("confirmed_by_user_id")) in current_members
                    and str(v.get("confirmed_by_user_id")) != author_id
                ]

                caller_disputed = any(
                    str(v.get("confirmed_by_user_id")) == str(user_id) and v.get("action") == "dispute"
                    for v in votes
                )

                if is_disputed and not is_author and not caller_disputed:
                    continue

                has_caller_voted = any(
                    str(v.get("confirmed_by_user_id")) == str(user_id)
                    for v in votes
                )

                waiting_on_me = (not is_author) and (not has_caller_voted) and (not is_disputed)

                confirmations_list = []
                for cv in sorted([v for v in valid_votes if v.get("action") == "confirm"], key=lambda x: str(x.get("confirmed_at") or "")):
                    voter_id = str(cv.get("confirmed_by_user_id"))
                    confirmations_list.append(
                        ConfirmationVoteInfo(
                            name=_resolve_user_clean_name(voter_id, None),
                            at=cv.get("confirmed_at") or datetime.now(timezone.utc).isoformat(),
                        )
                    )

                author_clean_name = c.get("contributor_name") or _resolve_user_clean_name(author_id, None)

                ledger_entries.append(
                    LedgerEntryResponse(
                        id=cid,
                        contributor_id=author_id,
                        contributor_name=author_clean_name,
                        title=c.get("title") or "Untitled Deliverable",
                        category=c.get("category"),
                        description=c.get("description"),
                        evidence_link=c.get("evidence_link"),
                        verification_status=status_val,
                        confirmations=confirmations_list,
                        waiting_on_me=waiting_on_me,
                        created_at=c.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    )
                )

            return ledger_entries

        raise handle_route_error(
            e,
            generic_message="Failed to fetch project ledger. Please try again.",
            log_message="Failed to fetch project ledger",
        )










