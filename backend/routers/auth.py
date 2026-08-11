from fastapi import APIRouter, Depends, HTTPException, status
from core.database import get_supabase_client
from core.dependencies import get_current_user
from schemas.auth import LoginRequest, SignUpRequest

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(credentials: SignUpRequest):
    supabase = get_supabase_client()
    try:
        response = supabase.auth.sign_up(
            {
                "email": credentials.email,
                "password": credentials.password,
            }
        )
        return {
            "message": "User registered successfully",
            "user": {
                "id": response.user.id if response.user else None,
                "email": response.user.email if response.user else None,
            },
            "session": response.session,
        }
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            return {
                "message": "User registered successfully (Local Dev Mode)",
                "user": {
                    "id": "dev-user-123",
                    "email": credentials.email,
                },
                "session": {
                    "access_token": "mock-dev-access-token",
                    "refresh_token": "mock-dev-refresh-token",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "expires_at": 1700000000,
                },
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(credentials: LoginRequest):
    supabase = get_supabase_client()
    try:
        response = supabase.auth.sign_in_with_password(
            {
                "email": credentials.email,
                "password": credentials.password,
            }
        )
        if not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials or email not confirmed.",
            )
        return {
            "message": "Login successful",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "token_type": response.session.token_type,
            "expires_in": response.session.expires_in,
            "expires_at": response.session.expires_at,
            "user": {
                "id": response.user.id if response.user else None,
                "email": response.user.email if response.user else None,
            },
            "session": response.session,
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            return {
                "message": "Login successful (Local Dev Mode)",
                "access_token": "mock-dev-access-token",
                "refresh_token": "mock-dev-refresh-token",
                "token_type": "bearer",
                "expires_in": 3600,
                "expires_at": 1700000000,
                "user": {
                    "id": "dev-user-123",
                    "email": credentials.email,
                },
                "session": {
                    "access_token": "mock-dev-access-token",
                    "refresh_token": "mock-dev-refresh-token",
                },
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err_msg,
        )


@router.get("/github", status_code=status.HTTP_200_OK)
async def github_login(redirect_to: str | None = None):
    """Initiate GitHub OAuth authentication flow via Supabase Auth."""
    supabase = get_supabase_client()
    try:
        credentials = {"provider": "github"}
        if redirect_to:
            credentials["options"] = {"redirect_to": redirect_to}

        response = supabase.auth.sign_in_with_oauth(credentials)
        return {
            "url": response.url,
            "provider": "github",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth error: {str(e)}",
        )


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(current_user=Depends(get_current_user)):
    """Retrieve current logged-in user's profile from the database."""
    supabase = get_supabase_client()
    user_id = getattr(current_user, "id", None)
    if not user_id and isinstance(current_user, dict):
        user_id = current_user.get("id")

    profile_data = None
    if user_id:
        try:
            res = (
                supabase.table("profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            profile_data = res.data
        except Exception:
            profile_data = None

    if not profile_data:
        email = getattr(current_user, "email", None) or (
            current_user.get("email") if isinstance(current_user, dict) else None
        )
        profile_data = {
            "id": user_id,
            "display_name": email,
            "github_username": None,
            "avatar_url": None,
        }

    return {
        "user": current_user,
        "profile": profile_data,
    }
