from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Profile:
    id: str
    display_name: Optional[str] = None
    github_username: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
