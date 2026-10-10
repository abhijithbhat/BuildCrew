import os
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from core.config import settings
from core.rate_limit import limiter, get_ip_key, get_email_key, get_global_key, get_ip_email_key
from core.database import (
    get_supabase_client,
    get_supabase_pub_client,
    create_client,
    _is_dev_fallback_error,
    is_dev_mode,
)
try:
    from supabase import AuthApiError
except ImportError:
    class AuthApiError(Exception):
        pass
from core.dependencies import get_current_user, stable_dev_user_id
from core.logging import logger
from core.errors import handle_route_error
from schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    SignUpRequest,
    VerifyOTPRequest,
)
from services.github_service import generate_app_jwt

router = APIRouter(prefix="/auth", tags=["Authentication"])


# In-memory user store for Local Dev Mode when Supabase URL is unconfigured/offline
DEV_USERS_DB: dict[str, str] = {}
DEV_VERIFIED_USERS: set[str] = set()
DEV_USER_NAMES_DB: dict[str, str] = {}


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour", key_func=get_email_key)
@limiter.limit("20/hour", key_func=get_ip_key)
@limiter.limit("200/hour", key_func=get_global_key)
async def signup(request: Request, credentials: SignUpRequest):
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
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
            # Store credentials in Local Dev DB
            DEV_USERS_DB[credentials.email.lower()] = credentials.password
            if credentials.name and credentials.name.strip():
                DEV_USER_NAMES_DB[credentials.email.lower()] = credentials.name.strip()
            return {
                "message": "Verification code sent to your email (Local Dev OTP: 123456)",
                "requires_otp": True,
                "email": credentials.email,
                "user": {
                    "id": stable_dev_user_id(credentials.email),
                    "email": credentials.email,
                    "display_name": credentials.name,
                },
            }
        logger.warning(f"Signup failed for {credentials.email}: {err_msg}")
        err_lower = err_msg.lower()
        if any(s in err_lower for s in ("already registered", "already exists", "user already registered")):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Please log in.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request failed. Please try again.",
        )


@router.post("/verify-otp", status_code=status.HTTP_200_OK)
@limiter.limit("10/15minute", key_func=get_email_key)
@limiter.limit("60/15minute", key_func=get_ip_key)
async def verify_otp(request: Request, req: VerifyOTPRequest):
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

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
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
                    "id": stable_dev_user_id(req.email),
                    "email": req.email,
                    "display_name": DEV_USER_NAMES_DB.get(req.email.lower()),
                },
            }
        logger.warning(f"Verify OTP failed for {req.email}: {err_msg}")
        err_lower = err_msg.lower()
        if any(s in err_lower for s in ("expired", "invalid", "otp", "token", "code")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired code.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request failed. Please try again.",
        )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/hour", key_func=get_email_key)
@limiter.limit("20/hour", key_func=get_ip_key)
async def forgot_password(request: Request, req: ForgotPasswordRequest):
    supabase = get_supabase_pub_client()
    try:
        supabase.auth.reset_password_for_email(req.email)
        return {
            "message": f"Password reset OTP sent to {req.email}",
            "email": req.email,
        }
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
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
        logger.warning(f"Forgot password failed for {req.email}: {err_msg}")
        err_lower = err_msg.lower()
        if "email not confirmed" in err_lower or "email not verified" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your email first.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request failed. Please try again.",
        )


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("10/15minute", key_func=get_email_key)
@limiter.limit("60/15minute", key_func=get_ip_key)
async def reset_password(request: Request, req: ResetPasswordRequest):
    supabase = get_supabase_pub_client()
    try:
        # Verify OTP code
        response = supabase.auth.verify_otp(
            {
                "email": req.email,
                "token": req.token,
                "type": "recovery",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
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
        logger.warning(f"Reset password failed for {req.email}: {err_msg}")
        err_lower = err_msg.lower()
        if any(s in err_lower for s in ("expired", "invalid", "otp", "token", "code")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired code.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request failed. Please try again.",
        )

    user_id = None
    if response and getattr(response, "user", None):
        user_id = getattr(response.user, "id", None)
    elif isinstance(response, dict) and "user" in response:
        u = response["user"]
        user_id = u.get("id") if isinstance(u, dict) else getattr(u, "id", None)

    admin_client = get_supabase_client()
    try:
        if not user_id:
            raise ValueError("No user ID found in verify_otp response")
        admin_client.auth.admin.update_user_by_id(str(user_id), {"password": req.new_password})
    except Exception as e:
        logger.exception(f"Could not reset password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not reset password. Please try again.",
        )

    # Best-effort session revocation
    try:
        if response and getattr(response, "session", None) and getattr(response.session, "access_token", None):
            admin_client.auth.admin.sign_out(response.session.access_token)
    except Exception:
        pass

    return {"message": "Password reset successfully. Please log in with your new password."}


@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("10/15minute", key_func=get_email_key)
@limiter.limit("60/15minute", key_func=get_ip_key)
async def login(request: Request, credentials: LoginRequest):
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
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
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
                    "id": stable_dev_user_id(credentials.email),
                    "email": credentials.email,
                    "display_name": DEV_USER_NAMES_DB.get(email_key),
                },
                "session": {

                    "access_token": f"mock-dev-access-token-{credentials.email}",
                    "refresh_token": f"mock-dev-refresh-token-{credentials.email}",
                },
            }
        logger.warning(f"Login failed for {credentials.email}: {err_msg}")
        err_lower = err_msg.lower()
        if (
            "invalid login credentials" in err_lower
            or "invalid credentials" in err_lower
            or "invalid login" in err_lower
            or "invalid email or password" in err_lower
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        if "email not confirmed" in err_lower or "email not verified" in err_lower:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your email first.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request failed. Please try again.",
        )


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_token(payload: RefreshTokenRequest):
    """
    Refresh an expired access token using a valid refresh token.
    Calls Supabase auth.refresh_session(refresh_token).
    Returns new access_token, refresh_token, token_type, expires_in, and expires_at.
    Returns 401 Unauthorized with INVALID_REFRESH_TOKEN if refresh token is invalid or expired.
    """
    raw_token = (payload.refresh_token or "").strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_REFRESH_TOKEN: Refresh token is required",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Refresh token is required\""},
        )

    # Local Dev Mode fallback if token matches mock pattern
    if raw_token.startswith("mock-dev-refresh-token-"):
        if not is_dev_mode():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_REFRESH_TOKEN: Invalid or expired refresh token. Please log in again.",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Refresh token is expired or invalid\""},
            )
        email = raw_token.replace("mock-dev-refresh-token-", "")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return {
            "message": "Token refreshed successfully (Local Dev Mode)",
            "access_token": f"mock-dev-access-token-{email}",
            "refresh_token": f"mock-dev-refresh-token-{email}",
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": now_ts + 3600,
            "user": {
                "id": stable_dev_user_id(email),
                "email": email,
                "display_name": DEV_USER_NAMES_DB.get(email.lower(), email),
            },
        }

    supabase = get_supabase_pub_client()
    try:
        response = supabase.auth.refresh_session(raw_token)
        if not response or not response.session or not response.session.access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="INVALID_REFRESH_TOKEN: Invalid or expired refresh token. Please log in again.",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Refresh token is expired or invalid\""},
            )

        user_meta = getattr(response.user, "user_metadata", {}) or {} if response.user else {}
        display_name = (
            user_meta.get("display_name")
            or user_meta.get("name")
            or user_meta.get("full_name")
        )
        if not display_name and response.user:
            try:
                prof = (
                    supabase.table("profiles")
                    .select("display_name, full_name")
                    .eq("id", response.user.id)
                    .single()
                    .execute()
                )
                if prof.data:
                    display_name = prof.data.get("display_name") or prof.data.get("full_name")
            except Exception:
                pass

        return {
            "message": "Token refreshed successfully",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "token_type": response.session.token_type or "bearer",
            "expires_in": response.session.expires_in,
            "expires_at": response.session.expires_at,
            "user": {
                "id": response.user.id if response.user else None,
                "email": response.user.email if response.user else None,
                "display_name": display_name,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if _is_dev_fallback_error(err_msg, service_name="Authentication"):
            if raw_token.startswith("mock-dev-refresh-token-"):
                email = raw_token.replace("mock-dev-refresh-token-", "")
                now_ts = int(datetime.now(timezone.utc).timestamp())
                return {
                    "message": "Token refreshed successfully (Local Dev Mode)",
                    "access_token": f"mock-dev-access-token-{email}",
                    "refresh_token": f"mock-dev-refresh-token-{email}",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "expires_at": now_ts + 3600,
                    "user": {
                        "id": stable_dev_user_id(email),
                        "email": email,
                        "display_name": DEV_USER_NAMES_DB.get(email.lower(), email),
                    },
                }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_REFRESH_TOKEN: Invalid or expired refresh token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"Refresh token is expired or invalid\""},
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
        raise handle_route_error(
            e,
            generic_message="Failed to initiate GitHub authentication. Please try again.",
            log_message="GitHub OAuth initiation failed",
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


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(current_user=Depends(get_current_user)):
    """Permanently delete user profile, personal projects, credentials, and Supabase auth user.
    
    Never returns 200 unless the Supabase auth user was actually deleted.
    """
    user_id = getattr(current_user, "id", None)
    email = getattr(current_user, "email", None)
    if not user_id and isinstance(current_user, dict):
        user_id = current_user.get("id")
        email = current_user.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to delete account.",
        )

    try:
        supabase = get_supabase_client()

        # Step 2a: For each project created by the user
        owned_res = supabase.table("projects").select("id").eq("created_by", user_id).execute()
        owned_projects = owned_res.data or []
        for proj in owned_projects:
            pid = proj["id"]
            members_res = (
                supabase.table("project_members")
                .select("user_id, joined_at")
                .eq("project_id", pid)
                .order("joined_at", desc=False)
                .execute()
            )

            other_members = [
                m for m in (members_res.data or [])
                if str(m.get("user_id")) != str(user_id)
            ]

            if other_members:
                # Transfer ownership to the EARLIEST-JOINED other member
                next_owner = other_members[0]["user_id"]
                upd_res = (
                    supabase.table("projects")
                    .update({"created_by": next_owner})
                    .eq("id", pid)
                    .execute()
                )
                if not upd_res.data or len(upd_res.data) != 1:
                    raise RuntimeError(
                        f"Expected exactly 1 project row updated for {pid}, got {len(upd_res.data) if upd_res.data else 0}"
                    )
            else:
                # User is the only member: delete project and its dependents
                # Before deleting github_installations row, call GitHub DELETE /app/installations/{installation_id}
                # Only call GitHub's DELETE /app/installations/{id} when no OTHER github_installations row references the same installation_id (the uninstall removes the app from the whole GitHub account).
                gh_res = (
                    supabase.table("github_installations")
                    .select("installation_id")
                    .eq("project_id", pid)
                    .execute()
                )

                for inst in (gh_res.data or []):
                    installation_id = inst.get("installation_id")
                    if installation_id:
                        # Check if another project row references this installation_id
                        other_inst_res = (
                            supabase.table("github_installations")
                            .select("project_id")
                            .eq("installation_id", str(installation_id))
                            .neq("project_id", pid)
                            .execute()
                        )
                        has_other = bool(isinstance(other_inst_res.data, (list, tuple)) and len(other_inst_res.data) > 0)
                        if is_dev_mode():
                            from services.github_service import DEV_GITHUB_INSTALLATIONS_DB
                            if any(
                                other_pid != pid and str(inst_data.get("installation_id")) == str(installation_id)
                                for other_pid, inst_data in DEV_GITHUB_INSTALLATIONS_DB.items()
                            ):
                                has_other = True

                        if not has_other:
                            app_jwt = generate_app_jwt()
                            if app_jwt:
                                async with httpx.AsyncClient() as http_client:
                                    gh_resp = await http_client.delete(
                                        f"https://api.github.com/app/installations/{installation_id}",
                                        headers={
                                            "Authorization": f"Bearer {app_jwt}",
                                            "Accept": "application/vnd.github+json",
                                            "X-GitHub-Api-Version": "2022-11-28",
                                        },
                                    )
                                    if gh_resp.status_code != 404 and (gh_resp.status_code < 200 or gh_resp.status_code >= 300):
                                        raise RuntimeError(
                                            f"Failed to uninstall GitHub App installation {installation_id}: HTTP {gh_resp.status_code}"
                                        )
                            elif getattr(settings, "GITHUB_APP_ID", None):
                                raise RuntimeError("Failed to generate GitHub App JWT for uninstallation.")
                        else:
                            logger.info(
                                f"Skipping GitHub App uninstallation for installation_id {installation_id} "
                                f"because it is referenced by other projects."
                            )

                supabase.table("contributions").delete().eq("project", pid).execute()
                supabase.table("role_agreements").delete().eq("project_id", pid).execute()
                supabase.table("github_installations").delete().eq("project_id", pid).execute()
                supabase.table("project_members").delete().eq("project_id", pid).execute()
                supabase.table("projects").delete().eq("id", pid).execute()

        # Step 2b: Delete every object under "{user_id}/" in the "evidence" storage bucket (capped at 50 iterations)
        storage_bucket = supabase.storage.from_("evidence")
        objects_still_present = True
        for _ in range(50):
            list_res = storage_bucket.list(path=str(user_id))
            if not list_res:
                objects_still_present = False
                break
            paths_to_remove = [
                f"{user_id}/{obj['name']}"
                for obj in list_res
                if isinstance(obj, dict) and obj.get("name")
            ]
            if not paths_to_remove:
                objects_still_present = False
                break
            storage_bucket.remove(paths_to_remove)

        if objects_still_present:
            remaining_objects = storage_bucket.list(path=str(user_id))
            if remaining_objects:
                raise RuntimeError(
                    f"Storage cleanup could not remove all objects for user {user_id} after 50 iterations."
                )

        # Step 2c: Call supabase.auth.admin.delete_user(user_id) with the service-role client
        if not hasattr(supabase, "auth") or not hasattr(supabase.auth, "admin"):
            raise RuntimeError("Supabase client lacks admin auth service.")

        supabase.auth.admin.delete_user(str(user_id))

        # Step 4: After deletion, confirm via supabase.auth.admin.get_user_by_id that the user no longer exists
        still_exists = False
        try:
            check_user = supabase.auth.admin.get_user_by_id(str(user_id))
            if check_user is not None and getattr(check_user, "user", None) is not None:
                still_exists = True
        except AuthApiError as e:
            status_code = getattr(e, "status", None)
            err_msg = str(getattr(e, "message", "") or str(e)).lower()
            code = str(getattr(e, "code", "") or "").lower()
            if status_code == 404 or "not found" in err_msg or "not_found" in code or "404" in err_msg:
                still_exists = False
            else:
                logger.error(f"AuthApiError verifying user deletion for {user_id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete account. Please try again.",
                )
        except Exception as e:
            err_msg = str(e).lower()
            if "not found" in err_msg or "not_found" in err_msg:
                still_exists = False
            else:
                logger.error(f"Unexpected error verifying user deletion for {user_id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete account. Please try again.",
                )

        if still_exists:
            raise RuntimeError(f"User {user_id} still exists in Supabase auth after deletion.")

        # Clean up local development mock stores
        if email:
            DEV_USERS_DB.pop(email.lower(), None)
            DEV_VERIFIED_USERS.discard(email.lower())
            DEV_USER_NAMES_DB.pop(email.lower(), None)

        return {
            "status": "success",
            "message": "Account and associated data deleted successfully.",
            "user_id": user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise handle_route_error(
            e,
            generic_message="Failed to delete account. Please try again.",
            log_message=f"Failed to delete account for user {user_id}",
        )

