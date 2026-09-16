import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from core.database import get_supabase_client
from core.dependencies import get_current_user
from core.logging import logger
from routers.auth import DEV_USER_NAMES_DB
from routers.projects import (
    DEV_CONFIRMATION_REQUESTS_DB,
    DEV_CONTRIBUTIONS_DB,
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_ROLE_AGREEMENTS_DB,
    _get_user_id,
    _is_dev_fallback_error,
    _save_dev_data,
)
from schemas.contribution import (
    ConfirmationRequestResponse,
    ContributionResponse,
    EvidenceUploadResponse,
    ManualContributionCreate,
    PendingConfirmationsListResponse,
    ProjectPassportResponse,
    PublicContributionsResponse,
    RequestConfirmationPayload,
    UserPassportResponse,
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
    visibility = (payload.visibility or "private").strip()

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
            _save_dev_data()
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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
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
            _save_dev_data()
            return {
                "success": True,
                "message": "Contribution deleted successfully.",
                "id": contribution_id,
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete contribution: {err_msg}",
        )


@router.post(
    "/{contribution_id}/request-confirmation",
    response_model=list[ConfirmationRequestResponse],
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{contribution_id}/request-confirmation/",
    response_model=list[ConfirmationRequestResponse],
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def request_peer_confirmation(
    contribution_id: str,
    payload: RequestConfirmationPayload,
    current_user: Any = Depends(get_current_user),
):
    """Request peer confirmation from project teammates for a logged deliverable."""
    user_id = _get_user_id(current_user)

    reviewer_ids = list(dict.fromkeys(r.strip() for r in payload.reviewer_ids if r and r.strip()))
    if not reviewer_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one teammate reviewer must be selected.",
        )

    if user_id in reviewer_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot request confirmation from yourself.",
        )

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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Author check
        contrib_author = contribution.get("contributor") or contribution.get("contributor_id")
        if contrib_author != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author of a contribution can request peer confirmation.",
            )

        # 2b. Self-Request Block: Contributor cannot request confirmation from themselves
        if user_id in reviewer_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot request confirmation from yourself.",
            )

        target_project_id = contribution.get("project") or contribution.get("project_id")

        # 3. Fetch project and verify project exists
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
        project_name = project_data.get("name") or "Project"

        # 4. Fetch project members (creator + team members)
        m_res = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", target_project_id)
            .execute()
        )
        valid_member_ids = {m.get("user_id") for m in (m_res.data or []) if m.get("user_id")}
        if project_data.get("created_by"):
            valid_member_ids.add(project_data.get("created_by"))

        # Verify all reviewer_ids are valid project members
        for rev_id in reviewer_ids:
            if rev_id not in valid_member_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Reviewer '{rev_id}' is not a verified member of this project.",
                )

        # 5. Fetch contributor display name
        contributor_name = contribution.get("contributor_name")
        if not contributor_name:
            try:
                prof_res = (
                    supabase.table("profiles")
                    .select("display_name")
                    .eq("id", user_id)
                    .single()
                    .execute()
                )
                if prof_res.data:
                    contributor_name = prof_res.data.get("display_name")
            except Exception:
                pass
        contributor_name = contributor_name or getattr(current_user, "email", None) or f"User {user_id[:8]}"

        # 6. Create or retrieve pending confirmation requests
        created_records = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for rev_id in reviewer_ids:
            existing = (
                supabase.table("confirmation_requests")
                .select("*")
                .eq("contribution_id", contribution_id)
                .eq("reviewer_id", rev_id)
                .eq("status", "pending")
                .execute()
            )
            if existing.data and len(existing.data) > 0:
                rec = existing.data[0]
            else:
                new_rec = {
                    "id": str(uuid.uuid4()),
                    "contribution_id": contribution_id,
                    "project_id": target_project_id,
                    "requested_by": user_id,
                    "reviewer_id": rev_id,
                    "status": "pending",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                ins = supabase.table("confirmation_requests").insert(new_rec).execute()
                rec = ins.data[0] if ins.data and len(ins.data) > 0 else new_rec

            rec_copy = dict(rec)
            rec_copy["contribution_title"] = contribution.get("title")
            rec_copy["project_name"] = project_name
            rec_copy["contributor_name"] = contributor_name
            rec_copy["category"] = contribution.get("category")
            rec_copy["description"] = contribution.get("description")
            rec_copy["evidence_link"] = contribution.get("evidence_link")
            created_records.append(rec_copy)

        # 7. Update contribution status to confirmation-pending
        try:
            supabase.table("contributions").update({
                "verification_status": "confirmation-pending",
                "updated_at": now_iso,
            }).eq("id", contribution_id).execute()
        except Exception:
            pass

        return created_records

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]

            contrib_author = contribution.get("contributor") or contribution.get("contributor_id")
            if contrib_author != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the author of a contribution can request peer confirmation.",
                )

            # Self-Request Block
            if user_id in reviewer_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot request confirmation from yourself.",
                )

            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            valid_member_ids = {
                m.get("user_id")
                for m in DEV_PROJECT_MEMBERS_DB
                if m.get("project_id") == target_project_id and m.get("user_id")
            }
            if project_data.get("created_by"):
                valid_member_ids.add(project_data.get("created_by"))

            for rev_id in reviewer_ids:
                if rev_id not in valid_member_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Reviewer '{rev_id}' is not a verified member of this project.",
                    )

            user_email = getattr(current_user, "email", None)
            contributor_name = (
                contribution.get("contributor_name")
                or (DEV_USER_NAMES_DB.get(user_email.lower()) if user_email else None)
                or user_email
                or f"User {user_id[:8]}"
            )
            project_name = project_data.get("name") or "Project"

            created_records = []
            for rev_id in reviewer_ids:
                existing = [
                    r for r in DEV_CONFIRMATION_REQUESTS_DB
                    if r.get("contribution_id") == contribution_id
                    and r.get("reviewer_id") == rev_id
                    and r.get("status") == "pending"
                ]
                if existing:
                    rec = existing[0]
                else:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    rec = {
                        "id": str(uuid.uuid4()),
                        "contribution_id": contribution_id,
                        "project_id": target_project_id,
                        "requested_by": user_id,
                        "reviewer_id": rev_id,
                        "status": "pending",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    DEV_CONFIRMATION_REQUESTS_DB.insert(0, rec)

                rec_copy = dict(rec)
                rec_copy["contribution_title"] = contribution.get("title")
                rec_copy["project_name"] = project_name
                rec_copy["contributor_name"] = contributor_name
                rec_copy["category"] = contribution.get("category")
                rec_copy["description"] = contribution.get("description")
                rec_copy["evidence_link"] = contribution.get("evidence_link")
                created_records.append(rec_copy)

            contribution["verification_status"] = "confirmation-pending"
            contribution["updated_at"] = now_iso
            _save_dev_data()
            return created_records

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to request confirmation: {err_msg}",
        )


@router.post(
    "/{contribution_id}/confirm",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/confirm/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def confirm_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Peer confirms a teammate's contribution, updating status to 'peer-confirmed'."""
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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Self-Action Block: Author cannot confirm their own contribution
        author_id = contribution.get("contributor") or contribution.get("contributor_id")
        if author_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authors cannot confirm their own contributions.",
            )

        target_project_id = contribution.get("project") or contribution.get("project_id")

        # 3. Membership Check: Reviewer must be a project member or creator
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
        is_lead = project_data.get("created_by") == user_id

        member_res = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", target_project_id)
            .eq("user_id", user_id)
            .execute()
        )
        is_member = is_lead or (member_res.data and len(member_res.data) > 0)
        if not is_member:
            try:
                role_res = (
                    supabase.table("role_agreements")
                    .select("id")
                    .eq("project_id", target_project_id)
                    .eq("user_id", user_id)
                    .execute()
                )
                if role_res.data and len(role_res.data) > 0:
                    is_member = True
            except Exception:
                pass

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to confirm contributions.",
            )

        # 4. Update contribution status to 'peer-confirmed' and set confirmed_by
        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "verification_status": "peer-confirmed",
            "confirmed_by": user_id,
            "dispute_state": "none",
            "updated_at": now_iso,
        }
        upd_res = (
            supabase.table("contributions")
            .update(update_payload)
            .eq("id", contribution_id)
            .execute()
        )
        updated_contrib = (
            upd_res.data[0]
            if upd_res.data and len(upd_res.data) > 0
            else {**contribution, **update_payload}
        )

        # 5. Update confirmation request status to 'confirmed' if exists
        try:
            supabase.table("confirmation_requests").update({
                "status": "confirmed",
                "updated_at": now_iso,
            }).eq("contribution_id", contribution_id).execute()
        except Exception:
            pass

        # 6. Hydrate contributor profile/name if needed
        cid = updated_contrib.get("contributor")
        try:
            prof_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", cid)
                .single()
                .execute()
            )
            prof_data = prof_res.data or {}
            updated_contrib["contributor_name"] = (
                prof_data.get("display_name")
                or prof_data.get("email")
                or f"User {cid[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        return updated_contrib

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]

            # 1. Self-Action Block
            author_id = contribution.get("contributor") or contribution.get("contributor_id")
            if author_id == user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authors cannot confirm their own contributions.",
                )

            # 2. Membership Check
            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            is_lead = project_data.get("created_by") == user_id
            is_member = is_lead or any(
                m.get("project_id") == target_project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to confirm contributions.",
                )

            # 3. Update in DEV_CONTRIBUTIONS_DB
            now_iso = datetime.now(timezone.utc).isoformat()
            if not contribution.get("created_at"):
                contribution["created_at"] = now_iso
            contribution["verification_status"] = "peer-confirmed"
            contribution["confirmed_by"] = user_id
            contribution["dispute_state"] = "none"
            contribution["updated_at"] = now_iso

            # 4. Update in DEV_CONFIRMATION_REQUESTS_DB
            for r in DEV_CONFIRMATION_REQUESTS_DB:
                if r.get("contribution_id") == contribution_id and (
                    r.get("reviewer_id") == user_id or r.get("status") == "pending"
                ):
                    r["status"] = "confirmed"
                    r["updated_at"] = now_iso

            _save_dev_data()
            return contribution

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to confirm contribution: {err_msg}",
        )


@router.post(
    "/{contribution_id}/dispute",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/dispute/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def dispute_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Peer disputes a teammate's contribution, updating status to 'needs-review', dispute_state to 'disputed', and visibility to 'private'."""
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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Self-Action Block: Author cannot dispute their own contribution
        author_id = contribution.get("contributor") or contribution.get("contributor_id")
        if author_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authors cannot dispute their own contributions.",
            )

        target_project_id = contribution.get("project") or contribution.get("project_id")

        # 3. Membership Check: Caller must be a project member or creator
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
        is_lead = project_data.get("created_by") == user_id

        member_res = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", target_project_id)
            .eq("user_id", user_id)
            .execute()
        )
        is_member = is_lead or (member_res.data and len(member_res.data) > 0)
        if not is_member:
            try:
                role_res = (
                    supabase.table("role_agreements")
                    .select("id")
                    .eq("project_id", target_project_id)
                    .eq("user_id", user_id)
                    .execute()
                )
                if role_res.data and len(role_res.data) > 0:
                    is_member = True
            except Exception:
                pass

        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this project to dispute contributions.",
            )

        # 4. Update contribution: needs-review, disputed, private
        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "verification_status": "needs-review",
            "dispute_state": "disputed",
            "visibility": "private",
            "updated_at": now_iso,
        }
        upd_res = (
            supabase.table("contributions")
            .update(update_payload)
            .eq("id", contribution_id)
            .execute()
        )
        updated_contrib = (
            upd_res.data[0]
            if upd_res.data and len(upd_res.data) > 0
            else {**contribution, **update_payload}
        )

        # 5. Update confirmation request status to 'disputed' if exists
        try:
            supabase.table("confirmation_requests").update({
                "status": "disputed",
                "updated_at": now_iso,
            }).eq("contribution_id", contribution_id).execute()
        except Exception:
            pass

        # 6. Hydrate contributor profile/name if needed
        cid = updated_contrib.get("contributor")
        try:
            prof_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", cid)
                .single()
                .execute()
            )
            prof_data = prof_res.data or {}
            updated_contrib["contributor_name"] = (
                prof_data.get("display_name")
                or prof_data.get("email")
                or f"User {cid[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        return updated_contrib

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]

            # 1. Self-Action Block
            author_id = contribution.get("contributor") or contribution.get("contributor_id")
            if author_id == user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authors cannot dispute their own contributions.",
                )

            # 2. Membership Check
            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            is_lead = project_data.get("created_by") == user_id
            is_member = is_lead or any(
                m.get("project_id") == target_project_id and m.get("user_id") == user_id
                for m in DEV_PROJECT_MEMBERS_DB
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You must be a member of this project to dispute contributions.",
                )

            # 3. Update in DEV_CONTRIBUTIONS_DB
            now_iso = datetime.now(timezone.utc).isoformat()
            if not contribution.get("created_at"):
                contribution["created_at"] = now_iso
            contribution["verification_status"] = "needs-review"
            contribution["dispute_state"] = "disputed"
            contribution["visibility"] = "private"
            contribution["updated_at"] = now_iso

            # 4. Update in DEV_CONFIRMATION_REQUESTS_DB
            for r in DEV_CONFIRMATION_REQUESTS_DB:
                if r.get("contribution_id") == contribution_id and (
                    r.get("reviewer_id") == user_id or r.get("status") == "pending"
                ):
                    r["status"] = "disputed"
                    r["updated_at"] = now_iso

            _save_dev_data()
            return contribution

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to dispute contribution: {err_msg}",
        )


@router.post(
    "/{contribution_id}/publish",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/publish/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def publish_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """
    Publish a confirmed contribution to the public passport, toggling visibility to 'public'.
    Strictly rejects with 400 if verification_status is not 'confirmed' or 'peer-confirmed',
    or if the deliverable is disputed/needs-review.
    """
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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Ownership / Authorization check
        is_author = (
            contribution.get("contributor") == user_id
            or contribution.get("contributor_id") == user_id
        )
        target_project_id = contribution.get("project") or contribution.get("project_id")
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
                detail="You are not authorized to modify this contribution's visibility.",
            )

        # 3. Strict Defense-in-Depth Verification Guard:
        # Only confirmed contributions can ever be made public.
        v_status = contribution.get("verification_status")
        d_state = contribution.get("dispute_state")
        if v_status not in ("confirmed", "peer-confirmed") or d_state == "disputed" or v_status == "needs-review":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only confirmed contributions can be published to your passport.",
            )

        # 4. Update visibility to 'public'
        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "visibility": "public",
            "updated_at": now_iso,
        }
        upd_res = (
            supabase.table("contributions")
            .update(update_payload)
            .eq("id", contribution_id)
            .execute()
        )
        updated_contrib = (
            upd_res.data[0]
            if upd_res.data and len(upd_res.data) > 0
            else {**contribution, **update_payload}
        )

        # 5. Hydrate contributor profile/name if needed
        cid = updated_contrib.get("contributor")
        try:
            prof_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", cid)
                .single()
                .execute()
            )
            prof_data = prof_res.data or {}
            updated_contrib["contributor_name"] = (
                prof_data.get("display_name")
                or prof_data.get("email")
                or f"User {cid[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        return updated_contrib

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]

            # Authorization Check
            is_author = (
                contribution.get("contributor") == user_id
                or contribution.get("contributor_id") == user_id
            )
            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            is_lead = project_data.get("created_by") == user_id
            if not is_author and not is_lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to modify this contribution's visibility.",
                )

            # Strict Guard: Only confirmed deliverables can be made public
            v_status = contribution.get("verification_status")
            d_state = contribution.get("dispute_state")
            if v_status not in ("confirmed", "peer-confirmed") or d_state == "disputed" or v_status == "needs-review":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only confirmed contributions can be published to your passport.",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            if not contribution.get("created_at"):
                contribution["created_at"] = now_iso
            contribution["visibility"] = "public"
            contribution["updated_at"] = now_iso

            cid = contribution.get("contributor")
            if cid and not contribution.get("contributor_name"):
                contribution["contributor_name"] = DEV_USER_NAMES_DB.get(cid, f"User {cid[:8]}")

            _save_dev_data()
            return contribution

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to publish contribution: {err_msg}",
        )


@router.post(
    "/{contribution_id}/unpublish",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/unpublish/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def unpublish_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """
    Unpublish a contribution from the public passport, toggling visibility to 'private'.
    Allows builders to selectively conceal deliverables.
    """
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
            if any(c.get("id") == contribution_id for c in DEV_CONTRIBUTIONS_DB):
                raise Exception("LOCAL DEV FALLBACK: contribution in dev store")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contribution not found.",
            )
        contribution = c_res.data[0]

        # 2. Ownership / Authorization check
        is_author = (
            contribution.get("contributor") == user_id
            or contribution.get("contributor_id") == user_id
        )
        target_project_id = contribution.get("project") or contribution.get("project_id")
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
                detail="You are not authorized to modify this contribution's visibility.",
            )

        # 3. Update visibility to 'private'
        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            "visibility": "private",
            "updated_at": now_iso,
        }
        upd_res = (
            supabase.table("contributions")
            .update(update_payload)
            .eq("id", contribution_id)
            .execute()
        )
        updated_contrib = (
            upd_res.data[0]
            if upd_res.data and len(upd_res.data) > 0
            else {**contribution, **update_payload}
        )

        # 4. Hydrate contributor profile/name if needed
        cid = updated_contrib.get("contributor")
        try:
            prof_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", cid)
                .single()
                .execute()
            )
            prof_data = prof_res.data or {}
            updated_contrib["contributor_name"] = (
                prof_data.get("display_name")
                or prof_data.get("email")
                or f"User {cid[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        return updated_contrib

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            matching = [c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == contribution_id]
            if not matching:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Contribution not found.",
                )
            contribution = matching[0]

            # Authorization Check
            is_author = (
                contribution.get("contributor") == user_id
                or contribution.get("contributor_id") == user_id
            )
            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            is_lead = project_data.get("created_by") == user_id
            if not is_author and not is_lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to modify this contribution's visibility.",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            if not contribution.get("created_at"):
                contribution["created_at"] = now_iso
            contribution["visibility"] = "private"
            contribution["updated_at"] = now_iso

            cid = contribution.get("contributor")
            if cid and not contribution.get("contributor_name"):
                contribution["contributor_name"] = DEV_USER_NAMES_DB.get(cid, f"User {cid[:8]}")

            _save_dev_data()
            return contribution

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to unpublish contribution: {err_msg}",
        )



@router.get(
    "/pending-confirmations",
    response_model=PendingConfirmationsListResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/pending-confirmations/",
    response_model=PendingConfirmationsListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_pending_confirmations(
    current_user: Any = Depends(get_current_user),
):
    """
    Fetch pending confirmation requests where current_user is the assigned reviewer.
    Enriches each record with contribution, project, and contributor details.
    """
    user_id = _get_user_id(current_user)
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("confirmation_requests")
            .select("*")
            .eq("reviewer_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        raw_requests = res.data or []

        contrib_ids = list({r["contribution_id"] for r in raw_requests if r.get("contribution_id")})
        project_ids = list({r["project_id"] for r in raw_requests if r.get("project_id")})
        user_ids = list({r["requested_by"] for r in raw_requests if r.get("requested_by")})

        contrib_map = {}
        if contrib_ids:
            c_res = supabase.table("contributions").select("*").in_("id", contrib_ids).execute()
            for c in (c_res.data or []):
                contrib_map[c["id"]] = c

        project_map = {}
        if project_ids:
            p_res = supabase.table("projects").select("id, name").in_("id", project_ids).execute()
            for p in (p_res.data or []):
                project_map[p["id"]] = p

        profile_map = {}
        if user_ids:
            try:
                u_res = supabase.table("profiles").select("id, display_name, avatar_url").in_("id", user_ids).execute()
                for u in (u_res.data or []):
                    profile_map[u["id"]] = u
            except Exception:
                pass

        enriched_list = []
        for r in raw_requests:
            c_id = r.get("contribution_id")
            p_id = r.get("project_id")
            u_id = r.get("requested_by")

            contrib = contrib_map.get(c_id, {})
            # Ghost Pending Safety: Skip if contribution was deleted or already confirmed/disputed
            if not contrib or contrib.get("verification_status") in ("confirmed", "peer-confirmed", "needs-review", "disputed"):
                continue
            project = project_map.get(p_id, {})
            profile = profile_map.get(u_id, {})

            contrib_resp = None
            if contrib:
                c_copy = dict(contrib)
                if not c_copy.get("created_at"):
                    c_copy["created_at"] = now_iso
                if not c_copy.get("updated_at"):
                    c_copy["updated_at"] = now_iso
                try:
                    contrib_resp = ContributionResponse(**c_copy)
                except Exception:
                    pass

            enriched_list.append(
                ConfirmationRequestResponse(
                    id=r["id"],
                    contribution_id=c_id or "",
                    project_id=p_id or "",
                    requested_by=u_id or "",
                    reviewer_id=r.get("reviewer_id") or user_id,
                    status=r.get("status", "pending"),
                    created_at=r.get("created_at") or now_iso,
                    updated_at=r.get("updated_at") or now_iso,
                    contribution_title=contrib.get("title"),
                    project_name=project.get("name"),
                    contributor_name=profile.get("display_name")
                    or profile.get("email")
                    or contrib.get("contributor_name"),
                    category=contrib.get("category"),
                    description=contrib.get("description"),
                    evidence_link=contrib.get("evidence_link"),
                    contribution=contrib_resp,
                )
            )

        return PendingConfirmationsListResponse(
            total_count=len(enriched_list),
            requests=enriched_list,
        )

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            dev_requests = [
                r
                for r in DEV_CONFIRMATION_REQUESTS_DB
                if r.get("reviewer_id") == user_id
                and r.get("status", "pending") == "pending"
            ]

            enriched_list = []
            for r in dev_requests:
                c_id = r.get("contribution_id")
                contrib = next(
                    (c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == c_id),
                    None,
                )
                # Ghost Pending Safety: Skip if contribution was deleted or already confirmed/disputed
                if not contrib or contrib.get("verification_status") in ("confirmed", "peer-confirmed", "needs-review", "disputed"):
                    continue
                p_id = r.get("project_id") or (
                    contrib.get("project") if contrib else None
                )
                project = DEV_PROJECTS_DB.get(p_id, {})
                u_id = r.get("requested_by") or (
                    contrib.get("contributor") if contrib else None
                )
                contributor_name = DEV_USER_NAMES_DB.get(u_id) if u_id else None
                if not contributor_name and contrib and contrib.get("contributor_name"):
                    contributor_name = contrib.get("contributor_name")
                if not contributor_name and u_id:
                    contributor_name = f"Teammate {u_id}"

                contrib_resp = None
                if contrib:
                    c_copy = dict(contrib)
                    if not c_copy.get("created_at"):
                        c_copy["created_at"] = now_iso
                    if not c_copy.get("updated_at"):
                        c_copy["updated_at"] = now_iso
                    try:
                        contrib_resp = ContributionResponse(**c_copy)
                    except Exception:
                        pass

                enriched_list.append(
                    ConfirmationRequestResponse(
                        id=r["id"],
                        contribution_id=c_id or "",
                        project_id=p_id or "",
                        requested_by=u_id or "",
                        reviewer_id=r.get("reviewer_id") or user_id,
                        status=r.get("status", "pending"),
                        created_at=r.get("created_at") or now_iso,
                        updated_at=r.get("updated_at") or now_iso,
                        contribution_title=contrib.get("title") if contrib else None,
                        project_name=project.get("name") if project else None,
                        contributor_name=contributor_name,
                        category=contrib.get("category") if contrib else None,
                        description=contrib.get("description") if contrib else None,
                        evidence_link=contrib.get("evidence_link") if contrib else None,
                        contribution=contrib_resp,
                    )
                )

            enriched_list.sort(key=lambda x: str(x.created_at), reverse=True)
            return PendingConfirmationsListResponse(
                total_count=len(enriched_list),
                requests=enriched_list,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch pending confirmations: {err_msg}",
        )


@router.get(
    "/passport/{user_id}",
    response_model=UserPassportResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/passport/{user_id}/",
    response_model=UserPassportResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def get_user_passport(
    user_id: str,
):
    """
    Public builder passport query for a user.
    Guarantees that ANY contribution with status 'needs-review', dispute_state 'disputed',
    or visibility 'private' is strictly excluded from the passport.
    """
    try:
        supabase = get_supabase_client()

        # Fetch profile
        profile = {}
        try:
            p_res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
            if p_res.data:
                profile = p_res.data
        except Exception:
            pass

        # Fetch contributions for this user
        c_res = (
            supabase.table("contributions")
            .select("*")
            .eq("contributor", user_id)
            .eq("visibility", "public")
            .neq("verification_status", "needs-review")
            .neq("dispute_state", "disputed")
            .order("created_at", desc=True)
            .execute()
        )
        raw_items = c_res.data or []

        # Strict defense-in-depth filter
        valid_items = [
            c for c in raw_items
            if c.get("verification_status") != "needs-review"
            and c.get("dispute_state") != "disputed"
            and c.get("visibility") == "public"
        ]

        for c in valid_items:
            c["contributor_name"] = profile.get("display_name") or c.get("contributor_name") or f"User {user_id[:8]}"
            c["contributor_profile"] = profile or None

        confirmed_count = sum(1 for c in valid_items if c.get("verification_status") in ("confirmed", "peer-confirmed"))

        return UserPassportResponse(
            user_id=user_id,
            display_name=profile.get("display_name"),
            avatar_url=profile.get("avatar_url"),
            github_username=profile.get("github_username"),
            total_contributions=len(valid_items),
            confirmed_count=confirmed_count,
            contributions=valid_items,
        )

    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            display_name = DEV_USER_NAMES_DB.get(user_id, f"User {user_id[:8]}")

            valid_items = [
                c for c in DEV_CONTRIBUTIONS_DB
                if c.get("contributor") == user_id
                and c.get("verification_status") != "needs-review"
                and c.get("dispute_state") != "disputed"
                and c.get("visibility") == "public"
            ]

            for c in valid_items:
                if not c.get("contributor_name"):
                    c["contributor_name"] = display_name
                if not c.get("contributor_profile"):
                    c["contributor_profile"] = {
                        "user_id": user_id,
                        "display_name": display_name,
                        "email": f"{user_id}@buildcrew.io",
                    }

            confirmed_count = sum(1 for c in valid_items if c.get("verification_status") in ("confirmed", "peer-confirmed"))

            return UserPassportResponse(
                user_id=user_id,
                display_name=display_name,
                avatar_url=None,
                github_username=None,
                total_contributions=len(valid_items),
                confirmed_count=confirmed_count,
                contributions=valid_items,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch user passport: {err_msg}",
        )


@router.get(
    "/passport/{user_id}/{project_id}",
    response_model=ProjectPassportResponse,
    tags=["Passport"],
    summary="Get public project contribution passport",
)
@router.get(
    "/passport/{user_id}/{project_id}/",
    response_model=ProjectPassportResponse,
    tags=["Passport"],
    include_in_schema=False,
)
async def get_project_passport_route(
    user_id: str,
    project_id: str,
):
    return await get_project_passport(user_id, project_id)


def _format_clean_display_name(raw_name: Optional[str], profile: Optional[dict] = None) -> str:
    """
    Format a builder's name cleanly for the public passport and recruiter PDF.
    If only an email address was stored, converts username to clean capitalized name.
    """
    if profile:
        disp_name = profile.get("display_name")
        if disp_name and "@" not in str(disp_name) and len(str(disp_name).strip()) > 1:
            return str(disp_name).strip()
        full_name = profile.get("full_name")
        if full_name and "@" not in str(full_name) and len(str(full_name).strip()) > 1:
            return str(full_name).strip()
        if not raw_name:
            raw_name = disp_name or full_name

    if not raw_name:
        return "Anonymous Builder"
    
    clean = str(raw_name).strip()
    if "@" in clean:
        username = clean.split("@")[0]
        parts = username.replace(".", " ").replace("_", " ").replace("-", " ").split()
        capitalized = [p.capitalize() for p in parts if p]
        if capitalized:
            return " ".join(capitalized)
        return "Builder"
    
    return clean


async def get_project_passport(
    user_id: str,
    project_id: str,
) -> ProjectPassportResponse:
    """
    Public builder passport query for a specific project.
    Strictly returns ONLY published contributions (visibility == 'public')
    and strictly excludes any items with verification_status == 'needs-review'
    or dispute_state == 'disputed'.
    """
    try:
        supabase = get_supabase_client()

        # 1. Fetch user profile
        profile = {}
        try:
            p_res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
            if p_res.data:
                profile = p_res.data
        except Exception:
            pass

        # 2. Fetch project info
        project_name = "Project"
        project_data = {}
        try:
            proj_res = supabase.table("projects").select("*").eq("id", project_id).single().execute()
            if proj_res.data:
                project_data = proj_res.data
                project_name = project_data.get("name") or "Project"
        except Exception:
            pass

        # 3. Fetch role agreement for this user in this project
        role_name = None
        role_category = None
        try:
            r_res = (
                supabase.table("role_agreements")
                .select("*")
                .eq("project_id", project_id)
                .eq("user_id", user_id)
                .execute()
            )
            if r_res.data and len(r_res.data) > 0:
                role_name = r_res.data[0].get("role_name")
                role_category = r_res.data[0].get("category")
        except Exception:
            pass

        if not role_name:
            if project_data.get("created_by") == user_id:
                role_name = "Team Lead"
            else:
                role_name = "Contributor"

        # 4. Fetch published contributions for this user & project
        c_res = (
            supabase.table("contributions")
            .select("*")
            .eq("contributor", user_id)
            .eq("project", project_id)
            .eq("visibility", "public")
            .neq("verification_status", "needs-review")
            .neq("dispute_state", "disputed")
            .order("created_at", desc=True)
            .execute()
        )
        raw_items = c_res.data or []

        # If empty, also check if dev fallback has items (for tests / offline)
        if not raw_items:
            matching_dev = [
                c for c in DEV_CONTRIBUTIONS_DB
                if (c.get("contributor") == user_id or c.get("contributor_id") == user_id)
                and (c.get("project") == project_id or c.get("project_id") == project_id)
                and c.get("visibility") == "public"
                and c.get("verification_status") not in ("needs-review", "self-declared", "draft-pending")
                and c.get("dispute_state") != "disputed"
            ]
            if matching_dev:
                raise Exception("LOCAL DEV FALLBACK: matching contributions in dev store")

        # Strict defense-in-depth filter:
        # Only published items, confirmed, not in needs-review or disputed
        valid_items = [
            c for c in raw_items
            if c.get("verification_status") != "needs-review"
            and c.get("dispute_state") != "disputed"
            and c.get("visibility") == "public"
            and c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified")
        ]

        now_iso = datetime.now(timezone.utc).isoformat()
        display_name = _format_clean_display_name(profile.get("display_name") or profile.get("full_name"), profile)
        for c in valid_items:
            c["contributor_name"] = display_name
            c["contributor_profile"] = profile or None
            if not c.get("created_at"):
                c["created_at"] = now_iso
            if not c.get("updated_at"):
                c["updated_at"] = c.get("created_at") or now_iso

        confirmed_count = sum(
            1 for c in valid_items
            if c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified")
        )

        return ProjectPassportResponse(
            user_id=user_id,
            project_id=project_id,
            project_name=project_name,
            display_name=display_name,
            avatar_url=profile.get("avatar_url"),
            github_username=profile.get("github_username"),
            role=role_name,
            role_category=role_category,
            total_contributions=len(valid_items),
            confirmed_count=confirmed_count,
            contributions=valid_items,
        )

    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            display_name = _format_clean_display_name(DEV_USER_NAMES_DB.get(user_id, f"User {user_id[:8]}"))
            dev_project = DEV_PROJECTS_DB.get(project_id, {})
            project_name = dev_project.get("name", "Project")

            # Look up role
            role_name = None
            role_category = None
            for r in DEV_ROLE_AGREEMENTS_DB:
                if r.get("project_id") == project_id and r.get("user_id") == user_id:
                    role_name = r.get("role_name")
                    role_category = r.get("category")
                    break

            if not role_name:
                if dev_project.get("created_by") == user_id:
                    role_name = "Team Lead"
                else:
                    role_name = "Contributor"

            valid_items = [
                c for c in DEV_CONTRIBUTIONS_DB
                if (c.get("contributor") == user_id or c.get("contributor_id") == user_id)
                and (c.get("project") == project_id or c.get("project_id") == project_id)
                and c.get("visibility") == "public"
                and c.get("verification_status") != "needs-review"
                and c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified")
                and c.get("dispute_state") != "disputed"
            ]

            now_iso = datetime.now(timezone.utc).isoformat()
            for c in valid_items:
                if not c.get("contributor_name"):
                    c["contributor_name"] = display_name
                if not c.get("contributor_profile"):
                    c["contributor_profile"] = {
                        "user_id": user_id,
                        "display_name": display_name,
                        "email": f"{user_id}@buildcrew.io",
                    }
                if not c.get("created_at"):
                    c["created_at"] = now_iso
                if not c.get("updated_at"):
                    c["updated_at"] = c.get("created_at") or now_iso

            confirmed_count = len(valid_items)

            return ProjectPassportResponse(
                user_id=user_id,
                project_id=project_id,
                project_name=project_name,
                display_name=display_name,
                avatar_url=None,
                github_username=None,
                role=role_name,
                role_category=role_category,
                total_contributions=len(valid_items),
                confirmed_count=confirmed_count,
                contributions=valid_items,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch project passport: {err_msg}",
        )


@router.get(
    "/public",
    response_model=PublicContributionsResponse,
    status_code=status.HTTP_200_OK,
)
@router.get(
    "/public/",
    response_model=PublicContributionsResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def list_public_contributions(
    user_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """
    Publicly query contributions stream across projects and builders.
    Strictly excludes any contribution with verification_status == 'needs-review'
    or dispute_state == 'disputed' or visibility != 'public'.
    """
    try:
        supabase = get_supabase_client()
        query = (
            supabase.table("contributions")
            .select("*")
            .eq("visibility", "public")
            .neq("verification_status", "needs-review")
            .neq("dispute_state", "disputed")
        )
        if user_id and user_id.strip():
            query = query.eq("contributor", user_id.strip())
        if project_id and project_id.strip():
            query = query.eq("project", project_id.strip())
        if category and category.strip():
            query = query.eq("category", category.strip().lower())

        c_res = query.order("created_at", desc=True).execute()
        raw_items = c_res.data or []

        valid_items = [
            c for c in raw_items
            if c.get("verification_status") != "needs-review"
            and c.get("dispute_state") != "disputed"
            and c.get("visibility") == "public"
        ]

        contributor_ids = list({c.get("contributor") for c in valid_items if c.get("contributor")})
        profiles_map = {}
        if contributor_ids:
            try:
                p_res = supabase.table("profiles").select("*").in_("id", contributor_ids).execute()
                for p in (p_res.data or []):
                    profiles_map[p.get("id")] = p
            except Exception:
                pass

        for c in valid_items:
            cid = c.get("contributor")
            prof = profiles_map.get(cid) or c.get("profiles") or {}
            c["contributor_name"] = prof.get("display_name") or prof.get("email") or c.get("contributor_name") or (f"User {cid[:8]}" if cid else "Contributor")
            c["contributor_profile"] = prof or None

        return PublicContributionsResponse(
            total_count=len(valid_items),
            contributions=valid_items,
        )

    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            valid_items = [
                c for c in DEV_CONTRIBUTIONS_DB
                if c.get("visibility") == "public"
                and c.get("verification_status") != "needs-review"
                and c.get("dispute_state") != "disputed"
            ]
            if user_id and user_id.strip():
                valid_items = [c for c in valid_items if c.get("contributor") == user_id.strip()]
            if project_id and project_id.strip():
                valid_items = [c for c in valid_items if c.get("project") == project_id.strip()]
            if category and category.strip():
                cat_f = category.strip().lower()
                valid_items = [c for c in valid_items if c.get("category", "").lower() == cat_f]

            for c in valid_items:
                cid = c.get("contributor")
                if cid and not c.get("contributor_profile"):
                    c["contributor_name"] = c.get("contributor_name") or f"Member {cid}"
                    c["contributor_profile"] = {
                        "user_id": cid,
                        "display_name": c["contributor_name"],
                        "email": f"{cid}@buildcrew.io",
                    }

            return PublicContributionsResponse(
                total_count=len(valid_items),
                contributions=valid_items,
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to list public contributions: {err_msg}",
        )





