from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, model_validator


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


class RoleDeclareRequest(BaseModel):
    declared_role: Optional[str] = None
    role: Optional[str] = None
    responsibilities: Optional[str] = None
    deadline: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_role(cls, data: Any) -> Any:
        if isinstance(data, dict):
            role_val = data.get("declared_role") or data.get("role")
            if role_val is not None and isinstance(role_val, str):
                data["declared_role"] = role_val.strip()
        return data


class RoleAgreementResponse(RoleAgreementBase):
    id: str
    project_id: str
    user_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    profiles: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, extra="allow")


class RoleDeclarationResponse(BaseModel):
    message: str
    role_agreement: RoleAgreementResponse

    model_config = ConfigDict(from_attributes=True)


class RoleAgreementsListResponse(BaseModel):
    roles: list[RoleAgreementResponse] = []
    role_agreements: Optional[list[RoleAgreementResponse]] = None
    project_id: Optional[str] = None
    created_by: Optional[str] = None
    lead_user_id: Optional[str] = None
    total_members: Optional[int] = None
    declared_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, extra="allow")




