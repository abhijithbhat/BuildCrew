import os
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    GEMINI_API_KEY: str = ""
    
    # GitHub App Integration
    GITHUB_APP_ID: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_APP_SLUG: str = ""
    GITHUB_PRIVATE_KEY_PATH: str = "github_private_key.pem"
    GITHUB_PRIVATE_KEY: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""

    model_config = SettingsConfigDict(
        env_file=(_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


