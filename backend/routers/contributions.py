import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from core.database import get_supabase_client, is_dev_mode
from core.dependencies import get_current_user
from core.logging import logger
from core.errors import handle_route_error
from core.rate_limit import limiter, get_user_key
from routers.auth import DEV_USER_NAMES_DB
from routers.projects import (
    DEV_CONFIRMATION_REQUESTS_DB,
    DEV_CONFIRMATIONS_DB,
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
    ConfirmationVoteInfo,
    ContributionResponse,
    DisputeContributionPayload,
    EvidenceUploadResponse,
    ManualContributionCreate,
    PendingConfirmationsListResponse,
    ProjectPassportResponse,
    PublicContributionsResponse,
    RequestConfirmationPayload,
    UserPassportResponse,
)

router = APIRouter(prefix="/contributions", tags=["Contributions"])


ALLOWED_EVIDENCE_EXTENSIONS = {
    "png", "jpg", "jpeg", "webp", "gif", "pdf", "txt", "md", "docx", "pptx", "xlsx"
}

EXTENSION_MIME_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _format_clean_display_name(raw_name: Optional[str], profile: Optional[dict] = None) -> str:
    """
    Format a builder's name cleanly for the public passport and recruiter PDF.
    If only an email address was stored, converts username to clean capitalized name.
    Never returns raw emails.
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


def _resolve_user_clean_name(user_id: str, supabase: Any = None) -> str:
    """Resolve a clean display name for a given user ID without returning raw emails."""
    if not user_id:
        return "Anonymous Builder"
    profile_data = {}
    if supabase is not None:
        try:
            p_res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            if p_res.data:
                profile_data = p_res.data
        except Exception:
            pass
    raw_name = profile_data.get("display_name") or profile_data.get("full_name")
    if not raw_name:
        raw_name = DEV_USER_NAMES_DB.get(user_id)
        if not raw_name:
            for email, name in DEV_USER_NAMES_DB.items():
                if email.lower() == str(user_id).lower():
                    raw_name = name
                    break
    if not raw_name:
        raw_name = profile_data.get("email") or f"User {str(user_id)[:8]}"
    return _format_clean_display_name(raw_name, profile_data)


def _get_project_member_ids(project_id: Optional[str], supabase: Any = None) -> set[str]:
    """Return all valid current member IDs for a project (members + creator)."""
    if not project_id:
        return set()
    member_ids = set()
    if supabase is not None:
        try:
            p_res = (
                supabase.table("projects")
                .select("created_by")
                .eq("id", project_id)
                .single()
                .execute()
            )
            if p_res.data and p_res.data.get("created_by"):
                member_ids.add(str(p_res.data.get("created_by")))
            m_res = (
                supabase.table("project_members")
                .select("user_id")
                .eq("project_id", project_id)
                .execute()
            )
            for m in (m_res.data or []):
                if m.get("user_id"):
                    member_ids.add(str(m.get("user_id")))
        except Exception:
            pass

    if not member_ids:
        dev_proj = DEV_PROJECTS_DB.get(project_id, {})
        if dev_proj.get("created_by"):
            member_ids.add(str(dev_proj.get("created_by")))
        for m in DEV_PROJECT_MEMBERS_DB:
            if m.get("project_id") == project_id and m.get("user_id"):
                member_ids.add(str(m.get("user_id")))
    return member_ids


def _get_contribution_votes(contribution_id: str, supabase: Any = None) -> list[dict]:
    """Retrieve all confirmation/dispute votes for a contribution from Supabase or Dev store."""
    all_votes = []
    loaded_from_supabase = False
    if supabase is not None:
        try:
            v_res = (
                supabase.table("confirmations")
                .select("*")
                .eq("contribution_id", contribution_id)
                .order("confirmed_at", desc=False)
                .execute()
            )
            all_votes = v_res.data or []
            loaded_from_supabase = True
        except Exception:
            pass

    if not loaded_from_supabase or (not all_votes and is_dev_mode()):
        dev_votes = [v for v in DEV_CONFIRMATIONS_DB if v.get("contribution_id") == contribution_id]
        if dev_votes:
            all_votes = dev_votes
    return all_votes


def _recompute_contribution_status(supabase: Any, contribution: dict) -> dict:
    """
    Recompute contribution verification status based on standing votes:
    1. Keep only votes whose voter is a CURRENT member (project_members or created_by) and NOT the author.
    2. If any valid vote is 'dispute':
       verification_status='needs-review', dispute_state='disputed', visibility='private'.
    3. Elif >=1 valid 'confirm':
       dispute_state='none',
       verification_status='source-verified' if source_type starts with 'github' else 'peer-confirmed',
       confirmed_by=latest confirmer.
    4. Else:
       dispute_state='none',
       verification_status='source-verified' if source_type starts with 'github' else 'self-declared'.
    Never turns 'source-verified' into 'peer-confirmed'.
    Persists only on change.
    """
    contrib_id = contribution.get("id")
    target_project_id = contribution.get("project") or contribution.get("project_id")
    author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")

    current_member_ids = _get_project_member_ids(target_project_id, supabase)
    all_votes = _get_contribution_votes(contrib_id, supabase)

    valid_votes = [
        v for v in all_votes
        if str(v.get("confirmed_by_user_id")) in current_member_ids
        and str(v.get("confirmed_by_user_id")) != author_id
    ]

    dispute_votes = [v for v in valid_votes if v.get("action") == "dispute"]
    confirm_votes = [v for v in valid_votes if v.get("action") == "confirm"]

    source_type = str(contribution.get("source_type") or "").strip().lower()
    current_status = contribution.get("verification_status")
    is_github_source = source_type.startswith("github")
    was_source_verified = (current_status == "source-verified") or is_github_source

    if dispute_votes:
        new_status = "needs-review"
        new_dispute_state = "disputed"
        new_visibility = "private"
        new_confirmed_by = contribution.get("confirmed_by")
    elif confirm_votes:
        new_dispute_state = "none"
        new_status = "source-verified" if was_source_verified else "peer-confirmed"
        sorted_confirms = sorted(confirm_votes, key=lambda v: str(v.get("confirmed_at") or ""))
        new_confirmed_by = sorted_confirms[-1].get("confirmed_by_user_id")
        new_visibility = contribution.get("visibility") or "private"
    else:
        new_dispute_state = "none"
        new_status = "source-verified" if was_source_verified else "self-declared"
        new_confirmed_by = None
        new_visibility = contribution.get("visibility") or "private"

    has_changed = (
        contribution.get("verification_status") != new_status
        or contribution.get("dispute_state") != new_dispute_state
        or contribution.get("visibility") != new_visibility
        or contribution.get("confirmed_by") != new_confirmed_by
    )

    if has_changed:
        now_iso = datetime.now(timezone.utc).isoformat()
        contribution["verification_status"] = new_status
        contribution["dispute_state"] = new_dispute_state
        contribution["visibility"] = new_visibility
        contribution["confirmed_by"] = new_confirmed_by
        contribution["updated_at"] = now_iso

        if supabase is not None:
            try:
                supabase.table("contributions").update({
                    "verification_status": new_status,
                    "dispute_state": new_dispute_state,
                    "visibility": new_visibility,
                    "confirmed_by": new_confirmed_by,
                    "updated_at": now_iso,
                }).eq("id", contrib_id).execute()
            except Exception:
                pass

        for dev_c in DEV_CONTRIBUTIONS_DB:
            if dev_c.get("id") == contrib_id:
                dev_c["verification_status"] = new_status
                dev_c["dispute_state"] = new_dispute_state
                dev_c["visibility"] = new_visibility
                dev_c["confirmed_by"] = new_confirmed_by
                dev_c["updated_at"] = now_iso
                break
        _save_dev_data()

    return contribution


def _enrich_contribution_metadata(
    contribution: dict,
    caller_user_id: Optional[str] = None,
    supabase: Any = None,
    is_public_passport: bool = False,
) -> dict:
    """Enrich a contribution dict with confirmations [{name, at}], confirm_count, team_size, and restricted dispute info."""
    contrib_id = contribution.get("id")
    target_project_id = contribution.get("project") or contribution.get("project_id")
    author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")

    current_member_ids = _get_project_member_ids(target_project_id, supabase)
    all_votes = _get_contribution_votes(contrib_id, supabase)

    valid_votes = [
        v for v in all_votes
        if str(v.get("confirmed_by_user_id")) in current_member_ids
        and str(v.get("confirmed_by_user_id")) != author_id
    ]

    valid_confirms = [v for v in valid_votes if v.get("action") == "confirm"]
    valid_disputes = [v for v in valid_votes if v.get("action") == "dispute"]

    sorted_confirms = sorted(valid_confirms, key=lambda v: str(v.get("confirmed_at") or ""))
    confirmations_list = []
    for cv in sorted_confirms:
        voter_id = str(cv.get("confirmed_by_user_id"))
        clean_name = _resolve_user_clean_name(voter_id, supabase)
        confirmations_list.append({
            "name": clean_name,
            "at": cv.get("confirmed_at") or datetime.now(timezone.utc).isoformat(),
        })

    contribution["confirmations"] = confirmations_list
    contribution["confirm_count"] = len(confirmations_list)
    contribution["team_size"] = len(current_member_ids)

    if not is_public_passport and valid_disputes:
        latest_dispute = sorted(valid_disputes, key=lambda v: str(v.get("confirmed_at") or ""))[-1]
        disputer_id = str(latest_dispute.get("confirmed_by_user_id"))
        if caller_user_id and (str(caller_user_id) == author_id or str(caller_user_id) == disputer_id):
            contribution["disputed_by_name"] = _resolve_user_clean_name(disputer_id, supabase)
            contribution["dispute_reason"] = latest_dispute.get("notes")
        else:
            contribution["disputed_by_name"] = None
            contribution["dispute_reason"] = None
    else:
        contribution["disputed_by_name"] = None
        contribution["dispute_reason"] = None

    is_disputed_status = bool(
        contribution.get("verification_status") in ("needs-review", "disputed")
        or contribution.get("dispute_state") == "disputed"
    )
    is_orphaned = is_disputed_status and (len(valid_disputes) == 0)
    contribution["is_dispute_orphaned"] = is_orphaned
    contribution["can_reopen"] = is_orphaned and bool(caller_user_id and str(caller_user_id) == author_id)

    return contribution


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
@limiter.limit("20/hour", key_func=get_user_key)
async def upload_evidence_file(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    current_user: Any = Depends(get_current_user),
):
    """Upload evidence file to Supabase Storage with local dev fallback.
    
    Reads in 1MB chunks and aborts with 413 if 25MB is exceeded.
    Validates extension against allowed list (415 if invalid).
    Determines content-type server-side from extension, ignoring client header.
    Never falls back to local disk outside development mode.
    """
    user_id = _get_user_id(current_user)

    if not project_id:
        project_id = request.query_params.get("project_id")

    if project_id:
        from routers.projects import is_project_archived
        if is_project_archived(project_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project is archived.",
            )

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file was uploaded.",
        )

    raw_filename = os.path.basename(file.filename)
    if not raw_filename or "." not in raw_filename:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file extension. Allowed extensions: png, jpg, jpeg, webp, gif, pdf, txt, md, docx, pptx, xlsx",
        )

    ext = raw_filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EVIDENCE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file extension '.{ext}'. Allowed extensions: png, jpg, jpeg, webp, gif, pdf, txt, md, docx, pptx, xlsx",
        )

    # Content-type determined server-side from extension, ignoring client-sent value
    content_type = (
        EXTENSION_MIME_TYPES.get(ext)
        or mimetypes.guess_type(raw_filename)[0]
        or "application/octet-stream"
    )

    # Read the upload in 1 MB chunks and abort with 413 once 25 MB is exceeded
    CHUNK_SIZE = 1024 * 1024  # 1 MB
    MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
                detail="File size exceeds maximum limit of 25MB.",
            )
        chunks.append(chunk)

    if total_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    file_bytes = b"".join(chunks)

    # Clean filename
    clean_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", raw_filename)
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
            "size_bytes": total_size,
            "storage_path": storage_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg, service_name="Storage"):
            # Local Dev Fallback (only reached if is_dev_mode() is True)
            upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads", "evidence", user_id)
            os.makedirs(upload_dir, exist_ok=True)
            saved_filename = f"{unique_prefix}_{clean_filename}"
            saved_filepath = os.path.join(upload_dir, saved_filename)
            with open(saved_filepath, "wb") as f:
                f.write(file_bytes)

            local_url = f"http://localhost:8000/static/evidence/{user_id}/{saved_filename}"
            return {
                "url": local_url,
                "filename": clean_filename,
                "file_type": content_type,
                "size_bytes": total_size,
                "storage_path": f"evidence/{user_id}/{saved_filename}",
            }

        if not is_dev_mode():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service unavailable",
            )

        raise handle_route_error(
            e,
            generic_message="Failed to upload evidence file. Please try again.",
            log_message="Failed to upload evidence file",
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

    from routers.projects import is_project_archived
    if is_project_archived(target_project_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is archived.",
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

        raise handle_route_error(
            e,
            generic_message="Failed to create contribution. Please try again.",
            log_message="Failed to create contribution",
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

        raise handle_route_error(
            e,
            generic_message="Failed to delete contribution. Please try again.",
            log_message="Failed to delete contribution",
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
    payload: Optional[RequestConfirmationPayload] = None,
    current_user: Any = Depends(get_current_user),
):
    """Request peer confirmation from project teammates for a logged deliverable."""
    user_id = _get_user_id(current_user)

    raw_reviewer_ids = []
    if payload and payload.reviewer_ids:
        raw_reviewer_ids = list(dict.fromkeys(r.strip() for r in payload.reviewer_ids if r and r.strip()))

    if user_id in raw_reviewer_ids:
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
        from routers.projects import is_project_archived
        if project_data.get("archived_at") or is_project_archived(target_project_id, supabase):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Project is archived.",
            )

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

        if raw_reviewer_ids:
            reviewer_ids = raw_reviewer_ids
            for rev_id in reviewer_ids:
                if rev_id not in valid_member_ids:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Reviewer '{rev_id}' is not a verified member of this project.",
                    )
        else:
            reviewer_ids = [m for m in valid_member_ids if m != user_id]
            if not reviewer_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No other teammates available in the project to review.",
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

            target_project_id = contribution.get("project") or contribution.get("project_id")
            project_data = DEV_PROJECTS_DB.get(target_project_id, {})
            if project_data.get("archived_at"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Project is archived.",
                )
            valid_member_ids = {
                m.get("user_id")
                for m in DEV_PROJECT_MEMBERS_DB
                if m.get("project_id") == target_project_id and m.get("user_id")
            }
            if project_data.get("created_by"):
                valid_member_ids.add(project_data.get("created_by"))

            if raw_reviewer_ids:
                reviewer_ids = raw_reviewer_ids
                for rev_id in reviewer_ids:
                    if rev_id not in valid_member_ids:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Reviewer '{rev_id}' is not a verified member of this project.",
                        )
            else:
                reviewer_ids = [m for m in valid_member_ids if m != user_id]
                if not reviewer_ids:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No other teammates available in the project to review.",
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

        raise handle_route_error(
            e,
            generic_message="Failed to request confirmation. Please try again.",
            log_message="Failed to request confirmation",
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
    """Peer confirms a teammate's contribution, recording a confirmation vote and recomputing status."""
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
        author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
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

        # 4. Check for active dispute from ANOTHER member
        current_member_ids = _get_project_member_ids(target_project_id, supabase)
        all_votes = _get_contribution_votes(contribution_id, supabase)
        dispute_votes_from_others = [
            v for v in all_votes
            if v.get("action") == "dispute"
            and str(v.get("confirmed_by_user_id")) != user_id
            and str(v.get("confirmed_by_user_id")) in current_member_ids
            and str(v.get("confirmed_by_user_id")) != author_id
        ]
        if dispute_votes_from_others:
            disputer_id = str(dispute_votes_from_others[0].get("confirmed_by_user_id"))
            disputer_name = _resolve_user_clean_name(disputer_id, supabase)
            _recompute_contribution_status(supabase, contribution)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This item is disputed by {disputer_name}. They need to withdraw their dispute first.",
            )

        # 5. Upsert caller's confirm vote
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            supabase.table("confirmations").upsert({
                "contribution_id": contribution_id,
                "confirmed_by_user_id": user_id,
                "action": "confirm",
                "confirmed_at": now_iso,
                "notes": None,
            }, on_conflict="contribution_id,confirmed_by_user_id").execute()
        except Exception as up_err:
            if _is_dev_fallback_error(str(up_err)):
                raise
            pass

        found_dev = False
        for dv in DEV_CONFIRMATIONS_DB:
            if dv.get("contribution_id") == contribution_id and str(dv.get("confirmed_by_user_id")) == user_id:
                dv["action"] = "confirm"
                dv["confirmed_at"] = now_iso
                dv["notes"] = None
                found_dev = True
                break
        if not found_dev:
            DEV_CONFIRMATIONS_DB.append({
                "id": str(uuid.uuid4()),
                "contribution_id": contribution_id,
                "confirmed_by_user_id": user_id,
                "action": "confirm",
                "confirmed_at": now_iso,
                "notes": None,
            })
        _save_dev_data()

        # 6. Recompute status
        updated_contrib = _recompute_contribution_status(supabase, contribution)

        # 7. Update confirmation request status to 'confirmed' if exists
        try:
            supabase.table("confirmation_requests").update({
                "status": "confirmed",
                "updated_at": now_iso,
            }).eq("contribution_id", contribution_id).execute()
        except Exception:
            pass
        for r in DEV_CONFIRMATION_REQUESTS_DB:
            if r.get("contribution_id") == contribution_id and (
                r.get("reviewer_id") == user_id or r.get("status") == "pending"
            ):
                r["status"] = "confirmed"
                r["updated_at"] = now_iso

        # 8. Hydrate contributor profile/name
        cid = updated_contrib.get("contributor") or updated_contrib.get("contributor_id")
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
                or f"User {str(cid)[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=supabase)
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
            author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
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

            # 3. Check for active dispute from ANOTHER member
            current_member_ids = _get_project_member_ids(target_project_id, None)
            all_votes = _get_contribution_votes(contribution_id, None)
            dispute_votes_from_others = [
                v for v in all_votes
                if v.get("action") == "dispute"
                and str(v.get("confirmed_by_user_id")) != user_id
                and str(v.get("confirmed_by_user_id")) in current_member_ids
                and str(v.get("confirmed_by_user_id")) != author_id
            ]
            if dispute_votes_from_others:
                disputer_id = str(dispute_votes_from_others[0].get("confirmed_by_user_id"))
                disputer_name = _resolve_user_clean_name(disputer_id, None)
                _recompute_contribution_status(None, contribution)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"This item is disputed by {disputer_name}. They need to withdraw their dispute first.",
                )

            # 4. Upsert caller's confirm vote in DEV_CONFIRMATIONS_DB
            now_iso = datetime.now(timezone.utc).isoformat()
            found_dev = False
            for dv in DEV_CONFIRMATIONS_DB:
                if dv.get("contribution_id") == contribution_id and str(dv.get("confirmed_by_user_id")) == user_id:
                    dv["action"] = "confirm"
                    dv["confirmed_at"] = now_iso
                    dv["notes"] = None
                    found_dev = True
                    break
            if not found_dev:
                DEV_CONFIRMATIONS_DB.append({
                    "id": str(uuid.uuid4()),
                    "contribution_id": contribution_id,
                    "confirmed_by_user_id": user_id,
                    "action": "confirm",
                    "confirmed_at": now_iso,
                    "notes": None,
                })

            # 5. Recompute status
            updated_contrib = _recompute_contribution_status(None, contribution)

            # 6. Update in DEV_CONFIRMATION_REQUESTS_DB
            for r in DEV_CONFIRMATION_REQUESTS_DB:
                if r.get("contribution_id") == contribution_id and (
                    r.get("reviewer_id") == user_id or r.get("status") == "pending"
                ):
                    r["status"] = "confirmed"
                    r["updated_at"] = now_iso

            _save_dev_data()
            _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=None)
            return updated_contrib

        raise handle_route_error(
            e,
            generic_message="Failed to confirm contribution. Please try again.",
            log_message="Failed to confirm contribution",
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
    payload: Optional[DisputeContributionPayload] = None,
    current_user: Any = Depends(get_current_user),
):
    """Peer disputes a teammate's contribution, recording a dispute vote, setting needs-review, and making it private."""
    user_id = _get_user_id(current_user)

    reason = None
    if payload and payload.reason is not None:
        reason = payload.reason.strip()
        if len(reason) > 280:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dispute reason cannot exceed 280 characters.",
            )
        if not reason:
            reason = None

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
        author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
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

        # 4. Upsert caller's dispute vote
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            supabase.table("confirmations").upsert({
                "contribution_id": contribution_id,
                "confirmed_by_user_id": user_id,
                "action": "dispute",
                "confirmed_at": now_iso,
                "notes": reason,
            }, on_conflict="contribution_id,confirmed_by_user_id").execute()
        except Exception as up_err:
            if _is_dev_fallback_error(str(up_err)):
                raise
            pass

        found_dev = False
        for dv in DEV_CONFIRMATIONS_DB:
            if dv.get("contribution_id") == contribution_id and str(dv.get("confirmed_by_user_id")) == user_id:
                dv["action"] = "dispute"
                dv["confirmed_at"] = now_iso
                dv["notes"] = reason
                found_dev = True
                break
        if not found_dev:
            DEV_CONFIRMATIONS_DB.append({
                "id": str(uuid.uuid4()),
                "contribution_id": contribution_id,
                "confirmed_by_user_id": user_id,
                "action": "dispute",
                "confirmed_at": now_iso,
                "notes": reason,
            })
        _save_dev_data()

        # 5. Recompute status: sets needs-review, disputed, private immediately
        updated_contrib = _recompute_contribution_status(supabase, contribution)

        # 6. Update confirmation request status to 'disputed' if exists
        try:
            supabase.table("confirmation_requests").update({
                "status": "disputed",
                "updated_at": now_iso,
            }).eq("contribution_id", contribution_id).execute()
        except Exception:
            pass
        for r in DEV_CONFIRMATION_REQUESTS_DB:
            if r.get("contribution_id") == contribution_id and (
                r.get("reviewer_id") == user_id or r.get("status") == "pending"
            ):
                r["status"] = "disputed"
                r["updated_at"] = now_iso

        # 7. Hydrate contributor profile/name
        cid = updated_contrib.get("contributor") or updated_contrib.get("contributor_id")
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
                or f"User {str(cid)[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=supabase)
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
            author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
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

            # 3. Upsert caller's dispute vote in DEV_CONFIRMATIONS_DB
            now_iso = datetime.now(timezone.utc).isoformat()
            found_dev = False
            for dv in DEV_CONFIRMATIONS_DB:
                if dv.get("contribution_id") == contribution_id and str(dv.get("confirmed_by_user_id")) == user_id:
                    dv["action"] = "dispute"
                    dv["confirmed_at"] = now_iso
                    dv["notes"] = reason
                    found_dev = True
                    break
            if not found_dev:
                DEV_CONFIRMATIONS_DB.append({
                    "id": str(uuid.uuid4()),
                    "contribution_id": contribution_id,
                    "confirmed_by_user_id": user_id,
                    "action": "dispute",
                    "confirmed_at": now_iso,
                    "notes": reason,
                })

            # 4. Recompute status
            updated_contrib = _recompute_contribution_status(None, contribution)

            # 5. Update in DEV_CONFIRMATION_REQUESTS_DB
            for r in DEV_CONFIRMATION_REQUESTS_DB:
                if r.get("contribution_id") == contribution_id and (
                    r.get("reviewer_id") == user_id or r.get("status") == "pending"
                ):
                    r["status"] = "disputed"
                    r["updated_at"] = now_iso

            _save_dev_data()
            _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=None)
            return updated_contrib

        raise handle_route_error(
            e,
            generic_message="Failed to dispute contribution. Please try again.",
            log_message="Failed to dispute contribution",
        )


@router.post(
    "/{contribution_id}/withdraw-dispute",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/withdraw-dispute/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def withdraw_dispute(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Withdraw a peer dispute on a contribution. Only the member who submitted the dispute can withdraw it."""
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

        # 2. Check if caller has an active dispute vote
        all_votes = _get_contribution_votes(contribution_id, supabase)
        caller_dispute_votes = [
            v for v in all_votes
            if str(v.get("confirmed_by_user_id")) == user_id
            and v.get("action") == "dispute"
        ]
        if not caller_dispute_votes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the member whose dispute vote exists can withdraw the dispute.",
            )

        # 3. Delete that vote
        try:
            supabase.table("confirmations").delete().eq("contribution_id", contribution_id).eq("confirmed_by_user_id", user_id).execute()
        except Exception as del_err:
            if _is_dev_fallback_error(str(del_err)):
                raise
            pass

        DEV_CONFIRMATIONS_DB[:] = [
            v for v in DEV_CONFIRMATIONS_DB
            if not (v.get("contribution_id") == contribution_id and str(v.get("confirmed_by_user_id")) == user_id)
        ]
        for r in DEV_CONFIRMATION_REQUESTS_DB:
            if r.get("contribution_id") == contribution_id and str(r.get("reviewer_id")) == user_id:
                r["status"] = "pending"
                r["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            supabase.table("confirmation_requests").update({"status": "pending"}).eq("contribution_id", contribution_id).eq("reviewer_id", user_id).execute()
        except Exception:
            pass
        _save_dev_data()

        # 4. Recompute status
        updated_contrib = _recompute_contribution_status(supabase, contribution)

        # 5. Hydrate profile
        cid = updated_contrib.get("contributor") or updated_contrib.get("contributor_id")
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
                or f"User {str(cid)[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=supabase)
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

            caller_dispute_votes = [
                v for v in DEV_CONFIRMATIONS_DB
                if v.get("contribution_id") == contribution_id
                and str(v.get("confirmed_by_user_id")) == user_id
                and v.get("action") == "dispute"
            ]
            if not caller_dispute_votes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the member whose dispute vote exists can withdraw the dispute.",
                )

            DEV_CONFIRMATIONS_DB[:] = [
                v for v in DEV_CONFIRMATIONS_DB
                if not (v.get("contribution_id") == contribution_id and str(v.get("confirmed_by_user_id")) == user_id)
            ]
            for r in DEV_CONFIRMATION_REQUESTS_DB:
                if r.get("contribution_id") == contribution_id and str(r.get("reviewer_id")) == user_id:
                    r["status"] = "pending"
                    r["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_dev_data()

            updated_contrib = _recompute_contribution_status(None, contribution)
            _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=None)
            return updated_contrib

        raise handle_route_error(
            e,
            generic_message="Failed to withdraw dispute. Please try again.",
            log_message="Failed to withdraw dispute",
        )


@router.post(
    "/{contribution_id}/reopen",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/{contribution_id}/reopen/",
    response_model=ContributionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def reopen_contribution(
    contribution_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Author reopens a disputed contribution when no valid dispute votes remain from current team members."""
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

        # 2. Author check
        author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
        if author_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author can reopen a disputed contribution.",
            )

        target_project_id = contribution.get("project") or contribution.get("project_id")

        # 3. Check if any valid dispute vote remains from a CURRENT member
        current_member_ids = _get_project_member_ids(target_project_id, supabase)
        all_votes = _get_contribution_votes(contribution_id, supabase)
        active_disputes = [
            v for v in all_votes
            if v.get("action") == "dispute"
            and str(v.get("confirmed_by_user_id")) in current_member_ids
            and str(v.get("confirmed_by_user_id")) != author_id
        ]
        if active_disputes:
            disputer_id = str(active_disputes[0].get("confirmed_by_user_id"))
            disputer_name = _resolve_user_clean_name(disputer_id, supabase)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reopen: active dispute from {disputer_name} still exists.",
            )

        # 4. Recompute status
        updated_contrib = _recompute_contribution_status(supabase, contribution)

        # 5. Hydrate profile
        cid = updated_contrib.get("contributor") or updated_contrib.get("contributor_id")
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
                or f"User {str(cid)[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=supabase)
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

            author_id = str(contribution.get("contributor") or contribution.get("contributor_id") or "")
            if author_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the author can reopen a disputed contribution.",
                )

            target_project_id = contribution.get("project") or contribution.get("project_id")
            current_member_ids = _get_project_member_ids(target_project_id, None)
            all_votes = _get_contribution_votes(contribution_id, None)
            active_disputes = [
                v for v in all_votes
                if v.get("action") == "dispute"
                and str(v.get("confirmed_by_user_id")) in current_member_ids
                and str(v.get("confirmed_by_user_id")) != author_id
            ]
            if active_disputes:
                disputer_id = str(active_disputes[0].get("confirmed_by_user_id"))
                disputer_name = _resolve_user_clean_name(disputer_id, None)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cannot reopen: active dispute from {disputer_name} still exists.",
                )

            updated_contrib = _recompute_contribution_status(None, contribution)
            _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=None)
            return updated_contrib

        raise handle_route_error(
            e,
            generic_message="Failed to reopen contribution. Please try again.",
            log_message="Failed to reopen contribution",
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
        # Only confirmed or source-verified contributions can ever be made public.
        v_status = contribution.get("verification_status")
        d_state = contribution.get("dispute_state")
        if v_status not in ("peer-confirmed", "confirmed", "source-verified") or d_state == "disputed" or v_status == "needs-review":
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
        cid = updated_contrib.get("contributor") or updated_contrib.get("contributor_id")
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
                or f"User {str(cid)[:8]}"
            )
            updated_contrib["contributor_profile"] = prof_data
        except Exception:
            pass

        _enrich_contribution_metadata(updated_contrib, caller_user_id=user_id, supabase=supabase)
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

            # Strict Guard: Only confirmed or source-verified deliverables can be made public
            v_status = contribution.get("verification_status")
            d_state = contribution.get("dispute_state")
            if v_status not in ("peer-confirmed", "confirmed", "source-verified") or d_state == "disputed" or v_status == "needs-review":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only confirmed contributions can be published to your passport.",
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            if not contribution.get("created_at"):
                contribution["created_at"] = now_iso
            contribution["visibility"] = "public"
            contribution["updated_at"] = now_iso

            cid = contribution.get("contributor") or contribution.get("contributor_id")
            if cid and not contribution.get("contributor_name"):
                contribution["contributor_name"] = DEV_USER_NAMES_DB.get(cid, f"User {str(cid)[:8]}")

            _save_dev_data()
            _enrich_contribution_metadata(contribution, caller_user_id=user_id, supabase=None)
            return contribution

        raise handle_route_error(
            e,
            generic_message="Failed to publish contribution. Please try again.",
            log_message="Failed to publish contribution",
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

        raise handle_route_error(
            e,
            generic_message="Failed to unpublish contribution. Please try again.",
            log_message="Failed to unpublish contribution",
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
            .in_("status", ["pending", "disputed"])
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
            # Ghost Pending Safety: Skip if contribution was deleted or already confirmed
            if not contrib or contrib.get("verification_status") in ("confirmed", "peer-confirmed"):
                continue
            # For disputed/needs-review items, only include if current reviewer has an active dispute
            if contrib.get("verification_status") in ("needs-review", "disputed") and r.get("status") != "disputed":
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
                and r.get("status", "pending") in ("pending", "disputed")
            ]

            enriched_list = []
            for r in dev_requests:
                c_id = r.get("contribution_id")
                contrib = next(
                    (c for c in DEV_CONTRIBUTIONS_DB if c.get("id") == c_id),
                    None,
                )
                if not contrib or contrib.get("verification_status") in ("confirmed", "peer-confirmed"):
                    continue
                if contrib.get("verification_status") in ("needs-review", "disputed") and r.get("status") != "disputed":
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

        raise handle_route_error(
            e,
            generic_message="Failed to fetch pending confirmations. Please try again.",
            log_message="Failed to fetch pending confirmations",
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
            _enrich_contribution_metadata(c, caller_user_id=None, supabase=supabase, is_public_passport=True)

        confirmed_count = sum(1 for c in valid_items if c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified"))

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
                _enrich_contribution_metadata(c, caller_user_id=None, supabase=None, is_public_passport=True)

            confirmed_count = sum(1 for c in valid_items if c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified"))

            return UserPassportResponse(
                user_id=user_id,
                display_name=display_name,
                avatar_url=None,
                github_username=None,
                total_contributions=len(valid_items),
                confirmed_count=confirmed_count,
                contributions=valid_items,
            )

        raise handle_route_error(
            e,
            generic_message="Failed to fetch user passport. Please try again.",
            log_message="Failed to fetch user passport",
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


async def get_project_passport(
    user_id: str,
    project_id: str,
) -> ProjectPassportResponse:
    """
    Public builder passport query for a specific project.
    Strictly returns ONLY published contributions (visibility == 'public')
    and strictly excludes any items with verification_status == 'needs-review'
    or dispute_state == 'disputed'.
    Collapses raw GitHub commits into ONE summary row, lists merged PRs and manual
    items individually, and computes confirmed_count strictly over merged PRs + manual items.
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
        proj_res = supabase.table("projects").select("*").eq("id", project_id).single().execute()
        if not proj_res.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Passport not found",
            )
        project_data = proj_res.data
        project_name = project_data.get("name") or "Project"
        project_description = project_data.get("description") or ""
        is_archived = bool(project_data.get("archived_at"))
        archived_at = project_data.get("archived_at")

        # 3. Fetch team size
        member_uids = set()
        try:
            m_res = supabase.table("project_members").select("user_id").eq("project_id", project_id).execute()
            for m in (m_res.data or []):
                if m.get("user_id"):
                    member_uids.add(m["user_id"])
        except Exception:
            pass
        if project_data.get("created_by"):
            member_uids.add(project_data["created_by"])
        team_size = max(len(member_uids), 1)

        # 4. Fetch linked repository
        repo_full_name = None
        try:
            inst_res = supabase.table("github_installations").select("repo_full_name").eq("project_id", project_id).execute()
            if inst_res.data and len(inst_res.data) > 0:
                repo_full_name = inst_res.data[0].get("repo_full_name")
        except Exception:
            pass
        if not repo_full_name:
            repo_full_name = project_data.get("github_repo")

        if repo_full_name:
            clean_repo = repo_full_name.replace("https://github.com/", "").replace("http://github.com/", "").strip("/")
            repository = clean_repo
            repository_url = f"https://github.com/{clean_repo}"
        else:
            repository = None
            repository_url = None

        # 5. Fetch verified GitHub username
        from routers.projects import _verified_github_logins
        verified_map = _verified_github_logins([{"user_id": user_id}], supabase)
        gh_user = None
        for k, v in verified_map.items():
            if v == user_id:
                gh_user = k
                break
        github_username = gh_user or profile.get("github_username")

        # 6. Fetch role agreement for this user in this project
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

        # 7. Fetch published contributions for this user & project
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

        # If empty, check if dev fallback has items
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

        valid_items = [
            c for c in raw_items
            if c.get("verification_status") != "needs-review"
            and c.get("dispute_state") != "disputed"
            and c.get("visibility") == "public"
            and c.get("verification_status") in ("confirmed", "peer-confirmed", "source-verified")
        ]

        # 8. Fetch confirm votes from confirmations table (D1)
        confirmations_map = {}
        all_confirmer_uids = set()
        item_ids = [c["id"] for c in valid_items if c.get("id")]
        if item_ids:
            try:
                v_res = (
                    supabase.table("confirmations")
                    .select("contribution_id, confirmed_by_user_id, action, confirmed_at")
                    .in_("contribution_id", item_ids)
                    .eq("action", "confirm")
                    .execute()
                )
                for v in (v_res.data or []):
                    cid = v.get("contribution_id")
                    cb = v.get("confirmed_by_user_id")
                    if cid and cb:
                        confirmations_map.setdefault(cid, []).append({
                            "confirmed_by": cb,
                            "confirmed_at": v.get("confirmed_at"),
                        })
                        all_confirmer_uids.add(cb)
            except Exception:
                pass

        for c in valid_items:
            cb = c.get("confirmed_by")
            if cb and c.get("id") not in confirmations_map:
                confirmations_map[c["id"]] = [{"confirmed_by": cb, "confirmed_at": c.get("created_at")}]
                all_confirmer_uids.add(cb)

        confirmer_names_lookup = {}
        if all_confirmer_uids:
            try:
                prof_res = supabase.table("profiles").select("id, display_name, email, full_name").in_("id", list(all_confirmer_uids)).execute()
                for p in (prof_res.data or []):
                    confirmer_names_lookup[p["id"]] = _format_clean_display_name(p.get("display_name") or p.get("full_name"), p)
            except Exception:
                pass

        now_iso = datetime.now(timezone.utc).isoformat()
        display_name = _format_clean_display_name(profile.get("display_name") or profile.get("full_name"), profile)

        for c in valid_items:
            c["contributor_name"] = display_name
            c["contributor_profile"] = profile or None
            if not c.get("created_at"):
                c["created_at"] = now_iso
            if not c.get("updated_at"):
                c["updated_at"] = c.get("created_at") or now_iso

            votes_for_item = confirmations_map.get(c.get("id"), [])
            item_confirmers = []
            latest_at = None
            for v in votes_for_item:
                cb = v.get("confirmed_by")
                name = confirmer_names_lookup.get(cb) or _format_clean_display_name(cb)
                if name and name not in item_confirmers:
                    item_confirmers.append(name)
                if v.get("confirmed_at"):
                    latest_at = v.get("confirmed_at")

            c["confirmer_names"] = item_confirmers
            date_str = (latest_at or c.get("created_at") or now_iso)[:10]
            if item_confirmers:
                c["confirmation_label"] = f"Confirmed by {', '.join(item_confirmers)} · {date_str}"
            else:
                c["confirmation_label"] = f"Confirmed · {date_str}"

            _enrich_contribution_metadata(c, caller_user_id=None, supabase=supabase, is_public_passport=True)

        # 9. Collapsing Commits & Segregation
        commits = [c for c in valid_items if c.get("source_type") == "github_commit"]
        prs = [c for c in valid_items if c.get("source_type") == "github_pr"]
        manual = [c for c in valid_items if c.get("source_type") not in ("github_commit", "github_pr")]

        display_items = []
        if commits:
            commits_sorted = sorted(commits, key=lambda x: str(x.get("created_at") or x.get("date_range") or ""))
            first_date = (commits_sorted[0].get("created_at") or commits_sorted[0].get("date_range") or now_iso)[:10]
            last_date = (commits_sorted[-1].get("created_at") or commits_sorted[-1].get("date_range") or now_iso)[:10]

            commit_login = github_username or commits_sorted[0].get("author_login") or "contributor"
            if repo_full_name and commit_login:
                commit_link = f"https://github.com/{repo_full_name}/commits?author={commit_login}"
            elif repo_full_name:
                commit_link = f"https://github.com/{repo_full_name}/commits"
            else:
                commit_link = commits_sorted[0].get("evidence_link") or "https://github.com"

            collapsed_commit = {
                "id": f"commits-{project_id}-{user_id}",
                "contributor": user_id,
                "project": project_id,
                "title": f"{len(commits)} commits between {first_date} and {last_date}",
                "category": "code",
                "description": f"Git commit history on {repo_full_name or 'connected repository'}",
                "source_type": "github_commit",
                "evidence_link": commit_link,
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": commits_sorted[-1].get("created_at") or now_iso,
                "updated_at": commits_sorted[-1].get("updated_at") or now_iso,
                "contributor_name": display_name,
                "confirmer_names": [],
                "confirmation_label": None,
            }
            _enrich_contribution_metadata(collapsed_commit, caller_user_id=None, supabase=supabase, is_public_passport=True)
            display_items.append(collapsed_commit)

        display_items.extend(prs)
        display_items.extend(manual)

        confirmed_count = len(prs) + len(manual)
        total_contributions = len(display_items)

        # 10. Summary Line
        N = len(display_items)
        G = (1 if commits else 0) + len(prs)
        C = len(manual)

        all_distinct_confirmers = sorted(list(set(
            name for item in manual for name in item.get("confirmer_names", [])
        )))
        k = len(all_distinct_confirmers)
        names_part = ", ".join(all_distinct_confirmers) if all_distinct_confirmers else "teammates"
        login_str = f"@{github_username}" if github_username else "@contributor"
        summary_line = f"Evidence: {N} items · {G} matched to GitHub {login_str} · {C} confirmed by {names_part} ({k} of {team_size} teammates)"

        return ProjectPassportResponse(
            user_id=user_id,
            project_id=project_id,
            project_name=project_name,
            project_description=project_description,
            is_archived=is_archived,
            archived_at=archived_at,
            team_size=team_size,
            repository=repository,
            repository_url=repository_url,
            display_name=display_name,
            avatar_url=profile.get("avatar_url"),
            github_username=github_username,
            role=role_name,
            role_category=role_category,
            total_contributions=total_contributions,
            confirmed_count=confirmed_count,
            evidence_count=N,
            github_matched_count=G,
            peer_confirmed_count=C,
            confirmer_names=all_distinct_confirmers,
            summary_line=summary_line,
            contributions=display_items,
        )

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg):
            # Local Dev Fallback
            if project_id not in DEV_PROJECTS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Passport not found",
                )
            dev_project = DEV_PROJECTS_DB[project_id]
            project_name = dev_project.get("name", "Project")
            project_description = dev_project.get("description") or ""

            # Team size
            dev_members = [m for m in DEV_PROJECT_MEMBERS_DB if m.get("project_id") == project_id]
            dev_member_ids = {m.get("user_id") for m in dev_members if m.get("user_id")}
            if dev_project.get("created_by"):
                dev_member_ids.add(dev_project["created_by"])
            team_size = max(len(dev_member_ids), 1)

            # Linked repository
            from services.github_service import DEV_GITHUB_INSTALLATIONS_DB
            inst = DEV_GITHUB_INSTALLATIONS_DB.get(project_id, {})
            repo_full_name = inst.get("repo_full_name") or dev_project.get("github_repo")
            if repo_full_name:
                clean_repo = repo_full_name.replace("https://github.com/", "").replace("http://github.com/", "").strip("/")
                repository = clean_repo
                repository_url = f"https://github.com/{clean_repo}"
            else:
                repository = None
                repository_url = None

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

            # Profile and GitHub login
            from routers.projects import DEV_GITHUB_IDENTITIES_DB
            display_name = _format_clean_display_name(DEV_USER_NAMES_DB.get(user_id, f"User {user_id[:8]}"))
            github_username = DEV_GITHUB_IDENTITIES_DB.get(user_id)

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

            # Confirmers map from DEV_CONFIRMATIONS_DB
            confirmations_map = {}
            all_confirmer_uids = set()
            for c in valid_items:
                cid = c.get("id")
                votes = [v for v in DEV_CONFIRMATIONS_DB if v.get("contribution_id") == cid and v.get("action") == "confirm"]
                if votes:
                    confirmations_map[cid] = [{"confirmed_by": v.get("confirmed_by_user_id"), "confirmed_at": v.get("confirmed_at")} for v in votes]
                    for v in votes:
                        if v.get("confirmed_by_user_id"):
                            all_confirmer_uids.add(v.get("confirmed_by_user_id"))
                elif c.get("confirmed_by"):
                    cb = c.get("confirmed_by")
                    confirmations_map[cid] = [{"confirmed_by": cb, "confirmed_at": c.get("created_at")}]
                    all_confirmer_uids.add(cb)

            confirmer_names_lookup = {}
            for uid in all_confirmer_uids:
                confirmer_names_lookup[uid] = _format_clean_display_name(DEV_USER_NAMES_DB.get(uid, f"Teammate {uid[:6]}"))

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

                votes_for_item = confirmations_map.get(c.get("id"), [])
                item_confirmers = []
                latest_at = None
                for v in votes_for_item:
                    cb = v.get("confirmed_by")
                    name = confirmer_names_lookup.get(cb) or _format_clean_display_name(cb)
                    if name and name not in item_confirmers:
                        item_confirmers.append(name)
                    if v.get("confirmed_at"):
                        latest_at = v.get("confirmed_at")

                c["confirmer_names"] = item_confirmers
                date_str = (latest_at or c.get("created_at") or now_iso)[:10]
                if item_confirmers:
                    c["confirmation_label"] = f"Confirmed by {', '.join(item_confirmers)} · {date_str}"
                else:
                    c["confirmation_label"] = f"Confirmed · {date_str}"

                _enrich_contribution_metadata(c, caller_user_id=None, supabase=None, is_public_passport=True)

            # Collapsing raw commits & segregation
            commits = [c for c in valid_items if c.get("source_type") == "github_commit"]
            prs = [c for c in valid_items if c.get("source_type") == "github_pr"]
            manual = [c for c in valid_items if c.get("source_type") not in ("github_commit", "github_pr")]

            display_items = []
            if commits:
                commits_sorted = sorted(commits, key=lambda x: str(x.get("created_at") or x.get("date_range") or ""))
                first_date = (commits_sorted[0].get("created_at") or commits_sorted[0].get("date_range") or now_iso)[:10]
                last_date = (commits_sorted[-1].get("created_at") or commits_sorted[-1].get("date_range") or now_iso)[:10]

                commit_login = github_username or commits_sorted[0].get("author_login") or "contributor"
                if repo_full_name and commit_login:
                    commit_link = f"https://github.com/{repo_full_name}/commits?author={commit_login}"
                elif repo_full_name:
                    commit_link = f"https://github.com/{repo_full_name}/commits"
                else:
                    commit_link = commits_sorted[0].get("evidence_link") or "https://github.com"

                collapsed_commit = {
                    "id": f"commits-{project_id}-{user_id}",
                    "contributor": user_id,
                    "project": project_id,
                    "title": f"{len(commits)} commits between {first_date} and {last_date}",
                    "category": "code",
                    "description": f"Git commit history on {repo_full_name or 'connected repository'}",
                    "source_type": "github_commit",
                    "evidence_link": commit_link,
                    "verification_status": "source-verified",
                    "confirmed_by": None,
                    "visibility": "public",
                    "dispute_state": "none",
                    "created_at": commits_sorted[-1].get("created_at") or now_iso,
                    "updated_at": commits_sorted[-1].get("updated_at") or now_iso,
                    "contributor_name": display_name,
                    "confirmer_names": [],
                    "confirmation_label": None,
                }
                _enrich_contribution_metadata(collapsed_commit, caller_user_id=None, supabase=None, is_public_passport=True)
                display_items.append(collapsed_commit)

            display_items.extend(prs)
            display_items.extend(manual)

            confirmed_count = len(prs) + len(manual)
            total_contributions = len(display_items)

            # Summary Line
            N = len(display_items)
            G = (1 if commits else 0) + len(prs)
            C = len(manual)

            all_distinct_confirmers = sorted(list(set(
                name for item in manual for name in item.get("confirmer_names", [])
            )))
            k = len(all_distinct_confirmers)
            names_part = ", ".join(all_distinct_confirmers) if all_distinct_confirmers else "teammates"
            login_str = f"@{github_username}" if github_username else "@contributor"
            summary_line = f"Evidence: {N} items · {G} matched to GitHub {login_str} · {C} confirmed by {names_part} ({k} of {team_size} teammates)"

            is_archived = bool(dev_project.get("archived_at"))
            archived_at = dev_project.get("archived_at")

            return ProjectPassportResponse(
                user_id=user_id,
                project_id=project_id,
                project_name=project_name,
                project_description=project_description,
                is_archived=is_archived,
                archived_at=archived_at,
                team_size=team_size,
                repository=repository,
                repository_url=repository_url,
                display_name=display_name,
                avatar_url=None,
                github_username=github_username,
                role=role_name,
                role_category=role_category,
                total_contributions=total_contributions,
                confirmed_count=confirmed_count,
                evidence_count=N,
                github_matched_count=G,
                peer_confirmed_count=C,
                confirmer_names=all_distinct_confirmers,
                summary_line=summary_line,
                contributions=display_items,
            )

        logger.exception("Failed to fetch project passport")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporarily unavailable, try again shortly",
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
            _enrich_contribution_metadata(c, caller_user_id=None, supabase=supabase, is_public_passport=True)

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
                _enrich_contribution_metadata(c, caller_user_id=None, supabase=None, is_public_passport=True)

            return PublicContributionsResponse(
                total_count=len(valid_items),
                contributions=valid_items,
            )

        raise handle_route_error(
            e,
            generic_message="Failed to list public contributions. Please try again.",
            log_message="Failed to list public contributions",
        )





