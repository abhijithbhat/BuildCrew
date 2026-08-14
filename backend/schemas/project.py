from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    created_by: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(ProjectBase):
    id: str
    created_by: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectInviteResponse(BaseModel):
    invite_code: str
    project_id: str
    project_name: Optional[str] = None
    created_by: Optional[str] = None
    invite_url: str
    created_at: Optional[Union[datetime, str]] = None
    expires_at: Optional[Union[datetime, str]] = None
    message: Optional[str] = "Invite code generated successfully"

    model_config = ConfigDict(from_attributes=True)


class ProjectJoinRequest(BaseModel):
    invite_code: str


class ProjectJoinResponse(BaseModel):
    message: str = "Successfully joined project"
    project: dict
    member: dict

    model_config = ConfigDict(from_attributes=True)



