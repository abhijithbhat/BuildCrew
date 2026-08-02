from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Confirmation:
    id: str
    contribution_id: str
    confirmed_by_user_id: str
    action: Literal["confirm", "dispute"]
    confirmed_at: Optional[datetime] = None
    notes: Optional[str] = None
