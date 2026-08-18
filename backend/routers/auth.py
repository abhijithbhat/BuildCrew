from fastapi import APIRouter, Depends, HTTPException, status
from core.database import get_supabase_client, get_supabase_pub_client
from core.dependencies import get_current_user
from schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignUpRequest,
    VerifyOTPRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# In-memory user store for Local Dev Mode when Supabase URL is unconfigured/offline
DEV_USERS_DB: dict[str, str] = {}
DEV_VERIFIED_USERS: set[str] = set()
DEV_USER_NAMES_DB: dict[str, str] = {}


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(credentials: SignUpRequest):
    supabase = get_supabase_pub_client()
    try:
        signup_payload = {
            "email": credentials.email,
            "password": credentials.password,
        }
        if credentials.name and credentials.name.strip():
            signup_payload["options"] = {
                "data": {
                    "display_name": credentials.name.strip(),
                    "full_name": credentials.name.strip(),
                    "name": credentials.name.strip(),
                }
            }
            DEV_USER_NAMES_DB[credentials.email.lower()] = credentials.name.strip()

        response = supabase.auth.sign_up(signup_payload)

        # Supabase returns a user with empty identities when the email is
        # already registered and confirmed (anti-enumeration pattern).
        # Detect this and tell the user to log in instead.
        user_identities = getattr(response.user, "identities", None)
        if response.user and (user_identities is not None and len(user_identities) == 0):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please log in.",
            )

        user_meta = getattr(response.user, "user_metadata", {}) or {} if response.user else {}
        display_name = user_meta.get("display_name") or user_meta.get("name") or credentials.name

        # For unconfirmed re-signups, Supabase automatically resends the OTP.
        # We return success so the user is navigated to the OTP screen.
        return {
            "message": "Verification code sent to your email.",
            "requires_otp": True,
            "email": credentials.email,
            "user": {
                "id": response.user.id if response.user else None,
                "email": response.user.email if response.user else None,
                "display_name": display_name,
            },
            "session": response.session,
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            # Store credentials in Local Dev DB
            DEV_USERS_DB[credentials.email.lower()] = credentials.password
            if credentials.name and credentials.name.strip():
                DEV_USER_NAMES_DB[credentials.email.lower()] = credentials.name.strip()
            return {
                "message": "Verification code sent to your email (Local Dev OTP: 123456)",
                "requires_otp": True,
                "email": credentials.email,
                "user": {
                    "id": f"dev-user-{hash(credentials.email) & 0xffff}",
                    "email": credentials.email,
                    "display_name": credentials.name,
                },
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.post("/verify-otp", status_code=status.HTTP_200_OK)
async def verify_otp(req: VerifyOTPRequest):
    supabase = get_supabase_pub_client()
    try:
        response = supabase.auth.verify_otp(
            {
                "email": req.email,
                "token": req.token,
                "type": req.type,
            }
        )
        user_meta = getattr(response.user, "user_metadata", {}) or {} if response.user else {}
        display_name = user_meta.get("display_name") or user_meta.get("name") or user_meta.get("full_name") or DEV_USER_NAMES_DB.get(req.email.lower())
        if not display_name and response.user:
            try:
                prof = supabase.table("profiles").select("display_name, full_name").eq("id", response.user.id).single().execute()
                if prof.data:
                    display_name = prof.data.get("display_name") or prof.data.get("full_name")
            except Exception:
                pass

        return {
            "message": "OTP verified successfully",
            "access_token": response.session.access_token if response.session else "mock-access-token",
            "refresh_token": response.session.refresh_token if response.session else "mock-refresh-token",
            "user": {
                "id": response.user.id if response.user else None,
                "email": response.user.email if response.user else req.email,
                "display_name": display_name,
            },
        }

    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            # Accept "123456" as universal Dev Mode OTP
            if req.token.strip() != "123456":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid verification code. Use dev OTP: 123456",
                )
            DEV_VERIFIED_USERS.add(req.email.lower())
            return {
                "message": "OTP verified successfully (Local Dev Mode)",
                "access_token": f"mock-dev-access-token-{req.email}",
                "refresh_token": f"mock-dev-refresh-token-{req.email}",
                "user": {
                    "id": f"dev-user-{hash(req.email) & 0xffff}",
                    "email": req.email,
                    "display_name": DEV_USER_NAMES_DB.get(req.email.lower()),
                },
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,

            detail=err_msg,
        )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(req: ForgotPasswordRequest):
    supabase = get_supabase_pub_client()
    try:
        supabase.auth.reset_password_for_email(req.email)
        return {
            "message": f"Password reset OTP sent to {req.email}",
            "email": req.email,
        }
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            email_key = req.email.lower()
            if email_key not in DEV_USERS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account found with this email address.",
                )
            return {
                "message": f"Password reset code sent to {req.email} (Local Dev OTP: 123456)",
                "email": req.email,
            }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_msg,
        )


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(req: ResetPasswordRequest):
    supabase = get_supabase_pub_client()
    try:
        # Verify OTP code and update password
        supabase.auth.verify_otp(
            {
                "email": req.email,
                "token": req.token,
                "type": "recovery",
            }
        )
        return {"message": "Password reset successfully. Please log in with your new password."}
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            if req.token.strip() != "123456":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid reset code. Use dev OTP: 123456",
                )
            email_key = req.email.lower()
            if email_key not in DEV_USERS_DB:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account found with this email address.",
                )
            DEV_USERS_DB[email_key] = req.new_password
            return {"message": "Password reset successfully (Local Dev Mode). Please log in."}
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
        user_meta = getattr(response.user, "user_metadata", {}) or {} if response.user else {}
        display_name = user_meta.get("display_name") or user_meta.get("name") or user_meta.get("full_name") or DEV_USER_NAMES_DB.get(credentials.email.lower())
        if not display_name and response.user:
            try:
                prof = supabase.table("profiles").select("display_name, full_name").eq("id", response.user.id).single().execute()
                if prof.data:
                    display_name = prof.data.get("display_name") or prof.data.get("full_name")
            except Exception:
                pass


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
                "display_name": display_name,
            },
            "session": response.session,
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "nodename nor servname provided" in err_msg or "gai_error" in err_msg or "Name or service not known" in err_msg:
            email_key = credentials.email.lower()
            if email_key not in DEV_USERS_DB:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not registered. Please sign up first.",
                )
            if DEV_USERS_DB[email_key] != credentials.password:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid login credentials.",
                )
            return {
                "message": "Login successful (Local Dev Mode)",
                "access_token": f"mock-dev-access-token-{credentials.email}",
                "refresh_token": f"mock-dev-refresh-token-{credentials.email}",
                "token_type": "bearer",
                "expires_in": 3600,
                "expires_at": 1700000000,
                "user": {
                    "id": f"dev-user-{hash(credentials.email) & 0xffff}",
                    "email": credentials.email,
                    "display_name": DEV_USER_NAMES_DB.get(email_key),
                },
                "session": {

                    "access_token": f"mock-dev-access-token-{credentials.email}",
                    "refresh_token": f"mock-dev-refresh-token-{credentials.email}",
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
