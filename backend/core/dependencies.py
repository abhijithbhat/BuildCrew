import hashlib
from typing import Any, Optional
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from core.config import settings
from core.database import get_supabase_pub_client, is_dev_mode
from core.logging import logger

security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def stable_dev_user_id(email: str) -> str:
    """Generate a deterministic, stable dev-mode user ID for an email across process restarts."""
    cleaned = (email or "").lower().strip()
    short_hash = hashlib.md5(cleaned.encode("utf-8")).hexdigest()[:8]
    return f"dev-user-{short_hash}"


class DevUser:
    """Local development mock user."""
    def __init__(self, id: str, email: str):
        self.id = id
        self.email = email


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """FastAPI dependency to verify Supabase JWT token and extract current user."""
    token = credentials.credentials

    # Local dev mock access token convenience ONLY when explicitly allowed in development
    if (
        settings.ALLOW_DEV_AUTH
        and settings.ENVIRONMENT == "development"
        and token.startswith("mock-dev-access-token-")
    ):
        email = token.replace("mock-dev-access-token-", "")
        user_id = stable_dev_user_id(email)
        return DevUser(id=user_id, email=email)

    try:
        supabase = get_supabase_pub_client()
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_response.user
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Supabase auth validation failed")

        err_msg = str(e).lower()
        is_network_or_config = (
            isinstance(e, (httpx.RequestError, ValueError))
            or any(
                s in err_msg
                for s in (
                    "nodename nor servname provided",
                    "gai_error",
                    "name or service not known",
                    "connection refused",
                    "failed to connect",
                    "connecterror",
                    "timeout",
                    "network",
                    "configured in environment variables",
                    "service unavailable",
                    "cannot connect",
                )
            )
        )

        if is_network_or_config:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
                headers={"WWW-Authenticate": "Bearer"},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[Any]:
    """Optional FastAPI dependency allowing unauthenticated access while identifying authenticated users."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException as e:
        if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            raise
        return None
    except Exception:
        return None



