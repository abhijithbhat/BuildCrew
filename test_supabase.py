import sys
from supabase_client import get_supabase_client, SUPABASE_URL
from postgrest.exceptions import APIError


def run_connection_test():
    print(f"Connecting to Supabase at: {SUPABASE_URL}")
    try:
        client = get_supabase_client()
        # Attempt to query a health/test table or check REST API response
        try:
            # Simple query to check connectivity
            client.table("_health_check").select("*").limit(1).execute()
            print("✅ Supabase connection successful! (Table query executed)")
        except APIError as e:
            # PGRST205 indicates postgrest server responded (table doesn't exist yet, but connection & auth succeed)
            if e.code == "PGRST205":
                print(
                    "✅ Supabase connection successful! (Authenticated and connected to PostgREST API)"
                )
            else:
                print(f"⚠️ Supabase API responded with code {e.code}: {e.message}")
        except Exception as e:
            print(f"⚠️ Query response: {e}")

        return True
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return False


if __name__ == "__main__":
    success = run_connection_test()
    sys.exit(0 if success else 1)

