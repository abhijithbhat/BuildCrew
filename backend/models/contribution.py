from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Contribution:
    id: str
    contributor: str
    project: str
    title: str
    category: Optional[str] = None
    description: Optional[str] = None
    date_range: Optional[str] = None
    source_type: Optional[str] = None
    evidence_link: Optional[str] = None
    verification_status: str = "pending"
    confirmed_by: Optional[str] = None
    visibility: str = "public"
    dispute_state: str = "none"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
