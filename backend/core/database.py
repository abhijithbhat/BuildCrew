from fastapi import HTTPException, status
from supabase import create_client, Client
from core.config import settings
from core.logging import logger


def get_supabase_client() -> Client:
    """Retrieve an initialized Supabase Client instance (Service Role).

    Raises ValueError if required environment variables are missing.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be configured in environment variables."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def get_supabase_pub_client() -> Client:
    """Retrieve Supabase Client initialized with Publishable/Anon key for user token verification."""
    key = settings.SUPABASE_PUBLISHABLE_KEY
    if not settings.SUPABASE_URL or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured in environment variables."
        )
    return create_client(settings.SUPABASE_URL, key)


def is_dev_mode() -> bool:
    """Check if local dev conveniences and in-memory mock stores are enabled."""
    return bool(settings.ALLOW_DEV_AUTH and settings.ENVIRONMENT == "development")


def _is_dev_fallback_error(err_msg: str, service_name: str = "Database") -> bool:
    """
    Check if an upstream error matches dev fallback conditions.
    Outside development, an upstream failure raises HTTP 503 and never falls back.
    """
    err_lower = str(err_msg).lower()
    matched = any(
        s in err_lower
        for s in (
            "nodename nor servname provided",
            "gai_error",
            "name or service not known",
            "supabase_url",
            "environment variables",
            "failed to connect",
            "client disconnected",
            "connection refused",
            "connection",
            "connect",
            "connecterror",
            "timeout",
            "network",
            "invalid api key",
            "unauthorized",
            "pgrst",
            "postgrest",
            "mock",
            "invalid input syntax for type uuid",
            "22p02",
            "violates foreign key constraint",
            "foreign key",
            "23503",
            "is not present in table",
            "dev_fallback",
            "local dev fallback",
            "service unavailable",
            "cannot connect",
            "bucket",
            "storage",
        )
    )
    if not matched:
        return False

    if not is_dev_mode():
        logger.warning(
            f"Upstream Supabase failure in production/non-dev mode: {err_msg[:120]}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{service_name} service unavailable",
        )

    logger.warning(
        f"⚠️ [LOCAL DEV FALLBACK] Supabase unavailable ({err_msg[:80]}). "
        "Data is being read/written to Local Dev Store."
    )
    return True


# Global Supabase client instance
supabase: Client | None = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
    supabase = create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
    )

