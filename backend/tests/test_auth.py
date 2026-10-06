from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_signup_endpoint_success():
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_user = MagicMock(id="user-123", email="test@example.com")
    mock_user.identities = [MagicMock()]  # Non-empty = new signup (not duplicate)
    mock_response.user = mock_user
    mock_response.session = None
    mock_supabase.auth.sign_up.return_value = mock_response

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        response = client.post(
            "/auth/signup",
            json={"email": "test@example.com", "password": "SecurePassword123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "Verification code sent to your email" in data["message"]
        assert data["user"]["id"] == "user-123"
        assert data["user"]["email"] == "test@example.com"


def test_signup_endpoint_failure():
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_up.side_effect = Exception("Invalid email format")
        mock_get_client.return_value = mock_client

        response = client.post(
            "/auth/signup",
            json={"email": "invalid-email", "password": "SecurePassword123"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Request failed. Please try again."


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
        assert response.json()["detail"] == "Invalid email or password."


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
        assert "Invalid or expired authentication token" in response.json()["detail"]


def test_refresh_token_success():
    mock_supabase = MagicMock()
    mock_session = MagicMock()
    mock_session.access_token = "new-access-token-xyz"
    mock_session.refresh_token = "new-refresh-token-abc"
    mock_session.token_type = "bearer"
    mock_session.expires_in = 3600
    mock_session.expires_at = 1750000000

    mock_user = MagicMock()
    mock_user.id = "user-uuid-123"
    mock_user.email = "builder@example.com"
    mock_user.user_metadata = {"display_name": "Pro Builder"}

    mock_auth_response = MagicMock()
    mock_auth_response.session = mock_session
    mock_auth_response.user = mock_user

    mock_supabase.auth.refresh_session.return_value = mock_auth_response

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "valid-refresh-token-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new-access-token-xyz"
        assert data["refresh_token"] == "new-refresh-token-abc"
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600
        assert data["expires_at"] == 1750000000
        assert data["user"]["email"] == "builder@example.com"
        assert data["user"]["display_name"] == "Pro Builder"


def test_refresh_token_invalid_or_expired():
    mock_supabase = MagicMock()
    mock_supabase.auth.refresh_session.side_effect = Exception("Refresh token is not valid")

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "expired-or-revoked-token"},
        )
        assert response.status_code == 401
        assert "INVALID_REFRESH_TOKEN" in response.json()["detail"]


def test_refresh_token_empty():
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "   "},
    )
    assert response.status_code == 401
    assert "INVALID_REFRESH_TOKEN" in response.json()["detail"]


def test_refresh_token_dev_mode():
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "mock-dev-refresh-token-developer@buildcrew.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "mock-dev-access-token-developer@buildcrew.com" in data["access_token"]
    assert "mock-dev-refresh-token-developer@buildcrew.com" in data["refresh_token"]
    assert data["user"]["email"] == "developer@buildcrew.com"


def test_delete_my_account_unauthenticated():
    response = client.delete("/auth/me")
    assert response.status_code in (401, 403)


def test_delete_my_account_authenticated():
    mock_supabase = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "user-delete-123"
    mock_user.email = "delete-me@example.com"
    mock_user_response = MagicMock(user=mock_user)

    mock_supabase.auth.get_user.return_value = mock_user_response

    # Table mocks: no owned projects
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    # Storage mocks: empty bucket
    mock_supabase.storage.from_.return_value.list.return_value = []
    # Admin delete succeeds
    mock_supabase.auth.admin.delete_user.return_value = None
    # Admin confirmation check confirms user no longer exists (404)
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer valid-delete-jwt"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "deleted successfully" in data["message"]
        assert data["user_id"] == "user-delete-123"


def test_reset_password_valid_otp_success():
    """Valid OTP -> update_user_by_id called once with the new password -> 200."""
    mock_pub = MagicMock()
    mock_otp_resp = MagicMock()
    mock_otp_resp.user = MagicMock(id="user-reset-456")
    mock_otp_resp.session = MagicMock(access_token="temp-recovery-access-token")
    mock_pub.auth.verify_otp.return_value = mock_otp_resp

    mock_admin = MagicMock()
    mock_admin.auth.admin.update_user_by_id.return_value = MagicMock()
    mock_admin.auth.admin.sign_out.return_value = None

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth.get_supabase_client", return_value=mock_admin):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "user@example.com",
                "token": "654321",
                "new_password": "ValidNewPassword123!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "Password reset successfully" in data["message"]
        # update_user_by_id called once with the new password
        mock_admin.auth.admin.update_user_by_id.assert_called_once_with(
            "user-reset-456",
            {"password": "ValidNewPassword123!"},
        )
        # Session sign_out called with temporary access token
        mock_admin.auth.admin.sign_out.assert_called_once_with("temp-recovery-access-token")
        # Response body never contains access_token
        assert "access_token" not in data
        assert "token" not in data
        assert "refresh_token" not in data


def test_reset_password_invalid_otp_fails():
    """Invalid OTP -> 400 'Invalid or expired code.' and update not called."""
    mock_pub = MagicMock()
    mock_pub.auth.verify_otp.side_effect = Exception("Token has expired or is invalid")

    mock_admin = MagicMock()

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth.get_supabase_client", return_value=mock_admin):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "user@example.com",
                "token": "000000",
                "new_password": "ValidNewPassword123!",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Invalid or expired code."
        # Update must not be called
        mock_admin.auth.admin.update_user_by_id.assert_not_called()
        # Response body never contains access_token
        assert "access_token" not in data


def test_reset_password_update_raises_500():
    """Valid OTP but update raises -> 500 'Could not reset password. Please try again.'."""
    mock_pub = MagicMock()
    mock_otp_resp = MagicMock()
    mock_otp_resp.user = MagicMock(id="user-reset-456")
    mock_otp_resp.session = MagicMock(access_token="temp-recovery-access-token")
    mock_pub.auth.verify_otp.return_value = mock_otp_resp

    mock_admin = MagicMock()
    mock_admin.auth.admin.update_user_by_id.side_effect = Exception("Supabase Auth API timeout")

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth.get_supabase_client", return_value=mock_admin):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "user@example.com",
                "token": "654321",
                "new_password": "ValidNewPassword123!",
            },
        )
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Could not reset password. Please try again."
        mock_admin.auth.admin.update_user_by_id.assert_called_once_with(
            "user-reset-456",
            {"password": "ValidNewPassword123!"},
        )
        # Response body never contains access_token
        assert "access_token" not in data


def test_reset_password_response_body_never_contains_access_token():
    """Verify response body never contains access_token, refresh_token, or sensitive session data."""
    mock_pub = MagicMock()
    mock_otp_resp = MagicMock()
    mock_otp_resp.user = MagicMock(id="user-789")
    mock_otp_resp.session = MagicMock(access_token="super-secret-jwt", refresh_token="super-secret-refresh")
    mock_pub.auth.verify_otp.return_value = mock_otp_resp

    mock_admin = MagicMock()
    mock_admin.auth.admin.update_user_by_id.return_value = MagicMock()

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth.get_supabase_client", return_value=mock_admin):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "privacy@example.com",
                "token": "112233",
                "new_password": "NewSafePassword123!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" not in data
        assert "refresh_token" not in data
        assert "session" not in data



