import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.logging import logger
from core.templates import templates
from routers.auth import router as auth_router
from routers.contributions import router as contributions_router
from routers.github import router as github_router
from routers.health import router as health_router
from routers.projects import router as projects_router

app = FastAPI(title="BuildCrew Backend API")

# Configure CORS Middleware for Flutter Web, Desktop & Mobile
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*$",  # Compliant with allow_credentials=True across all local/web origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_check():
    from core.config import settings
    supabase_url = getattr(settings, "SUPABASE_URL", "")
    if not supabase_url or "placeholder" in supabase_url.lower() or "example" in supabase_url.lower():
        logger.warning(
            "⚠️ [LOCAL DEV FALLBACK MODE] Supabase URL is not configured. "
            "Backend will automatically run using local dev memory & file storage."
        )


# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.2f}ms)"
    )
    return response


# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(github_router)
app.include_router(contributions_router)

# Public Passport Endpoints
from typing import Optional
from routers.contributions import get_project_passport, get_user_passport
from schemas.contribution import ProjectPassportResponse, UserPassportResponse

@app.get(
    "/passport/{user_id}/{project_id}",
    response_model=ProjectPassportResponse,
    tags=["Passport"],
    summary="Get public project-scoped contribution passport",
)
@app.get(
    "/passport/{user_id}/{project_id}/",
    response_model=ProjectPassportResponse,
    tags=["Passport"],
    include_in_schema=False,
)
async def get_project_passport_endpoint(
    request: Request,
    user_id: str,
    project_id: str,
    format: Optional[str] = None,
):
    """
    Public (no-authentication-required) endpoint for viewing a builder's verified passport
    for a specific project. Returns ONLY published contributions, strictly excluding
    any unconfirmed, private, or disputed items.
    """
    passport_data = await get_project_passport(user_id, project_id)

    # If client specifically accepts text/html and passport.html exists, render Jinja2 template
    import os
    from core.templates import TEMPLATES_DIR, templates
    template_path = os.path.join(TEMPLATES_DIR, "passport.html")
    accept_header = request.headers.get("accept", "")

    if format != "json" and "text/html" in accept_header and os.path.exists(template_path):
        return templates.TemplateResponse(
            request=request,
            name="passport.html",
            context={
                "passport": passport_data.model_dump(),
                "user_id": user_id,
                "project_id": project_id,
            },
        )

    return passport_data


@app.get(
    "/users/{user_id}/passport",
    response_model=UserPassportResponse,
    tags=["Passport"],
    summary="Get public builder passport",
)
@app.get(
    "/users/{user_id}/passport/",
    response_model=UserPassportResponse,
    tags=["Passport"],
    include_in_schema=False,
)
async def get_user_passport_endpoint(user_id: str):
    """
    Public builder passport query for a user.
    Guarantees that ANY contribution with status 'needs-review', dispute_state 'disputed',
    or visibility 'private' is strictly excluded from the passport.
    """
    return await get_user_passport(user_id)


@app.get(
    "/users/{user_id}/contributions",
    response_model=UserPassportResponse,
    tags=["Passport"],
    summary="Get public user contributions",
)
@app.get(
    "/users/{user_id}/contributions/",
    response_model=UserPassportResponse,
    tags=["Passport"],
    include_in_schema=False,
)
async def get_user_contributions_endpoint(user_id: str):
    """
    Public user contributions query.
    Guarantees that ANY contribution with status 'needs-review', dispute_state 'disputed',
    or visibility 'private' is strictly excluded.
    """
    return await get_user_passport(user_id)


# Mount static files directory for local dev evidence uploads
import os
from fastapi.staticfiles import StaticFiles

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads", "evidence")
os.makedirs(uploads_dir, exist_ok=True)
app.mount(
    "/static/evidence",
    StaticFiles(directory=uploads_dir),
    name="static_evidence",
)




if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

