import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from core.database import get_supabase_client
from core.dependencies import get_current_user
from core.logging import logger
from routers.auth import DEV_USER_NAMES_DB
from routers.projects import (
    DEV_CONTRIBUTIONS_DB,
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    _get_user_id,
    _is_dev_fallback_error,
)
from schemas.contribution import (
    ContributionResponse,
    EvidenceUploadResponse,
    ManualContributionCreate,
)

router = APIRouter(prefix="/contributions", tags=["Contributions"])


@router.post(
    "/upload-evidence",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/upload-evidence/",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_evidence_file(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    current_user: Any = Depends(get_current_user),
):
    """Upload evidence file (screenshot, document, image, PDF) to Supabase Storage with local dev fallback."""
    user_id = _get_user_id(current_user)

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded.",
        )

    file_bytes = await file.read()
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Maximum 25MB file size limit
    max_size_bytes = 25 * 1024 * 1024
    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum limit of 25MB.",
        )

    # Clean filename
    raw_filename = os.path.basename(file.filename)
    clean_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", raw_filename)
    content_type = file.content_type or mimetypes.guess_type(clean_filename)[0] or "application/octet-stream"

    unique_prefix = uuid.uuid4().hex[:12]
    storage_path = f"{user_id}/{unique_prefix}_{clean_filename}"

    try:
        supabase = get_supabase_client()
        bucket_name = "evidence"

        # Upload file to Supabase Storage
        upload_res = supabase.storage.from_(bucket_name).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )

        # Generate public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(storage_path)

        return {
            "url": public_url,
            "filename": clean_filename,
            "file_type": content_type,
            "size_bytes": len(file_bytes),
            "storage_path": storage_path,
        }

    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg) or "bucket" in err_msg.lower() or "storage" in err_msg.lower() or "not found" in err_msg.lower():
            # Local Dev Fallback
            upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads", "evidence", user_id)
            os.makedirs(upload_dir, exist_ok=True)
            saved_filename = f"{unique_prefix}_{clean_filename}"
            saved_filepath = os.path.join(upload_dir, saved_filename)
            with open(saved_filepath, "wb") as f:
                f.write(file_bytes)

            local_url = f"/static/evidence/{user_id}/{saved_filename}"
            return {
                "url": local_url,
                "filename": clean_filename,
                "file_type": content_type,
                "size_bytes": len(file_bytes),
                "storage_path": f"evidence/{user_id}/{saved_filename}",
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to upload evidence file: {err_msg}",
        )


@router.post(
    "",
    response_model=ContributionResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/",
    response_model=ContributionResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_manual_contribution(
    payload: ManualContributionCreate,
    current_user: Any = Depends(get_current_user),
):
    """Manually log non-code contribution (e.g. Design, Research, Docs) with evidence and self-declared status."""
    user_id = _get_user_id(current_user)

    target_project_id = (payload.project_id or payload.project or "").strip()
    if not target_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID is required to log a contribution.",
        )

    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contribution title cannot be empty.",
        )

    category = (payload.category or "other").strip().lower()
    date_range = (
        payload.date_range.strip()
        if payload.date_range and payload.date_range.strip()
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    source_type = (payload.source_type or "manual").strip()
    evidence_link = (
        payload.evidence_link.strip() if payload.evidence_link else None
    )
    description = (
        payload.description.strip() if payload.description else None
    )
    visibility = (payload.visibility or "public").strip()

    now_iso = datetime.now(timezone.utc).isoformat()
    contribution_id = str(uuid.uuid4())

    new_record = {
        "id": contribution_id,
        "contributor": user_id,
        "project": target_project_id,
        "title": title,
        "category": category,
        "description": description,
        "date_range": date_range,
        "source_type": source_type,
        "evidence_link": evidence_link,
        "verification_status": "self-declared",
        "confirmed_by": None,
        "visibility": visibility,
        "dispute_state": "none",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    try:
        supabase = get_supabase_client()

        # 1. Verify project exists
        proj_res = (
            supabase.table("projects")
            .select("*")
            .eq("id", target_project_id)
            .single()
            .execute()
        )
        if not proj_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )
        project_data = proj_res.data

        # 2. Verify membership (must be project creator or member)
        is_lead = project_data.get("created_by") == user_id
        member_res = (
            supabase.table("project_members")
            .select("*")
            .eq("project_id", target_project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not is_lead and not (member_res.data and len(member_res.data) > 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to log contributions.",
            )

        # 3. Fetch contributor profile
        profile_data = {}
        try:
            profile_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            profile_data = profile_res.data or {}
        except Exception:
            pass

        # 4. Insert contribution
        ins_res = (
            supabase.table("contributions")
            .insert(new_record)
            .execute()
        )
        saved = (
            ins_res.data[0]
            if ins_res.data and len(ins_res.data) > 0
            else new_record
        )

        display_name = (
            profile_data.get("display_name")
            or profile_data.get("email")
            or getattr(current_user, "email", None)
            or f"User {user_id[:8]}"
        )
        saved["contributor_name"] = display_name
        saved["contributor_profile"] = profile_data or {
            "id": user_id,
            "display_name": display_name,
            "email": getattr(current_user, "email", f"{user_id}@buildcrew.io"),
        }

        return saved

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Dev mode fallback
            if target_project_id in DEV_PROJECTS_DB:
                project_data = DEV_PROJECTS_DB[target_project_id]
                is_lead = project_data.get("created_by") == user_id
                is_member = is_lead or any(
                    m.get("project_id") == target_project_id
                    and m.get("user_id") == user_id
                    for m in DEV_PROJECT_MEMBERS_DB
                )
                if not is_member:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You must be a member of this project to log contributions.",
                    )
            elif DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )

            user_email = getattr(current_user, "email", None)
            display_name = (
                DEV_USER_NAMES_DB.get(user_email.lower())
                if user_email
                else None
            ) or user_email or f"User {user_id[:8]}"

            dev_record = dict(new_record)
            dev_record["contributor_name"] = display_name
            dev_record["contributor_profile"] = {
                "id": user_id,
                "display_name": display_name,
                "email": user_email or f"{user_id}@buildcrew.io",
            }
            DEV_CONTRIBUTIONS_DB.insert(0, dev_record)
            return dev_record

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create contribution: {err_msg}",
        )


@router.delete(
    "/{contribution_id}",
    status_code=status.HTTP_200_OK,
)
@router.delete(
    "/{contribution_id}/",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def delete_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Delete a logged contribution. Only the author or project team lead can delete it."""
    user_id = _get_user_id(current_user)

    try:
        supabase = get_supabase_client()

        # 1. Fetch contribution
        c_res = (
            supabase.table("contributions")
            .select("*")
            .eq("id", contribution_id)
            .execute()
        )
        if not c_res.data or len(c_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Check authorization (Author or Team Lead)
        target_project_id = contribution.get("project") or contribution.get("project_id")
        is_author = contribution.get("contributor") == user_id
        is_lead = False

        if target_project_id:
            try:
                proj_res = (
                    supabase.table("projects")
                    .select("created_by")
                    .eq("id", target_project_id)
                    .single()
                    .execute()
                )
                if proj_res.data and proj_res.data.get("created_by") == user_id:
                    is_lead = True
            except Exception:
                pass

        if not is_author and not is_lead:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to delete this contribution.",
            )

        # 3. Delete from Supabase
        supabase.table("contributions").delete().eq("id", contribution_id).execute()

        return {
            "success": True,
            "message": "Contribution deleted successfully.",
            "id": contribution_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Dev mode fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]
            target_project_id = contribution.get("project") or contribution.get("project_id")
            is_author = contribution.get("contributor") == user_id
            is_lead = False
            if target_project_id and target_project_id in DEV_PROJECTS_DB:
                is_lead = DEV_PROJECTS_DB[target_project_id].get("created_by") == user_id

            if not is_author and not is_lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to delete this contribution.",
                )

            DEV_CONTRIBUTIONS_DB.remove(contribution)
            return {
                "success": True,
                "message": "Contribution deleted successfully.",
                "id": contribution_id,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete contribution: {err_msg}",
        )

