from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProfileBase(BaseModel):
    display_name: Optional[str] = None
    github_username: Optional[str] = None
    avatar_url: Optional[str] = None


class ProfileCreate(ProfileBase):
    id: str


class ProfileUpdate(ProfileBase):
    pass


class ProfileResponse(ProfileBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
