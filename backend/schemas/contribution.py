from datetime import datetime
from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict


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


class ContributionResponse(ContributionBase):
    id: str
    contributor: str
    project: str
    created_at: Union[datetime, str]
    updated_at: Union[datetime, str]
    contributor_name: Optional[str] = None
    contributor_profile: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class DraftGenerationResponse(BaseModel):
    message: str
    project_id: str
    generated_count: int
    contributions: List[ContributionResponse]
    last_generated_at: str


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
    reviewer_ids: List[str]


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
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    github_username: Optional[str] = None
    role: Optional[str] = None
    role_category: Optional[str] = None
    total_contributions: int
    confirmed_count: int
    contributions: List[ContributionResponse]

    model_config = ConfigDict(from_attributes=True)


