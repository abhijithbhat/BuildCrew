from core.config import settings
from core.database import get_supabase_client, supabase

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_SERVICE_KEY = settings.SUPABASE_SERVICE_KEY

__all__ = ["get_supabase_client", "supabase", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
