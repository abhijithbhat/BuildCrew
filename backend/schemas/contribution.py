from datetime import datetime
from typing import Any, List, Optional, Union
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, field_validator


def _validate_evidence_link(v: Optional[str]) -> Optional[str]:
    """Validate evidence_link for creation and updates.
    
    Trim whitespace, allow only http:// or https:// URLs with a valid hostname, max 2048 chars;
    otherwise raise ValueError resulting in 422: 'Evidence link must start with http:// or https://'.
    """
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if len(v) > 2048:
        raise ValueError("Evidence link must start with http:// or https://")
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("Evidence link must start with http:// or https://")
    parsed = urlparse(v)
    if not parsed.scheme or not parsed.netloc or not parsed.netloc.strip():
        raise ValueError("Evidence link must start with http:// or https://")
    return v


def _sanitize_existing_evidence_link(v: Any) -> Optional[str]:
    """Sanitize existing rows: skip rendering any link that is not valid http(s)."""
    if not v:
        return None
    v = str(v).strip()
    if not v:
        return None
    if len(v) > 2048:
        return None
    if not (v.startswith("http://") or v.startswith("https://")):
        return None
    try:
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc or not parsed.netloc.strip():
            return None
    except Exception:
        return None
    return v


class ContributionBase(BaseModel):
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    date_range: Optional[str] = None
    source_type: Optional[str] = None
    evidence_link: Optional[str] = None
    verification_status: str = "pending"
    confirmed_by: Optional[str] = None
    visibility: str = "private"
    dispute_state: str = "none"

    @field_validator("evidence_link", mode="after")
    @classmethod
    def validate_evidence_link(cls, v: Optional[str]) -> Optional[str]:
        return _validate_evidence_link(v)


class ContributionCreate(ContributionBase):
    contributor: str
    project: str


class ManualContributionCreate(BaseModel):
    project_id: Optional[str] = None
    project: Optional[str] = None
    title: str
    category: Optional[str] = "other"
    description: Optional[str] = None
    date_range: Optional[str] = None
    source_type: Optional[str] = "manual"
    evidence_link: Optional[str] = None
    visibility: Optional[str] = "private"

    @field_validator("evidence_link", mode="after")
    @classmethod
    def validate_evidence_link(cls, v: Optional[str]) -> Optional[str]:
        return _validate_evidence_link(v)


class ContributionUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date_range: Optional[str] = None
    source_type: Optional[str] = None
    evidence_link: Optional[str] = None
    verification_status: Optional[str] = None
    confirmed_by: Optional[str] = None
    visibility: Optional[str] = None
    dispute_state: Optional[str] = None

    @field_validator("evidence_link", mode="after")
    @classmethod
    def validate_evidence_link(cls, v: Optional[str]) -> Optional[str]:
        return _validate_evidence_link(v)


class ConfirmationVoteInfo(BaseModel):
    name: str
    at: Union[datetime, str]

    model_config = ConfigDict(from_attributes=True)


class DisputeContributionPayload(BaseModel):
    reason: Optional[str] = None


class ContributionResponse(ContributionBase):
    id: str
    contributor: str
    project: str
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    contributor_name: Optional[str] = None
    contributor_profile: Optional[dict] = None
    confirmations: List[ConfirmationVoteInfo] = []
    confirm_count: int = 0
    team_size: int = 0
    disputed_by_name: Optional[str] = None
    dispute_reason: Optional[str] = None
    confirmer_names: List[str] = []
    confirmation_label: Optional[str] = None
    can_reopen: bool = False
    is_dispute_orphaned: bool = False

    @field_validator("evidence_link", mode="before")
    @classmethod
    def sanitize_evidence_link_for_response(cls, v: Any) -> Optional[str]:
        return _sanitize_existing_evidence_link(v)

    model_config = ConfigDict(from_attributes=True)


class LedgerEntryResponse(BaseModel):
    id: str
    contributor_id: str
    contributor_name: Optional[str] = None
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    evidence_link: Optional[str] = None
    verification_status: str
    confirmations: List[ConfirmationVoteInfo] = []
    waiting_on_me: bool = False
    created_at: Union[datetime, str]

    @field_validator("evidence_link", mode="before")
    @classmethod
    def sanitize_evidence_link(cls, v: Any) -> Optional[str]:
        return _sanitize_existing_evidence_link(v)

    model_config = ConfigDict(from_attributes=True)


class UnmatchedAuthorInfo(BaseModel):
    login: str
    count: int

    model_config = ConfigDict(from_attributes=True)


class DraftGenerationResponse(BaseModel):
    message: str
    project_id: str
    generated_count: int
    contributions: List[ContributionResponse]
    last_generated_at: str
    unmatched: List[UnmatchedAuthorInfo] = []
    skipped_bots: int = 0

    model_config = ConfigDict(from_attributes=True)


class ContributionsListResponse(BaseModel):
    project_id: str
    total_count: int
    draft_count: int
    confirmed_count: int
    contributions: List[ContributionResponse]


class EvidenceUploadResponse(BaseModel):
    url: str
    filename: str
    file_type: str
    size_bytes: int
    storage_path: Optional[str] = None


class RequestConfirmationPayload(BaseModel):
    reviewer_ids: Optional[List[str]] = None


class ConfirmationRequestResponse(BaseModel):
    id: str
    contribution_id: str
    project_id: str
    requested_by: str
    reviewer_id: str
    status: str = "pending"
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]

    # Enriched metadata for clients
    contribution_title: Optional[str] = None
    project_name: Optional[str] = None
    contributor_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    evidence_link: Optional[str] = None
    contribution: Optional[ContributionResponse] = None

    @field_validator("evidence_link", mode="before")
    @classmethod
    def sanitize_evidence_link(cls, v: Any) -> Optional[str]:
        return _sanitize_existing_evidence_link(v)

    model_config = ConfigDict(from_attributes=True)


class PendingConfirmationsListResponse(BaseModel):
    total_count: int
    requests: List[ConfirmationRequestResponse]


class UserPassportResponse(BaseModel):
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    github_username: Optional[str] = None
    total_contributions: int
    confirmed_count: int
    contributions: List[ContributionResponse]

    model_config = ConfigDict(from_attributes=True)


class PublicContributionsResponse(BaseModel):
    total_count: int
    contributions: List[ContributionResponse]

    model_config = ConfigDict(from_attributes=True)


class ProjectPassportResponse(BaseModel):
    user_id: str
    project_id: str
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    team_size: int = 1
    repository: Optional[str] = None
    repository_url: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    github_username: Optional[str] = None
    role: Optional[str] = None
    role_category: Optional[str] = None
    total_contributions: int
    confirmed_count: int
    evidence_count: int = 0
    github_matched_count: int = 0
    peer_confirmed_count: int = 0
    confirmer_names: List[str] = []
    summary_line: Optional[str] = None
    is_archived: bool = False
    archived_at: Optional[Union[datetime, str]] = None
    contributions: List[ContributionResponse]

    model_config = ConfigDict(from_attributes=True)


