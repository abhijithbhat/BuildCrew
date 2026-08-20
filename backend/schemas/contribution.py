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
    visibility: str = "public"
    dispute_state: str = "none"


class ContributionCreate(ContributionBase):
    contributor: str
    project: str


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
