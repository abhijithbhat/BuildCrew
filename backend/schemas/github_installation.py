from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class GitHubInstallationBase(BaseModel):
    installation_id: str
    repo_full_name: str


class GitHubInstallationCreate(BaseModel):
    installation_id: str
    repo_full_name: Optional[str] = None
    project_id: Optional[str] = None



class GitHubInstallationUpdate(BaseModel):
    installation_id: Optional[str] = None
    repo_full_name: Optional[str] = None


class GitHubInstallationResponse(GitHubInstallationBase):
    id: str
    project_id: str
    connected_at: datetime

    model_config = ConfigDict(from_attributes=True)
