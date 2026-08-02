from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ProjectMember:
    project_id: str
    user_id: str
    role: str = "member"
    joined_at: Optional[datetime] = None
