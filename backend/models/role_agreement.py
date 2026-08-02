from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RoleAgreement:
    id: str
    project_id: str
    user_id: str
    declared_role: str
    responsibilities: Optional[str] = None
    deadline: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
