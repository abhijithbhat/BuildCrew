from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RoleAgreementBase(BaseModel):
    declared_role: str
    responsibilities: Optional[str] = None
    deadline: Optional[datetime] = None


class RoleAgreementCreate(RoleAgreementBase):
    project_id: str
    user_id: str


class RoleAgreementUpdate(BaseModel):
    declared_role: Optional[str] = None
    responsibilities: Optional[str] = None
    deadline: Optional[datetime] = None


class RoleAgreementResponse(RoleAgreementBase):
    id: str
    project_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
