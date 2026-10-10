import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
import jwt
from fastapi import HTTPException

from core.config import settings
from core.database import get_supabase_client
from core.logging import logger

# In-memory storage for local dev fallback mode
DEV_GITHUB_INSTALLATIONS_DB: dict[str, dict] = {}


def _get_private_key_content() -> Optional[bytes]:
    """Retrieve the RSA private key bytes from env or file path."""
    if settings.GITHUB_PRIVATE_KEY and settings.GITHUB_PRIVATE_KEY.strip():
        key_str = settings.GITHUB_PRIVATE_KEY.strip().replace("\\n", "\n")
        return key_str.encode("utf-8")

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
        from core.database import is_dev_mode
        if is_dev_mode():
            return [
                {"full_name": "buildcrew/mobile-flutter"},
                {"full_name": "buildcrew/backend"},
                {"full_name": "lead-org/approved-repo"},
            ]
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


LATEST_SELECTED_REPOS_CACHE: Dict[str, str] = {}


def set_latest_selected_repo(installation_id: str, repo_full_name: str) -> None:
    """Record the most recent repository selected on GitHub for an installation."""
    LATEST_SELECTED_REPOS_CACHE[str(installation_id)] = repo_full_name


def get_latest_selected_repo(installation_id: str) -> Optional[str]:
    """Retrieve the most recent repository selected on GitHub for an installation."""
    return LATEST_SELECTED_REPOS_CACHE.get(str(installation_id))


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


def get_installation_id_for_lead(user_id: str) -> Optional[str]:
    """Find active installation ID from projects led by this user (created_by == user_id)."""
    if not user_id:
        return None

    try:
        supabase = get_supabase_client()
        p_res = supabase.table("projects").select("id").eq("created_by", user_id).execute()
        lead_pids = [p["id"] for p in (p_res.data or []) if p.get("id")]
        if lead_pids:
            inst_res = (
                supabase.table("github_installations")
                .select("installation_id")
                .in_("project_id", lead_pids)
                .order("connected_at", desc=True)
                .limit(1)
                .execute()
            )
            if inst_res.data and inst_res.data[0].get("installation_id"):
                return str(inst_res.data[0]["installation_id"])
    except Exception as e:
        logger.debug(f"Supabase get_installation_id_for_lead failed: {e}")

    from core.database import is_dev_mode
    if is_dev_mode():
        from routers.projects import DEV_PROJECTS_DB
        dev_lead_pids = {pid for pid, p in DEV_PROJECTS_DB.items() if p.get("created_by") == user_id}
        for pid in dev_lead_pids:
            inst = DEV_GITHUB_INSTALLATIONS_DB.get(pid)
            if inst and inst.get("installation_id"):
                return str(inst["installation_id"])

    return None


def get_any_active_installation_id() -> Optional[str]:
    """Deprecated: cross-team fallbacks stopped. Use get_installation_id_for_lead(user_id)."""
    return None


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
    """Clear repo_full_name from the project's GitHub installation link, keeping the installation row."""
    updated_supabase = False
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("github_installations")
            .update({"repo_full_name": ""})
            .eq("project_id", project_id)
            .execute()
        )
        updated_supabase = bool(res.data)
    except Exception as e:
        logger.warning(f"Supabase remove_project_installation failed: {e}")

    updated_dev = False
    if project_id in DEV_GITHUB_INSTALLATIONS_DB:
        DEV_GITHUB_INSTALLATIONS_DB[project_id]["repo_full_name"] = ""
        updated_dev = True

    return updated_supabase or updated_dev


async def fetch_repository_commits(
    repo_full_name: str,
    installation_id: str,
    per_page: int = 20,
    branch: Optional[str] = None,
    since: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch recent commits from GitHub repository with optional branch/ref and since filtering."""
    token = await get_installation_access_token(installation_id)
    if not token:
        from core.database import is_dev_mode
        if is_dev_mode():
            # Return structured mock data for local testing in dev mode only
            return [
                {
                    "sha": "7f8b9a1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a",
                    "message": "feat(core): initialize GitHub App integration & repository tracking",
                    "author": "BuildCrew Developer",
                    "author_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                    "date": datetime.now(timezone.utc).isoformat(),
                    "url": f"https://github.com/{repo_full_name}/commit/7f8b9a1",
                    "author_email": "dev@buildcrew.io",
                    "author_login": "buildcrew-dev",
                    "author_name": "BuildCrew Developer",
                },
                {
                    "sha": "3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b",
                    "message": "chore: configure multi-endpoint networking and fallback resilience",
                    "author": "BuildCrew Team",
                    "author_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                    "date": datetime.now(timezone.utc).isoformat(),
                    "url": f"https://github.com/{repo_full_name}/commit/3a2b1c0",
                    "author_email": "team@buildcrew.io",
                    "author_login": "buildcrew-team",
                    "author_name": "BuildCrew Team",
                },
            ]
        raise HTTPException(
            status_code=502,
            detail="GitHub is unavailable. Please try again.",
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    url = f"https://api.github.com/repos/{repo_full_name}/commits?per_page={per_page}"
    if branch and branch.strip():
        url += f"&sha={branch.strip()}"
    if since and since.strip():
        url += f"&since={since.strip()}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                raw_commits = resp.json()
                commits = []
                for c in raw_commits:
                    commit_obj = c.get("commit", {})
                    author_obj = c.get("author") or {}
                    committer_obj = commit_obj.get("committer") or {}
                    commit_author = commit_obj.get("author") or {}
                    commits.append({
                        "sha": c.get("sha", ""),
                        "message": commit_obj.get("message", "").split("\n")[0],
                        "author": author_obj.get("login") or commit_author.get("name", "Unknown"),
                        "author_avatar": author_obj.get("avatar_url") or "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
                        "date": commit_author.get("date") or committer_obj.get("date") or datetime.now(timezone.utc).isoformat(),
                        "url": c.get("html_url", ""),
                        "author_email": commit_author.get("email"),
                        "author_login": author_obj.get("login"),
                        "author_name": commit_author.get("name"),
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
                from core.database import is_dev_mode
                if not is_dev_mode():
                    raise HTTPException(
                        status_code=502,
                        detail="GitHub is unavailable. Please try again.",
                    )
                return []
    except HTTPException:
        raise
    except Exception as e:
        from core.database import is_dev_mode
        if not is_dev_mode():
            raise HTTPException(
                status_code=502,
                detail="GitHub is unavailable. Please try again.",
            )
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
        from core.database import is_dev_mode
        if is_dev_mode():
            return [
                {
                    "id": 101,
                    "number": 1,
                    "title": "feat: Add GitHub App Integration for BuildCrew",
                    "state": "merged",
                    "user": "buildcrew-dev",
                    "user_avatar": "https://avatars.githubusercontent.com/u/9919?v=4",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "merged_at": datetime.now(timezone.utc).isoformat(),
                    "head_branch": "feature/github-app",
                    "base_branch": "main",
                    "url": f"https://github.com/{repo_full_name}/pull/1",
                    "draft": False,
                    "labels": [{"name": "enhancement", "color": "a2eeef"}],
                }
            ]
        raise HTTPException(
            status_code=502,
            detail="GitHub is unavailable. Please try again.",
        )

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
            from core.database import is_dev_mode
            if not is_dev_mode():
                raise HTTPException(
                    status_code=502,
                    detail="GitHub is unavailable. Please try again.",
                )
            return []
    except HTTPException:
        raise
    except Exception as e:
        from core.database import is_dev_mode
        if not is_dev_mode():
            raise HTTPException(
                status_code=502,
                detail="GitHub is unavailable. Please try again.",
            )
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
        from core.database import is_dev_mode
        if is_dev_mode():
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
        raise HTTPException(
            status_code=502,
            detail="GitHub is unavailable. Please try again.",
        )

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
            from core.database import is_dev_mode
            if not is_dev_mode():
                raise HTTPException(
                    status_code=502,
                    detail="GitHub is unavailable. Please try again.",
                )
            return []
    except HTTPException:
        raise
    except Exception as e:
        from core.database import is_dev_mode
        if not is_dev_mode():
            raise HTTPException(
                status_code=502,
                detail="GitHub is unavailable. Please try again.",
            )
        logger.error(f"Error fetching issues for {repo_full_name}: {e}")
        return []


async def exchange_code_for_user_token(code: str) -> Optional[str]:
    """
    Exchange OAuth temporary code for a user access token via GitHub OAuth token endpoint:
    POST https://github.com/login/oauth/access_token
    """
    client_id = settings.GITHUB_CLIENT_ID
    client_secret = settings.GITHUB_CLIENT_SECRET
    if not client_id or not client_secret:
        logger.error("GITHUB_CLIENT_ID or GITHUB_CLIENT_SECRET is missing for OAuth code exchange.")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                if not token:
                    logger.warning(f"No access_token in GitHub OAuth response: {data}")
                return token
            logger.warning(f"GitHub OAuth token exchange failed with status {resp.status_code}: {resp.text}")
            return None
    except Exception as e:
        logger.error(f"Error exchanging GitHub OAuth code: {e}")
        return None


async def get_user_installations(user_token: str) -> List[Dict[str, Any]]:
    """
    Fetch the list of GitHub App installations accessible to the authenticated user:
    GET https://api.github.com/user/installations
    """
    if not user_token:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.github.com/user/installations",
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return data.get("installations", [])
                if isinstance(data, list):
                    return data
                return []
            logger.warning(f"GitHub user installations request failed with status {resp.status_code}: {resp.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching user installations: {e}")
        return []

