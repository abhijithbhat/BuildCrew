from supabase import create_client, Client
from core.config import settings


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
    key = settings.SUPABASE_PUBLISHABLE_KEY or settings.SUPABASE_SERVICE_KEY
    if not settings.SUPABASE_URL or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured in environment variables."
        )
    return create_client(settings.SUPABASE_URL, key)


# Global Supabase client instance
supabase: Client | None = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
    supabase = create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
    )
