from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
