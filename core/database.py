from supabase import create_client, Client
from core.config import settings


def get_supabase_client() -> Client:
    """Retrieve an initialized Supabase Client instance.

    Raises ValueError if required environment variables are missing.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be configured in environment variables."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


# Global Supabase client instance
supabase: Client | None = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
    supabase = create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
    )
