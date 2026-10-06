"""
Rate limiting configuration and custom key functions using slowapi.
Supports:
- IP-based rate limiting
- IP + Email-based rate limiting
- User-based rate limiting (with test mock & JWT support)
- Real client IP extraction behind proxies (e.g. Render / Cloudflare)
- 429 Too Many Requests response with standard Retry-After header
"""

import base64
import hashlib
import json
import time
from typing import Any, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def get_real_client_ip(request: Request) -> str:
    """
    Extract real client IP address.
    In development use request.client.host.
    Otherwise read ONLY the X-Real-IP header (Railway overwrites it with the real client IP);
    if it is missing return the literal "unknown".
    Never read X-Forwarded-For anywhere.
    """
    from core.config import settings

    if getattr(settings, "ENVIRONMENT", "").lower() == "development":
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    return "unknown"


def get_ip_key(request: Request) -> str:
    """Rate limit key based strictly on client IP."""
    return get_real_client_ip(request)


def get_email_key(request: Request) -> str:
    """
    Rate limit key based on the lowercased email from the cached JSON body:
    "email:<lowercased email from the cached JSON body>",
    falling back to the IP key when there is no email.
    """
    email = ""
    cached_body = getattr(request.state, "_cached_body", None)
    if cached_body is None:
        cached_body = getattr(request, "_body", None)

    if cached_body:
        try:
            if isinstance(cached_body, bytes):
                payload = json.loads(cached_body.decode("utf-8"))
            elif isinstance(cached_body, str):
                payload = json.loads(cached_body)
            elif isinstance(cached_body, dict):
                payload = cached_body
            else:
                payload = {}

            if isinstance(payload, dict):
                raw_email = payload.get("email")
                if raw_email:
                    email = str(raw_email).strip().lower()
        except Exception:
            pass

    if email:
        return f"email:{email}"
    return get_ip_key(request)


def get_global_key(request: Request) -> str:
    """Constant rate limit key for global/endpoint-wide rate limiting."""
    return "global"


get_constant_key = get_global_key


def get_ip_email_key(request: Request) -> str:
    """Legacy rate limit key combining client IP and lowercased email address."""
    ip = get_real_client_ip(request)
    email_key = get_email_key(request)
    if email_key.startswith("email:"):
        return f"{ip}:{email_key[6:]}"
    return ip


def _extract_user_id_from_jwt(token: str) -> Optional[str]:
    """Extract user subject ID from JWT payload without verification (for rate-limit keying)."""
    parts = token.split(".")
    if len(parts) == 3:
        try:
            payload_b64 = parts[1]
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
            user_id = claims.get("sub") or claims.get("id")
            if user_id:
                return str(user_id)
        except Exception:
            pass
    return None


def get_user_key(request: Request) -> str:
    """
    Rate limit key based on the authenticated user.
    Checks test dependency overrides, Authorization Bearer token, or falls back to IP.
    """
    # 1. Check dependency_overrides (for pytest test suites)
    try:
        from core.dependencies import get_current_user
        override = request.app.dependency_overrides.get(get_current_user)
        if override:
            user = override() if callable(override) else override
            if hasattr(user, "id"):
                return f"user:{user.id}"
            if isinstance(user, dict) and "id" in user:
                return f"user:{user['id']}"
    except Exception:
        pass

    # 2. Extract user ID from Authorization header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        jwt_user_id = _extract_user_id_from_jwt(token)
        if jwt_user_id:
            return f"user:{jwt_user_id}"
        # For non-JWT mock tokens (e.g. dev mock tokens), hash the token
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
        return f"user:{token_hash}"

    # 3. Fallback to client IP if unauthenticated
    return get_real_client_ip(request)


# Global Limiter instance configured for endpoint key style
limiter = Limiter(
    key_func=get_real_client_ip,
    key_style="endpoint",
    headers_enabled=False,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom exception handler returning HTTP 429 with Retry-After header."""
    retry_after = 60
    view_rate_limit = getattr(request.state, "view_rate_limit", None)
    if view_rate_limit and hasattr(limiter, "limiter"):
        try:
            window_stats = limiter.limiter.get_window_stats(view_rate_limit[0], *view_rate_limit[1])
            reset_in = 1 + window_stats[0]
            retry_after = max(1, int(reset_in - time.time()))
        except Exception:
            retry_after = 60

    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={
            "Retry-After": str(retry_after),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        },
    )
