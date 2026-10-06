import hashlib
import hmac
import html
import json
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
import jwt

from core.config import settings
from core.database import get_supabase_client, is_dev_mode
from core.dependencies import get_current_user
from core.logging import logger
from schemas.github_installation import (
    GitHubInstallationCreate,
    GitHubInstallationResponse,
)
from services import github_service

router = APIRouter(tags=["GitHub Integration"])


def _render_error_html(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    """Render a generic styled HTML error page with HTML-escaped text."""
    safe_title = html.escape(str(title))
    safe_message = html.escape(str(message))
    content = f"""<!DOCTYPE html>
<html>
<head>
    <title>BuildCrew - {safe_title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0B0F19; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
        .card {{ background: #151C2C; padding: 2.5rem; border-radius: 16px; text-align: center; max-width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); border: 1px solid #1F293D; }}
        h1 {{ color: #EF4444; font-size: 1.5rem; margin-bottom: 0.5rem; }}
        p {{ color: #94A3B8; font-size: 0.95rem; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>❌ {safe_title}</h1>
        <p>{safe_message}</p>
    </div>
</body>
</html>"""
    return HTMLResponse(content=content, status_code=status_code)


def _check_user_project_access(project_id: str, user_id: str, lead_only: bool = False) -> Dict[str, Any]:
    """Helper to check if user has access to a project."""
    # Check Supabase first
    try:
        supabase = get_supabase_client()
        p_res = supabase.table("projects").select("*").eq("id", project_id).execute()
        if p_res.data:
            project = p_res.data[0]
            is_lead = str(project.get("created_by")) == str(user_id)
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
        else:
            if not is_dev_mode():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found.",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"Supabase project check failed: {e}")
        if not is_dev_mode():
            logger.warning(f"Upstream Supabase project check failed in production: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable",
            )

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
    code: Optional[str] = Query(None),
):
    """Root landing page and fallback for GitHub App redirects."""
    if not is_dev_mode():
        return await github_app_callback(
            request,
            installation_id=installation_id,
            setup_action=setup_action,
            state=state,
            code=code,
        )

    if installation_id:
        return await github_app_callback(
            request,
            installation_id=installation_id,
            setup_action=setup_action,
            state=state,
            code=code,
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
    code: Optional[str] = Query(None),
):
    """Callback endpoint for GitHub App installation redirect."""
    logger.info(
        f"GitHub App Callback received at {request.url.path}: installation_id={installation_id}, action={setup_action}, state={state}"
    )

    if not is_dev_mode():
        # In production mode:
        # Every callback route must verify signature and expiry and re-check that uid is still the project's lead.
        # Missing, invalid or expired state -> HTTP 400 with a generic HTML page and NO database write.
        if not state or not str(state).strip():
            logger.warning("Missing state parameter in GitHub App callback in production mode.")
            return _render_error_html("Invalid Request", "Missing state parameter. Please initiate connection from BuildCrew.", 400)

        secret = settings.APP_SECRET_KEY
        if not secret:
            logger.error("APP_SECRET_KEY is not configured in production.")
            return _render_error_html("Server Configuration Error", "Application secret key is not configured.", 400)

        try:
            payload = jwt.decode(str(state).strip(), secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            logger.warning("Expired state token received in GitHub App callback.")
            return _render_error_html("Session Expired", "The GitHub installation session has expired. Please try connecting again.", 400)
        except Exception as e:
            logger.warning(f"Invalid state token received in GitHub App callback: {e}")
            return _render_error_html("Invalid State", "Invalid state token. Please try connecting again.", 400)

        pid = payload.get("pid")
        uid = payload.get("uid")
        if not pid or not uid:
            logger.warning("State payload missing pid or uid.")
            return _render_error_html("Invalid State", "State payload missing required identifiers.", 400)

        # Re-check that uid is still the project's lead
        try:
            supabase = get_supabase_client()
            p_res = supabase.table("projects").select("id, created_by, name").eq("id", pid).execute()
            if not p_res.data:
                return _render_error_html("Project Not Found", "The specified project could not be found.", 404)
            project = p_res.data[0]
        except Exception as e:
            logger.error(f"Error checking project lead in callback: {e}")
            return _render_error_html("Service Unavailable", "Could not verify project ownership.", 500)

        if str(project.get("created_by")) != str(uid):
            logger.warning(f"User {uid} is not lead of project {pid} (actual: {project.get('created_by')})")
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Only the Team Lead can modify GitHub repository settings."},
                )
            return _render_error_html("Forbidden", "Only the Team Lead can modify GitHub repository settings.", 403)

        if not installation_id:
            return _render_error_html("Connection Incomplete", "No installation ID was received from GitHub.", 400)

        # Verify OAuth code and ensure installation_id belongs to the authorized user
        if not code or not str(code).strip():
            logger.warning("Missing code parameter in GitHub App callback in production mode.")
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Missing authorization code."},
                )
            return _render_error_html(
                "Invalid Request",
                "Missing authorization code. Please initiate connection from BuildCrew.",
                400,
            )

        user_token = await github_service.exchange_code_for_user_token(str(code).strip())
        if not user_token:
            logger.warning("Failed to exchange OAuth code for user access token.")
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Failed to exchange authorization code."},
                )
            return _render_error_html(
                "Authentication Failed",
                "Failed to exchange authorization code with GitHub. Please try again.",
                400,
            )

        user_installations = await github_service.get_user_installations(user_token)
        user_inst_ids = {
            str(inst["id"])
            for inst in user_installations
            if isinstance(inst, dict) and "id" in inst
        }
        if str(installation_id) not in user_inst_ids:
            logger.warning(
                f"Installation ID {installation_id} not authorized for current user (authorized: {user_inst_ids})"
            )
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Installation ID is not authorized for your GitHub account."},
                )
            return _render_error_html(
                "Forbidden",
                "Installation ID is not authorized for your GitHub account.",
                403,
            )

        project_id = str(pid)
    else:
        # Dev mode keeps today's behaviour
        if not installation_id:
            return _render_error_html(
                "Connection Incomplete",
                "No installation ID was received from GitHub. Please try connecting your repository again from BuildCrew.",
                400,
            )
        project_id = str(state).strip() if state and str(state).strip() else None

    # Auto-link if repository is found
    repo_linked: Optional[str] = None
    if project_id:
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
            if not proj_name and is_dev_mode():
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
            if is_dev_mode():
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
                "project_id": project_id,
                "repo_linked": repo_linked,
            }
        )

    # Sleek HTML confirmation page with HTML-escaped interpolated values
    safe_title = html.escape("GitHub Connected!")
    safe_repo = html.escape(str(repo_linked or ""))
    safe_pid = html.escape(str(project_id or ""))
    safe_inst = html.escape(str(installation_id or ""))

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>BuildCrew - {safe_title}</title>
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
        .repo {{
            color: #60A5FA;
            font-family: monospace;
            background: rgba(15, 23, 42, 0.6);
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
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
        <h1>{safe_title}</h1>
        <p>Your GitHub repository {f'<span class="repo">{safe_repo}</span>' if safe_repo else ''} is now linked to BuildCrew. You can safely close this browser window and return to your app.</p>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/projects/{project_id}/github/install-url")
async def get_github_install_url(
    project_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Retrieve the GitHub App install URL with project state parameter."""
    _check_user_project_access(project_id, current_user.id)
    slug = settings.GITHUB_APP_SLUG or "buildcrew-app"

    if is_dev_mode():
        state_param = project_id
    else:
        now = int(time.time())
        state_payload = {
            "pid": project_id,
            "uid": str(current_user.id),
            "exp": now + 15 * 60,
        }
        secret = settings.APP_SECRET_KEY
        state_param = jwt.encode(state_payload, secret, algorithm="HS256")

    url = f"https://github.com/apps/{slug}/installations/new?state={state_param}"
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

    if is_dev_mode():
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

    # Production mode:
    # A project may use only its own github_installations row, or one belonging to another project led by the same user.
    # POST /github/install returns 400 when neither exists.
    # Delete the hardcoded installation id "4635635" and the "buildcrew/project-repo" placeholder.
    installation = github_service.get_project_installation(project_id)
    installation_id = installation.get("installation_id") if installation else None
    if not installation_id:
        installation_id = github_service.get_installation_id_for_lead(str(current_user.id))

    if not installation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active GitHub App installation found for this project or lead. Please install the GitHub App first.",
        )

    repo_full_name = str(payload.repo_full_name or "").strip()
    if not repo_full_name:
        repos = await github_service.get_installation_repositories(str(installation_id))
        if repos:
            repo_full_name = repos[0].get("full_name", "")
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No repositories available for this GitHub installation.",
            )

    record = github_service.store_installation(
        project_id=project_id,
        installation_id=str(installation_id),
        repo_full_name=repo_full_name,
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
        if is_dev_mode():
            installation_id = github_service.get_any_active_installation_id()
        else:
            installation_id = github_service.get_installation_id_for_lead(str(current_user.id))

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
        if is_dev_mode():
            installation_id = github_service.get_any_active_installation_id()
        else:
            installation_id = github_service.get_installation_id_for_lead(str(current_user.id))

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

    if not is_dev_mode():
        # Requirement 3: select-repository must check that repo_full_name is in get_installation_repositories(installation_id) for that installation, else 400.
        repos = await github_service.get_installation_repositories(str(installation_id))
        allowed_names = [r.get("full_name") for r in repos if isinstance(r, dict) and r.get("full_name")]
        if clean_name not in allowed_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository '{clean_name}' is not in the granted repositories for this installation.",
            )

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

    # 1. Verify HMAC SHA-256 signature
    if not is_dev_mode():
        # Requirement 5: in production require GITHUB_WEBHOOK_SECRET (startup RuntimeError if missing), always verify X-Hub-Signature-256, 401 otherwise.
        if not settings.GITHUB_WEBHOOK_SECRET or not settings.GITHUB_WEBHOOK_SECRET.strip():
            logger.error("Missing GITHUB_WEBHOOK_SECRET in production.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook secret configuration",
            )
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
    else:
        # Dev mode: verify if secret is configured
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


