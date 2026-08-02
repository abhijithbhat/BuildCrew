from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict


class ConfirmationBase(BaseModel):
    action: Literal["confirm", "dispute"]
    notes: Optional[str] = None


class ConfirmationCreate(ConfirmationBase):
    contribution_id: str
    confirmed_by_user_id: str


class ConfirmationUpdate(BaseModel):
    action: Optional[Literal["confirm", "dispute"]] = None
    notes: Optional[str] = None


class ConfirmationResponse(ConfirmationBase):
    id: str
    contribution_id: str
    confirmed_by_user_id: str
    confirmed_at: datetime

    model_config = ConfigDict(from_attributes=True)
