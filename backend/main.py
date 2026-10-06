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

from core.config import settings
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from core.rate_limit import limiter, rate_limit_exceeded_handler

is_prod = settings.ENVIRONMENT == "production"

app = FastAPI(
    title="BuildCrew Backend API",
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
)

# Attach slowapi rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global fallback exception handler returning user-safe 500 error for unhandled exceptions."""
    logger.exception(f"Unhandled exception while processing {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again."},
        headers={
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        },
    )

# Configure CORS Middleware for Flutter Web, Desktop & Mobile
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cache_json_body_middleware(request: Request, call_next):
    """Cache raw JSON body on request.state so rate limiting key functions can read email synchronously."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        request.state._cached_body = await request.body()
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def gate_docs_middleware(request: Request, call_next):
    if settings.ENVIRONMENT == "production":
        if request.url.path in ("/docs", "/docs/", "/redoc", "/redoc/", "/openapi.json"):
            res = JSONResponse(status_code=404, content={"detail": "Not Found"})
            res.headers["X-Content-Type-Options"] = "nosniff"
            res.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            res.headers["X-Frame-Options"] = "DENY"
            res.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            return res
    return await call_next(request)


@app.on_event("startup")
async def startup_check():
    from core.config import settings
    if settings.ENVIRONMENT == "production":
        missing_supabase = []
        if not getattr(settings, "SUPABASE_URL", ""):
            missing_supabase.append("SUPABASE_URL")
        if not getattr(settings, "SUPABASE_SERVICE_KEY", ""):
            missing_supabase.append("SUPABASE_SERVICE_KEY")
        if not getattr(settings, "SUPABASE_PUBLISHABLE_KEY", ""):
            missing_supabase.append("SUPABASE_PUBLISHABLE_KEY")
        if missing_supabase:
            raise RuntimeError(
                f"Missing required Supabase environment variables in production: {', '.join(missing_supabase)}"
            )

        missing_app = []
        if not getattr(settings, "APP_SECRET_KEY", ""):
            missing_app.append("APP_SECRET_KEY")
        if not getattr(settings, "GITHUB_WEBHOOK_SECRET", ""):
            missing_app.append("GITHUB_WEBHOOK_SECRET")
        if missing_app:
            raise RuntimeError(
                f"Missing required environment variables in production: {', '.join(missing_app)}"
            )
    else:
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
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

