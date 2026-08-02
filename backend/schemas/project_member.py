from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProjectMemberBase(BaseModel):
    role: str = "member"


class ProjectMemberCreate(ProjectMemberBase):
    project_id: str
    user_id: str


class ProjectMemberUpdate(BaseModel):
    role: str


class ProjectMemberResponse(ProjectMemberBase):
    project_id: str
    user_id: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)
