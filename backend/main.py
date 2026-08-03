import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from core.logging import logger
from routers.auth import router as auth_router
from routers.health import router as health_router

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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
