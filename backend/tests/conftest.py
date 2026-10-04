import pytest
from core.config import settings


@pytest.fixture(autouse=True)
def setup_dev_mode_for_existing_tests(monkeypatch):
    """
    Ensure existing dev-mode tests default to development environment
    and ALLOW_DEV_AUTH=true so local dev conveniences and fallbacks work.
    Specific production and auth-rejection tests will override these fixtures.
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", True)
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOW_DEV_AUTH", "true")


@pytest.fixture(autouse=True)
def reset_rate_limiter_for_tests():
    from core.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()

