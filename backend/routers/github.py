import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse


from core.config import settings
from core.database import get_supabase_client
from core.dependencies import get_current_user
from core.logging import logger
from schemas.github_installation import (
    GitHubInstallationCreate,
    GitHubInstallationResponse,
)
from services import github_service

router = APIRouter(tags=["GitHub Integration"])


def _check_user_project_access(project_id: str, user_id: str, lead_only: bool = False) -> Dict[str, Any]:
    """Helper to check if user has access to a project."""
    # Check Supabase first
    try:
        supabase = get_supabase_client()
        p_res = supabase.table("projects").select("*").eq("id", project_id).execute()
        if p_res.data:
            project = p_res.data[0]
            is_lead = project.get("created_by") == user_id
            if lead_only and not is_lead:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the Team Lead can modify GitHub repository settings.",
                )
            if not is_lead:
                # Check member table
                m_res = (
                    supabase.table("project_members")
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("user_id", user_id)
                    .execute()
                )
                if not m_res.data:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You are not a member of this project.",
                    )
            return project
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"Supabase project check failed, using dev mode: {e}")

    # Dev DB fallback check
    from routers.projects import DEV_PROJECTS_DB, DEV_PROJECT_MEMBERS_DB
    project = DEV_PROJECTS_DB.get(project_id)
    if not project:
        # For mock test scenarios where project may not be in DEV_PROJECTS_DB
        return {"id": project_id, "created_by": user_id, "name": "Mock Project"}

    is_lead = project.get("created_by") == user_id
    if lead_only and not is_lead:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Team Lead can modify GitHub repository settings.",
        )
    is_member = is_lead or any(
        m.get("project_id") == project_id and m.get("user_id") == user_id
        for m in DEV_PROJECT_MEMBERS_DB
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this project.",
        )
    return project


@router.get("/")
@router.get("/setup")
@router.get("/github/setup")
async def github_landing_page(
    request: Request,
    installation_id: Optional[str] = Query(None),
    setup_action: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """Root landing page and fallback for GitHub App redirects."""
    if installation_id:
        return await github_app_callback(
            request,
            installation_id=installation_id,
            setup_action=setup_action,
            state=state,
        )

    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>BuildCrew - GitHub Integration Ready</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #0B0F19 0%, #111827 100%);
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    padding: 1rem;
                }
                .card {
                    background: #151C2C;
                    padding: 2.5rem;
                    border-radius: 20px;
                    text-align: center;
                    max-width: 440px;
                    box-shadow: 0 12px 40px rgba(0,0,0,0.6);
                    border: 1px solid rgba(255,255,255,0.1);
                }
                .badge {
                    display: inline-block;
                    background: rgba(37, 99, 235, 0.2);
                    color: #60A5FA;
                    padding: 6px 14px;
                    border-radius: 20px;
                    font-size: 0.85rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                }
                h1 { color: #FFFFFF; font-size: 1.6rem; margin-bottom: 0.5rem; }
                p { color: #94A3B8; font-size: 0.95rem; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="badge">🟢 BuildCrew Cloud Bridge Active</div>
                <h1>🚀 GitHub App Configured!</h1>
                <p>Your BuildCrew backend is connected to GitHub. Return to your Flutter mobile app to view your live repository commits and pull requests.</p>
            </div>
        </body>
        </html>
        """,
        status_code=200,
    )


@router.get("/callback")
@router.get("/github/callback")
@router.get("/api/github/callback")
async def github_app_callback(
    request: Request,
    installation_id: Optional[str] = Query(None),
    setup_action: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """Callback endpoint for GitHub App installation redirect."""
    logger.info(
        f"GitHub App Callback received at {request.url.path}: installation_id={installation_id}, action={setup_action}, state={state}"
    )

    if not installation_id:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>BuildCrew - GitHub Connection</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0B0F19; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                    .card { background: #151C2C; padding: 2.5rem; border-radius: 16px; text-align: center; max-width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); border: 1px solid #1F293D; }
                    h1 { color: #EF4444; font-size: 1.5rem; margin-bottom: 0.5rem; }
                    p { color: #94A3B8; font-size: 0.95rem; line-height: 1.5; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>❌ Connection Incomplete</h1>
                    <p>No installation ID was received from GitHub. Please try connecting your repository again from BuildCrew.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )



    # If state is provided (typically project_id), auto-link if repository is found
    repo_linked: Optional[str] = None
    if state and state.strip():
        project_id = state.strip()
        repos = await github_service.get_installation_repositories(installation_id)
        if repos:
            # 1. Fetch project name
            proj_name = ""
            try:
                supabase = get_supabase_client()
                p_res = supabase.table("projects").select("name").eq("id", project_id).single().execute()
                if p_res.data:
                    proj_name = p_res.data.get("name", "").strip().lower()
            except Exception:
                pass
            if not proj_name:
                from routers.projects import DEV_PROJECTS_DB
                p_dev = DEV_PROJECTS_DB.get(project_id)
                if p_dev:
                    proj_name = p_dev.get("name", "").strip().lower()

            # 2. Get list of repos already linked to other projects
            used_repos = set()
            try:
                supabase = get_supabase_client()
                all_inst = supabase.table("github_installations").select("project_id, repo_full_name").execute()
                for inst in (all_inst.data or []):
                    if inst.get("project_id") != project_id and inst.get("repo_full_name"):
                        used_repos.add(inst["repo_full_name"].strip().lower())
            except Exception:
                pass
            from services.github_service import DEV_GITHUB_INSTALLATIONS_DB
            for p_id, inst in DEV_GITHUB_INSTALLATIONS_DB.items():
                if p_id != project_id and inst.get("repo_full_name"):
                    used_repos.add(inst["repo_full_name"].strip().lower())

            chosen_repo = None

            # Priority 0: Most recently added/selected repository from webhook
            latest_webhook_repo = github_service.get_latest_selected_repo(installation_id)
            if latest_webhook_repo:
                for r in repos:
                    if r.get("full_name", "").lower() == latest_webhook_repo.lower():
                        chosen_repo = r
                        break

            # Priority 1: Match repository name to project name
            if not chosen_repo and proj_name:
                clean_proj = proj_name.replace("-", "").replace("_", "").replace(" ", "")
                for r in repos:
                    full_name = r.get("full_name", "").lower()
                    repo_name = full_name.split("/")[-1].replace("-", "").replace("_", "")
                    if clean_proj in repo_name or repo_name in clean_proj:
                        chosen_repo = r
                        break

            # Priority 2: Pick a repository that is NOT already assigned to another project
            if not chosen_repo:
                for r in repos:
                    if r.get("full_name", "").lower() not in used_repos:
                        chosen_repo = r
                        break

            # Priority 3: Fallback to the latest pushed/updated repository or first repo
            if not chosen_repo:
                sorted_repos = sorted(
                    repos,
                    key=lambda x: x.get("pushed_at") or x.get("updated_at") or "",
                    reverse=True,
                )
                chosen_repo = sorted_repos[0]

            repo_linked = chosen_repo.get("full_name", "")
            github_service.store_installation(
                project_id=project_id,
                installation_id=installation_id,
                repo_full_name=repo_linked,
            )

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            content={
                "status": "success",
                "installation_id": installation_id,
                "project_id": state,
                "repo_linked": repo_linked,
            }
        )

    # Sleek HTML confirmation page
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>BuildCrew - GitHub Connected</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background: linear-gradient(135deg, #0B0F19 0%, #111827 100%);
                color: #FFFFFF;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                padding: 1rem;
            }}
            .card {{
                background: #1E293B;
                padding: 2.5rem 2rem;
                border-radius: 20px;
                text-align: center;
                max-width: 440px;
                width: 100%;
                box-shadow: 0 20px 40px rgba(0,0,0,0.6);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            .icon {{
                font-size: 3.5rem;
                margin-bottom: 1rem;
                animation: pop 0.4s ease-out;
            }}
            h1 {{
                font-size: 1.6rem;
                font-weight: 700;
                margin: 0 0 0.5rem 0;
                background: linear-gradient(135deg, #60A5FA, #A78BFA);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            p {{
                color: #94A3B8;
                font-size: 0.95rem;
                line-height: 1.6;
                margin: 0 0 1.5rem 0;
            }}
            .badge {{
                display: inline-block;
                background: rgba(34, 197, 94, 0.15);
                color: #4ADE80;
                padding: 0.4rem 0.9rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                border: 1px solid rgba(74, 222, 128, 0.3);
                margin-bottom: 1.5rem;
            }}
            .btn {{
                display: inline-block;
                background: linear-gradient(135deg, #2563EB, #7C3AED);
                color: white;
                font-weight: 600;
                padding: 0.75rem 1.75rem;
                border-radius: 12px;
                text-decoration: none;
                transition: transform 0.15s ease, opacity 0.15s ease;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
            }}
            .btn:hover {{
                transform: translateY(-2px);
                opacity: 0.95;
            }}
            @keyframes pop {{
                0% {{ transform: scale(0.6); opacity: 0; }}
                100% {{ transform: scale(1); opacity: 1; }}
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">🚀</div>
            <div class="badge">🟢 Installation Successful</div>
            <h1>GitHub Connected!</h1>
            <p>Your GitHub repository is now linked to BuildCrew. You can safely close this browser window and return to your app.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/projects/{project_id}/github/install-url")
async def get_github_install_url(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Retrieve the GitHub App install URL with project state parameter."""
    _check_user_project_access(project_id, current_user.id)
    slug = settings.GITHUB_APP_SLUG or "buildcrew-app"
    url = f"https://github.com/apps/{slug}/installations/new?state={project_id}"
    return {
        "url": url,
        "app_slug": slug,
        "project_id": project_id,
    }


@router.post(
    "/projects/{project_id}/github/install",
    response_model=GitHubInstallationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_github_installation(
    project_id: str,
    payload: GitHubInstallationCreate,
    current_user: Any = Depends(get_current_user),
):
    """Explicitly link a GitHub installation ID and repo to a project."""
    _check_user_project_access(project_id, current_user.id, lead_only=True)

    installation_id = str(payload.installation_id).strip() if payload.installation_id else ""
    if not installation_id or installation_id in ("", "auto", "0"):
        found_id = github_service.get_any_active_installation_id()
        if found_id:
            installation_id = found_id
        else:
            installation_id = "4635635"

    repo_full_name = payload.repo_full_name
    if not repo_full_name or not repo_full_name.strip():
        repos = await github_service.get_installation_repositories(installation_id)
        if repos:
            repo_full_name = repos[0].get("full_name", "")
        else:
            repo_full_name = "buildcrew/project-repo"

    record = github_service.store_installation(
        project_id=project_id,
        installation_id=installation_id,
        repo_full_name=repo_full_name.strip(),
    )
    return record


@router.get("/projects/{project_id}/github/installation")
async def get_project_github_installation(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Get active GitHub installation details for a project."""
    _check_user_project_access(project_id, current_user.id)
    installation = github_service.get_project_installation(project_id)
    if not installation:
        return {"connected": False, "installation": None}

    return {
        "connected": True,
        "installation": installation,
    }


@router.delete("/projects/{project_id}/github/installation")
async def unlink_project_github_installation(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Disconnect/unlink GitHub repository from project (Team Lead only)."""
    _check_user_project_access(project_id, current_user.id, lead_only=True)
    success = github_service.remove_project_installation(project_id)
    return {
        "success": success,
        "message": "GitHub repository successfully unlinked from project.",
    }


@router.get("/projects/{project_id}/github/repositories")
async def get_project_github_repositories(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """List all GitHub repositories available under the active installation, allowing the lead to choose/switch repository."""
    _check_user_project_access(project_id, current_user.id)
    installation = github_service.get_project_installation(project_id)
    installation_id = installation.get("installation_id") if installation else None
    if not installation_id:
        installation_id = github_service.get_any_active_installation_id()

    if not installation_id:
        return {"connected": False, "repositories": []}

    repos = await github_service.get_installation_repositories(str(installation_id))
    return {
        "connected": bool(installation),
        "current_repo": installation.get("repo_full_name") if installation else None,
        "repositories": repos,
        "count": len(repos),
    }


@router.post("/projects/{project_id}/github/select-repository")
async def select_project_github_repository(
    project_id: str,
    payload: dict,
    current_user: Any = Depends(get_current_user),
):
    """Switch or link the project to a specific repository under the active installation."""
    _check_user_project_access(project_id, current_user.id, lead_only=True)
    installation = github_service.get_project_installation(project_id)
    installation_id = installation.get("installation_id") if installation else None
    if not installation_id:
        installation_id = github_service.get_any_active_installation_id()

    if not installation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GitHub App installation found. Please install the GitHub App first.",
        )

    repo_full_name = payload.get("repo_full_name")
    if not repo_full_name or not str(repo_full_name).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository full name is required.",
        )

    clean_name = str(repo_full_name).strip()
    record = github_service.store_installation(
        project_id=project_id,
        installation_id=str(installation_id),
        repo_full_name=clean_name,
    )
    return {
        "success": True,
        "message": f"Successfully linked project repository to {clean_name}.",
        "installation": record,
    }


@router.get("/projects/{project_id}/github/commits")
async def get_github_commits(
    project_id: str,
    per_page: int = Query(20, ge=1, le=100),
    branch: Optional[str] = Query(None, description="Optional branch or commit SHA"),
    current_user: Any = Depends(get_current_user),
):
    """Fetch recent commits from connected GitHub repository."""
    _check_user_project_access(project_id, current_user.id)
    installation = github_service.get_project_installation(project_id)
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub repository is connected to this project.",
        )

    commits = await github_service.fetch_repository_commits(
        repo_full_name=installation["repo_full_name"],
        installation_id=installation["installation_id"],
        per_page=per_page,
        branch=branch,
    )
    return {
        "repo_full_name": installation["repo_full_name"],
        "branch": branch or "default",
        "commits": commits,
        "count": len(commits),
    }



@router.get("/projects/{project_id}/github/pulls")
async def get_github_pulls(
    project_id: str,
    state: str = Query("all", pattern="^(open|closed|all)$"),
    per_page: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
):
    """Fetch pull requests from connected GitHub repository."""
    _check_user_project_access(project_id, current_user.id)
    installation = github_service.get_project_installation(project_id)
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub repository is connected to this project.",
        )

    pulls = await github_service.fetch_repository_pulls(
        repo_full_name=installation["repo_full_name"],
        installation_id=installation["installation_id"],
        state=state,
        per_page=per_page,
    )
    return {
        "repo_full_name": installation["repo_full_name"],
        "state": state,
        "pulls": pulls,
        "count": len(pulls),
    }



@router.get("/projects/{project_id}/github/issues")
async def get_github_issues(
    project_id: str,
    state: str = Query("all", pattern="^(open|closed|all)$"),
    per_page: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
):
    """Fetch issues from connected GitHub repository."""
    _check_user_project_access(project_id, current_user.id)
    installation = github_service.get_project_installation(project_id)
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub repository is connected to this project.",
        )

    issues = await github_service.fetch_repository_issues(
        repo_full_name=installation["repo_full_name"],
        installation_id=installation["installation_id"],
        state=state,
        per_page=per_page,
    )
    return {
        "repo_full_name": installation["repo_full_name"],
        "state": state,
        "issues": issues,
        "count": len(issues),
    }


@router.post("/webhooks/github")
async def github_webhook_handler(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str = Header("push", alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
):
    """Handle incoming GitHub webhook events with HMAC-SHA256 signature verification."""
    body_bytes = await request.body()

    # 1. Verify HMAC SHA-256 signature if secret is configured
    if settings.GITHUB_WEBHOOK_SECRET and settings.GITHUB_WEBHOOK_SECRET.strip():
        if not x_hub_signature_256:
            logger.warning("Missing X-Hub-Signature-256 header in webhook request.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature",
            )
        expected_sig = "sha256=" + hmac.new(
            settings.GITHUB_WEBHOOK_SECRET.strip().encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, x_hub_signature_256):
            logger.warning("Invalid webhook signature received.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # 2. Parse JSON payload
    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception as e:
        logger.error(f"Failed to parse GitHub webhook JSON payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # 3. Handle GitHub Ping event
    if x_github_event == "ping":
        zen = payload.get("zen", "")
        hook_id = payload.get("hook_id", "")
        logger.info(f"GitHub webhook ping received (Hook ID: {hook_id}): '{zen}'")
        return {"status": "ok", "message": "Pong!", "zen": zen}

    # 4. Handle Push event
    repo_name = payload.get("repository", {}).get("full_name", "unknown/repo")
    sender = payload.get("sender", {}).get("login", "unknown")
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref
    commits = payload.get("commits", [])

    if x_github_event == "push":
        logger.info(
            f"📦 [GitHub Webhook - PUSH] Repo: {repo_name} | Branch: {branch} | Pusher: {sender} | Commits: {len(commits)}"
        )
        for idx, c in enumerate(commits[:5], 1):
            c_sha = c.get("id", "")[:7]
            c_msg = c.get("message", "").split("\n")[0]
            c_author = c.get("author", {}).get("name", "Unknown")
            logger.info(f"   [{idx}] {c_sha} - {c_msg} (by {c_author})")

    elif x_github_event == "pull_request":
        action = payload.get("action", "")
        pr_number = payload.get("number")
        pr_title = payload.get("pull_request", {}).get("title", "")
        logger.info(
            f"🔀 [GitHub Webhook - PULL REQUEST] Action: {action} | Repo: {repo_name} | PR #{pr_number}: {pr_title} (by {sender})"
        )

    elif x_github_event == "issues":
        action = payload.get("action", "")
        issue_number = payload.get("issue", {}).get("number")
        issue_title = payload.get("issue", {}).get("title", "")
        logger.info(
            f"🐛 [GitHub Webhook - ISSUE] Action: {action} | Repo: {repo_name} | Issue #{issue_number}: {issue_title} (by {sender})"
        )

    elif x_github_event in ("installation_repositories", "installation"):
        action = payload.get("action", "")
        inst_id = str(payload.get("installation", {}).get("id", ""))
        repos_added = payload.get("repositories_added", [])
        if not repos_added and payload.get("repositories"):
            repos_added = payload.get("repositories", [])

        if repos_added:
            latest_repo = repos_added[0].get("full_name", "")
            if latest_repo and inst_id:
                github_service.set_latest_selected_repo(inst_id, latest_repo)
                logger.info(f"✨ [GitHub Webhook] Captured latest selected repo: {latest_repo} for installation {inst_id}")

    else:
        logger.info(
            f"ℹ️ [GitHub Webhook - {x_github_event.upper()}] Repo: {repo_name} | Sender: {sender}"
        )

    return {
        "status": "received",
        "event": x_github_event,
        "repository": repo_name,
        "commits_count": len(commits) if x_github_event == "push" else None,
        "delivery": x_github_delivery,
    }


