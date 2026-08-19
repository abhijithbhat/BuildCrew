import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
import jwt

from core.config import settings
from core.database import get_supabase_client
from core.logging import logger

# In-memory storage for local dev fallback mode
DEV_GITHUB_INSTALLATIONS_DB: dict[str, dict] = {}


def _get_private_key_content() -> Optional[bytes]:
    """Retrieve the RSA private key bytes from env or file path."""
    if settings.GITHUB_PRIVATE_KEY and settings.GITHUB_PRIVATE_KEY.strip():
        return settings.GITHUB_PRIVATE_KEY.encode("utf-8")

    key_path = settings.GITHUB_PRIVATE_KEY_PATH
    if not key_path:
        return None

    # Handle both relative (to backend root) and absolute paths
    possible_paths = [
        key_path,
        os.path.join(os.path.dirname(__file__), "..", key_path),
        os.path.join(os.path.dirname(__file__), "..", "..", key_path),
    ]

    for path in possible_paths:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read GitHub private key from {path}: {e}")

    return None


def generate_app_jwt() -> Optional[str]:
    """Generate a short-lived (10 min) RS256 signed GitHub App JWT."""
    if not settings.GITHUB_APP_ID:
        return None

    key_bytes = _get_private_key_content()
    if not key_bytes:
        return None

    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60 seconds ago to prevent clock drift issues
        "exp": now + 600,  # Expires in 10 minutes (maximum GitHub allows)
        "iss": str(settings.GITHUB_APP_ID),
    }

    try:
        encoded_jwt = jwt.encode(payload, key_bytes, algorithm="RS256")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Error encoding GitHub App JWT: {e}")
        return None


# In-memory token cache to avoid spamming GitHub API: {installation_id: {"token": "...", "expires_at": float}}
_INSTALLATION_TOKEN_CACHE: dict[str, dict] = {}


async def get_installation_access_token(
    installation_id: str,
    force_refresh: bool = False,
) -> Optional[str]:
    """Exchange GitHub App JWT for a short-lived Installation Access Token.
    
    Installation tokens from GitHub expire in 1 hour. This function caches
    active tokens in-memory and automatically refreshes them when expired.
    """
    now = time.time()

    # 1. Check in-memory cache unless force_refresh is requested
    if not force_refresh and installation_id in _INSTALLATION_TOKEN_CACHE:
        cached = _INSTALLATION_TOKEN_CACHE[installation_id]
        if cached["expires_at"] > now + 120:  # Valid for at least 2 more minutes
            return cached["token"]

    # 2. Generate signed RS256 App JWT
    app_jwt = generate_app_jwt()
    if not app_jwt:
        logger.warning("GitHub App JWT could not be generated. Using fallback/mock token.")
        return None

    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 201:
                data = resp.json()
                token = data.get("token")
                # Tokens usually expire in 3600 seconds
                expires_at = now + 3500
                _INSTALLATION_TOKEN_CACHE[installation_id] = {
                    "token": token,
                    "expires_at": expires_at,
                }
                return token
            else:
                logger.error(
                    f"Failed to exchange installation token for {installation_id}: {resp.status_code} {resp.text}"
                )
                return None
    except Exception as e:
        logger.error(f"Network error getting installation access token: {e}")
        return None



async def get_installation_repositories(installation_id: str) -> List[Dict[str, Any]]:
    """Retrieve all repositories accessible under this installation."""
    token = await get_installation_access_token(installation_id)
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = "https://api.github.com/installation/repositories"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("repositories", [])
            return []
    except Exception as e:
        logger.error(f"Error fetching installation repositories: {e}")
        return []


def store_installation(
    project_id: str,
    installation_id: str,
    repo_full_name: str,
) -> Dict[str, Any]:
    """Store or update GitHub installation for a project in Supabase or Dev DB."""
    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "installation_id": str(installation_id),
        "repo_full_name": repo_full_name,
        "connected_at": now_iso,
    }

    try:
        supabase = get_supabase_client()
        # Check existing installation for project
        existing = (
            supabase.table("github_installations")
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )

        if existing.data:
            updated = (
                supabase.table("github_installations")
                .update({
                    "installation_id": str(installation_id),
                    "repo_full_name": repo_full_name,
                    "connected_at": now_iso,
                })
                .eq("project_id", project_id)
                .execute()
            )
            if updated.data:
                return updated.data[0]
        else:
            inserted = (
                supabase.table("github_installations")
                .insert(record)
                .execute()
            )
            if inserted.data:
                return inserted.data[0]
    except Exception as e:
        logger.warning(f"Supabase store_installation failed, using local Dev DB: {e}")

    # Fallback in Dev DB
    DEV_GITHUB_INSTALLATIONS_DB[project_id] = record
    return record


def get_project_installation(project_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the active GitHub installation for a project."""
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("github_installations")
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.debug(f"Supabase get_project_installation failed, checking Dev DB: {e}")

    return DEV_GITHUB_INSTALLATIONS_DB.get(project_id)


def remove_project_installation(project_id: str) -> bool:
    """Remove GitHub installation link for a project."""
    deleted_from_supabase = False
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("github_installations")
            .delete()
            .eq("project_id", project_id)
            .execute()
        )
        deleted_from_supabase = bool(res.data)
    except Exception as e:
        logger.warning(f"Supabase remove_project_installation failed: {e}")

    deleted_from_dev = False
    if project_id in DEV_GITHUB_INSTALLATIONS_DB:
        del DEV_GITHUB_INSTALLATIONS_DB[project_id]
        deleted_from_dev = True

    return deleted_from_supabase or deleted_from_dev


async def fetch_repository_commits(
    repo_full_name: str,
    installation_id: str,
    per_page: int = 20,
    branch: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch recent commits from GitHub repository with optional branch/ref filtering."""
    token = await get_installation_access_token(installation_id)
    if not token:
        # Return structured mock data for local testing
        return [
            {
                "sha": "7f8b9a1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a",
                "message": "feat(core): initialize GitHub App integration & repository tracking",
                "author": "BuildCrew Developer",
                "author_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                "date": datetime.now(timezone.utc).isoformat(),
                "url": f"https://github.com/{repo_full_name}/commit/7f8b9a1",
            },
            {
                "sha": "3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b",
                "message": "chore: configure multi-endpoint networking and fallback resilience",
                "author": "BuildCrew Team",
                "author_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                "date": datetime.now(timezone.utc).isoformat(),
                "url": f"https://github.com/{repo_full_name}/commit/3a2b1c0",
            },
        ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    url = f"https://api.github.com/repos/{repo_full_name}/commits?per_page={per_page}"
    if branch and branch.strip():
        url += f"&sha={branch.strip()}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_commits = resp.json()
                commits = []
                for c in raw_commits:
                    commit_obj = c.get("commit", {})
                    author_obj = c.get("author") or {}
                    commits.append({
                        "sha": c.get("sha", ""),
                        "message": commit_obj.get("message", "").split("\n")[0],
                        "author": author_obj.get("login") or commit_obj.get("author", {}).get("name", "Unknown"),
                        "author_avatar": author_obj.get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "date": commit_obj.get("author", {}).get("date") or datetime.now(timezone.utc).isoformat(),
                        "url": c.get("html_url", ""),
                    })
                return commits
            elif resp.status_code == 409:
                # 409 Conflict is returned by GitHub when repository has 0 commits
                logger.info(f"Repository {repo_full_name} is empty (0 commits).")
                return []
            else:
                logger.warning(
                    f"GitHub API returned {resp.status_code} fetching commits for {repo_full_name}: {resp.text}"
                )
                return []
    except Exception as e:
        logger.error(f"Error fetching commits for {repo_full_name}: {e}")
        return []



async def fetch_repository_pulls(
    repo_full_name: str,
    installation_id: str,
    state: str = "all",
    per_page: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch pull requests for repository with author, branch, and status details."""
    token = await get_installation_access_token(installation_id)
    if not token:
        return [
            {
                "id": 101,
                "number": 1,
                "title": "feat: Add GitHub App Integration for BuildCrew",
                "state": "open",
                "user": "buildcrew-dev",
                "user_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "merged_at": None,
                "head_branch": "feature/github-app",
                "base_branch": "main",
                "url": f"https://github.com/{repo_full_name}/pull/1",
                "draft": False,
                "labels": [{"name": "enhancement", "color": "a2eeef"}],
            }
        ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo_full_name}/pulls?state={state}&per_page={per_page}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_pulls = resp.json()
                pulls = []
                for p in raw_pulls:
                    labels = [
                        {"name": l.get("name", ""), "color": l.get("color", "")}
                        for l in p.get("labels", [])
                    ]
                    pulls.append({
                        "id": p.get("id"),
                        "number": p.get("number"),
                        "title": p.get("title", ""),
                        "state": "merged" if p.get("merged_at") else p.get("state", "open"),
                        "user": p.get("user", {}).get("login", "Unknown"),
                        "user_avatar": p.get("user", {}).get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "created_at": p.get("created_at") or datetime.now(timezone.utc).isoformat(),
                        "merged_at": p.get("merged_at"),
                        "head_branch": p.get("head", {}).get("ref", ""),
                        "base_branch": p.get("base", {}).get("ref", ""),
                        "url": p.get("html_url", ""),
                        "draft": p.get("draft", False),
                        "labels": labels,
                    })
                return pulls
            return []
    except Exception as e:
        logger.error(f"Error fetching pull requests for {repo_full_name}: {e}")
        return []



async def fetch_repository_issues(
    repo_full_name: str,
    installation_id: str,
    state: str = "all",
    per_page: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch issues for repository (excluding pull requests)."""
    token = await get_installation_access_token(installation_id)
    if not token:
        return [
            {
                "id": 201,
                "number": 1,
                "title": "Set up CI/CD pipeline and automated test matrix",
                "state": "open",
                "user": "lead-architect",
                "user_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "closed_at": None,
                "url": f"https://github.com/{repo_full_name}/issues/1",
                "comments": 2,
                "labels": [{"name": "devops", "color": "0075ca"}],
                "assignees": ["lead-architect"],
            }
        ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo_full_name}/issues?state={state}&per_page={per_page}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_issues = resp.json()
                issues = []
                for item in raw_issues:
                    # GitHub Issues endpoint also returns PRs unless filtered by 'pull_request' key
                    if "pull_request" in item:
                        continue
                    labels = [
                        {"name": l.get("name", ""), "color": l.get("color", "")}
                        for l in item.get("labels", [])
                    ]
                    assignees = [
                        a.get("login", "") for a in item.get("assignees", []) if a.get("login")
                    ]
                    issues.append({
                        "id": item.get("id"),
                        "number": item.get("number"),
                        "title": item.get("title", ""),
                        "state": item.get("state", "open"),
                        "user": item.get("user", {}).get("login", "Unknown"),
                        "user_avatar": item.get("user", {}).get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "created_at": item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                        "closed_at": item.get("closed_at"),
                        "url": item.get("html_url", ""),
                        "comments": item.get("comments", 0),
                        "labels": labels,
                        "assignees": assignees,
                    })
                return issues
            return []
    except Exception as e:
        logger.error(f"Error fetching issues for {repo_full_name}: {e}")
        return []
