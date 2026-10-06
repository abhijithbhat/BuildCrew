from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient
from core.config import settings
from core.dependencies import DevUser
from main import app, startup_check

client = TestClient(app)


def test_garbage_token_returns_401(monkeypatch):
    """Garbage token returns 401 with safe error message."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Invalid JWT token")

    with patch("core.dependencies.get_supabase_pub_client", return_value=mock_supabase):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer totally-invalid-garbage-token"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired authentication token"


def test_supabase_unreachable_returns_503_not_200(monkeypatch):
    """When Supabase is unreachable, return 503 (not 200, never OfflineDevUser)."""
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = httpx.ConnectError(
        "[Errno 8] nodename nor servname provided, or not known"
    )

    with patch("core.dependencies.get_supabase_pub_client", return_value=mock_supabase):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer some-token"},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Authentication service unavailable"


def test_mock_token_returns_401_when_allow_dev_auth_is_false(monkeypatch):
    """Mock dev token returns 401 when ALLOW_DEV_AUTH is False."""
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Invalid token")

    with patch("core.dependencies.get_supabase_pub_client", return_value=mock_supabase):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer mock-dev-access-token-test@example.com"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired authentication token"


def test_docs_returns_404_in_production(monkeypatch):
    """Swagger UI /docs returns 404 in production."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response_docs = client.get("/docs")
    assert response_docs.status_code == 404

    response_redoc = client.get("/redoc")
    assert response_redoc.status_code == 404

    response_openapi = client.get("/openapi.json")
    assert response_openapi.status_code == 404


def test_startup_check_raises_runtime_error_if_keys_missing_in_production(monkeypatch):
    """Startup check raises RuntimeError in production if required keys are missing."""
    import asyncio
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "")
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "prod-app-secret-12345")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "prod-webhook-secret-12345")

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(startup_check())

    assert "Missing required Supabase environment variables in production" in str(exc_info.value)
    assert "SUPABASE_URL" in str(exc_info.value)
    assert "SUPABASE_SERVICE_KEY" in str(exc_info.value)
    assert "SUPABASE_PUBLISHABLE_KEY" in str(exc_info.value)


def test_startup_check_succeeds_in_production_when_keys_present(monkeypatch):
    """Startup check succeeds in production when all keys are present."""
    import asyncio
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "service-key-123")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "pub-key-123")
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "prod-app-secret-12345")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "prod-webhook-secret-12345")

    # Should not raise any exception
    asyncio.run(startup_check())


def test_dev_user_init_no_name_error():
    """DevUser class properly initializes without NameError / UnboundLocalError."""
    user = DevUser(id="uid-42", email="builder@buildcrew.com")
    assert user.id == "uid-42"
    assert user.email == "builder@buildcrew.com"


def test_upstream_failure_in_projects_returns_503_in_production(monkeypatch):
    """Upstream Supabase failure in projects returns 503 outside development (never local DB fallback)."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", False)

    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("failed to connect: Connection refused")

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # Using dependency override for current_user
        app.dependency_overrides[app.router.dependencies[0].dependency if app.router.dependencies else None] = None
        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-prod-123", email="prod@example.com")

        try:
            response = client.post(
                "/projects",
                json={"name": "Prod Project", "description": "No fallback"},
                headers={"Authorization": "Bearer valid-jwt"},
            )
            assert response.status_code == 503
            assert "Database service unavailable" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
