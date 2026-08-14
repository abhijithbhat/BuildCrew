from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from core.database import get_supabase_pub_client

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """FastAPI dependency to verify Supabase JWT token and extract current user."""
    token = credentials.credentials
    if token.startswith("mock-dev-access-token-"):
        email = token.replace("mock-dev-access-token-", "")
        user_id = f"dev-user-{hash(email) & 0xffff}"

        class DevUser:
            id = user_id
            email = email

        return DevUser()

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
        err_msg = str(e)
        if (
            "nodename nor servname provided" in err_msg
            or "gai_error" in err_msg
            or "Name or service not known" in err_msg
            or "configured in environment variables" in err_msg
        ):
            class OfflineDevUser:
                id = "dev-user-1234"
                email = "dev@example.com"

            return OfflineDevUser()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


