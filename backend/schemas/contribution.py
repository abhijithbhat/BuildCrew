from datetime import datetime
from typing import Optional
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
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
