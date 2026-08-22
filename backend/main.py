import time
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.logging import logger
from routers.auth import router as auth_router
from routers.contributions import router as contributions_router
from routers.github import router as github_router
from routers.health import router as health_router
from routers.projects import router as projects_router

app = FastAPI(title="BuildCrew Backend API")

# Configure CORS Middleware for Flutter & Local Development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins during local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

