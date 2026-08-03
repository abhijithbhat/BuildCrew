from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_signup_endpoint_success():
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.user = MagicMock(id="user-123", email="test@example.com")
    mock_response.session = None
    mock_supabase.auth.sign_up.return_value = mock_response

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/auth/signup",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "User registered successfully"
        assert data["user"]["id"] == "user-123"
        assert data["user"]["email"] == "test@example.com"


def test_signup_endpoint_failure():
    with patch("routers.auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_up.side_effect = Exception("Invalid email format")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/auth/signup",
            json={"email": "invalid-email", "password": "pass"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid email format"


def test_login_endpoint_success():
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_session = MagicMock()
    mock_session.access_token = "jwt-access-token"
    mock_session.refresh_token = "jwt-refresh-token"
    mock_session.token_type = "bearer"
    mock_session.expires_in = 3600
    mock_session.expires_at = 1700000000

    mock_response.user = MagicMock(id="user-123", email="test@example.com")
    mock_response.session = mock_session
    mock_supabase.auth.sign_in_with_password.return_value = mock_response

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Login successful"
        assert data["access_token"] == "jwt-access-token"
        assert data["refresh_token"] == "jwt-refresh-token"
        assert data["user"]["id"] == "user-123"


def test_login_endpoint_invalid_credentials():
    with patch("routers.auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid login credentials"


def test_github_oauth_endpoint_success():
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.url = "https://bidfjrgytnqexwsdnwlt.supabase.co/auth/v1/authorize?provider=github"
    mock_supabase.auth.sign_in_with_oauth.return_value = mock_response

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.get("/auth/github")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "github"
        assert "authorize?provider=github" in data["url"]


def test_get_me_unauthenticated():
    response = client.get("/auth/me")
    assert response.status_code in (401, 403)


def test_get_me_valid_jwt():
    mock_supabase = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.email = "test@example.com"
    mock_user_response = MagicMock(user=mock_user)

    mock_supabase.auth.get_user.return_value = mock_user_response

    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_single = MagicMock()
    mock_single.execute.return_value = MagicMock(
        data={
            "id": "user-123",
            "display_name": "Test User",
            "github_username": "testuser",
            "avatar_url": "https://example.com/avatar.png",
        }
    )
    mock_eq.single.return_value = mock_single
    mock_select.eq.return_value = mock_eq
    mock_table.select.return_value = mock_select
    mock_supabase.table.return_value = mock_table

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer valid-jwt-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "profile" in data
        assert data["profile"]["id"] == "user-123"
        assert data["profile"]["display_name"] == "Test User"


def test_get_me_invalid_jwt():
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("JWT expired")

    with patch("core.dependencies.get_supabase_pub_client", return_value=mock_supabase):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]
