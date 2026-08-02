from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class GitHubInstallation:
    id: str
    project_id: str
    installation_id: str
    repo_full_name: str
    connected_at: Optional[datetime] = None
