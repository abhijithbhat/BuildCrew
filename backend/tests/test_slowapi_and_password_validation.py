"""
Tests for slowapi rate limiting and 12-character minimum password enforcement.
Verifies:
- 6th login attempt is blocked with HTTP 429 and Retry-After header.
- Login attempt from different email or different IP is not blocked.
- 11-character password rejected on /auth/signup and /auth/reset-password with 422.
- 12-character password accepted on /auth/signup and /auth/reset-password.
- /auth/signup and /auth/forgot-password 4th attempt blocked (3 per hour per IP).
- /auth/verify-otp 11th attempt blocked (10 per 15 min per IP+email).
- /projects/join 11th attempt blocked (10 per minute per user).
- /contributions/upload-evidence 21st attempt blocked (20 per hour per user).
- Proxy headers: X-Forwarded-For correctly isolated.
"""

from unittest.mock import MagicMock, patch
import io
import pytest
from fastapi.testclient import TestClient
from main import app
from core.dependencies import get_current_user
from core.rate_limit import limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_limiter():
    """Ensure limiter is reset before and after every test."""
    limiter.reset()
    yield
    limiter.reset()


# ---------------------------------------------------------------------------
# Password Minimum Length Tests (12 characters)
# ---------------------------------------------------------------------------


def test_signup_password_11_chars_rejected():
    """An 11-character password on signup MUST be rejected with HTTP 422."""
    response = client.post(
        "/auth/signup",
        json={
            "email": "password_test@example.com",
            "password": "ShortPass11",  # Exactly 11 characters
            "name": "Short Password Tester",
        },
    )
    assert response.status_code == 422
    data = response.json()
    error_msg = str(data)
    assert "Password must be at least 12 characters long" in error_msg


def test_signup_password_12_chars_accepted():
    """A 12-character password on signup is accepted by schema validation."""
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_user = MagicMock(id="user-valid-pass", email="valid_pass@example.com")
    mock_user.identities = [MagicMock()]
    mock_response.user = mock_user
    mock_response.session = None
    mock_supabase.auth.sign_up.return_value = mock_response

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        response = client.post(
            "/auth/signup",
            json={
                "email": "valid_pass@example.com",
                "password": "ValidPass123",  # Exactly 12 characters
                "name": "Valid Password Tester",
            },
        )
        assert response.status_code == 201


def test_reset_password_11_chars_rejected():
    """An 11-character password on reset-password MUST be rejected with HTTP 422."""
    response = client.post(
        "/auth/reset-password",
        json={
            "email": "reset_test@example.com",
            "token": "123456",
            "new_password": "ShortPass11",  # Exactly 11 characters
        },
    )
    assert response.status_code == 422
    data = response.json()
    error_msg = str(data)
    assert "Password must be at least 12 characters long" in error_msg


def test_reset_password_12_chars_accepted():
    """A 12-character password on reset-password passes schema validation."""
    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp.return_value = MagicMock()

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "reset_valid@example.com",
                "token": "123456",
                "new_password": "ValidPass123",  # Exactly 12 characters
            },
        )
        assert response.status_code == 200
        assert "Password reset successfully" in response.json()["message"]


# ---------------------------------------------------------------------------
# Rate Limiting Tests
# ---------------------------------------------------------------------------


def test_login_rate_limit_6th_attempt_blocked():
    """
    /auth/login allows 5 per 15 min per IP+email.
    The 6th attempt from the same IP+email must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        target_email = "target_login@example.com"
        headers = {"X-Forwarded-For": "198.51.100.1"}

        # First 5 attempts: rejected with 401 (not rate limited)
        for i in range(5):
            res = client.post(
                "/auth/login",
                json={"email": target_email, "password": "WrongPassword123"},
                headers=headers,
            )
            assert res.status_code == 401, f"Attempt {i+1} got unexpected status {res.status_code}"

        # 6th attempt: MUST be blocked with 429
        res6 = client.post(
            "/auth/login",
            json={"email": target_email, "password": "WrongPassword123"},
            headers=headers,
        )
        assert res6.status_code == 429
        assert "Retry-After" in res6.headers
        assert int(res6.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res6.json()["detail"]

        # Different email from the SAME IP is NOT blocked
        res_diff_email = client.post(
            "/auth/login",
            json={"email": "other_user@example.com", "password": "WrongPassword123"},
            headers=headers,
        )
        assert res_diff_email.status_code == 401

        # Same email from a DIFFERENT IP is NOT blocked
        res_diff_ip = client.post(
            "/auth/login",
            json={"email": target_email, "password": "WrongPassword123"},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert res_diff_ip.status_code == 401


def test_signup_rate_limit_3_per_hour_per_ip():
    """
    /auth/signup allows 3 per hour per IP.
    The 4th attempt from the same IP must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.user = MagicMock(id="user-sub", identities=[MagicMock()])
    mock_supabase.auth.sign_up.return_value = mock_response

    headers = {"X-Forwarded-For": "203.0.113.10"}

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        # First 3 attempts succeed
        for i in range(3):
            res = client.post(
                "/auth/signup",
                json={
                    "email": f"signup_{i}@example.com",
                    "password": "ValidPassword123",
                    "name": f"User {i}",
                },
                headers=headers,
            )
            assert res.status_code == 201

        # 4th attempt is rate-limited
        res4 = client.post(
            "/auth/signup",
            json={
                "email": "signup_4@example.com",
                "password": "ValidPassword123",
                "name": "User 4",
            },
            headers=headers,
        )
        assert res4.status_code == 429
        assert "Retry-After" in res4.headers
        assert "Rate limit exceeded" in res4.json()["detail"]

        # A different IP is NOT blocked
        res_diff_ip = client.post(
            "/auth/signup",
            json={
                "email": "signup_diff_ip@example.com",
                "password": "ValidPassword123",
                "name": "Different IP User",
            },
            headers={"X-Forwarded-For": "203.0.113.20"},
        )
        assert res_diff_ip.status_code == 201


def test_forgot_password_rate_limit_3_per_hour_per_ip():
    """
    /auth/forgot-password allows 3 per hour per IP.
    The 4th attempt from the same IP must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.reset_password_for_email.return_value = None

    headers = {"X-Forwarded-For": "203.0.113.50"}

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        for i in range(3):
            res = client.post(
                "/auth/forgot-password",
                json={"email": f"forgot_{i}@example.com"},
                headers=headers,
            )
            assert res.status_code == 200

        res4 = client.post(
            "/auth/forgot-password",
            json={"email": "forgot_4@example.com"},
            headers=headers,
        )
        assert res4.status_code == 429
        assert "Retry-After" in res4.headers
        assert "Rate limit exceeded" in res4.json()["detail"]


def test_verify_otp_rate_limit_10_per_15min_per_ip_email():
    """
    /auth/verify-otp allows 10 per 15 min per IP+email.
    The 11th attempt from the same IP+email must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp.side_effect = Exception("Token has expired or is invalid")

    headers = {"X-Forwarded-For": "198.51.100.99"}
    email = "otp_target@example.com"

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        # 10 attempts
        for i in range(10):
            res = client.post(
                "/auth/verify-otp",
                json={"email": email, "token": f"00000{i}", "type": "signup"},
                headers=headers,
            )
            assert res.status_code == 400

        # 11th attempt blocked
        res11 = client.post(
            "/auth/verify-otp",
            json={"email": email, "token": "999999", "type": "signup"},
            headers=headers,
        )
        assert res11.status_code == 429
        assert "Retry-After" in res11.headers
        assert "Rate limit exceeded" in res11.json()["detail"]


def test_projects_join_rate_limit_10_per_minute_per_user():
    """
    /projects/join allows 10 per minute per user.
    The 11th attempt from the same user must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.ilike.return_value.execute.return_value = MagicMock(data=[])

    user = MagicMock(id="user-join-limiter-1", email="joinlimiter@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
            for i in range(10):
                res = client.post(
                    "/projects/join",
                    json={"invite_code": f"BC-CODE-{i}"},
                    headers={"Authorization": "Bearer mock-token"},
                )
                assert res.status_code == 404

            res11 = client.post(
                "/projects/join",
                json={"invite_code": "BC-CODE-11"},
                headers={"Authorization": "Bearer mock-token"},
            )
            assert res11.status_code == 429
            assert "Retry-After" in res11.headers
            assert "Rate limit exceeded" in res11.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_upload_evidence_rate_limit_20_per_hour_per_user():
    """
    /contributions/upload-evidence allows 20 per hour per user.
    The 21st attempt from the same user must be blocked with HTTP 429 and Retry-After.
    """
    user = MagicMock(id="user-upload-limiter", email="uploader@example.com")
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        mock_supabase = MagicMock()
        mock_supabase.storage.from_.return_value.upload.return_value = {"Key": "uploaded"}
        mock_supabase.storage.from_.return_value.get_public_url.return_value = "https://example.com/screenshot.png"

        with patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
            for i in range(20):
                res = client.post(
                    "/contributions/upload-evidence",
                    files={"file": ("screenshot.png", io.BytesIO(b"fake image data"), "image/png")},
                    data={"project_id": "proj-123"},
                    headers={"Authorization": "Bearer mock-token"},
                )
                assert res.status_code == 201

            # 21st attempt blocked
            res21 = client.post(
                "/contributions/upload-evidence",
                files={"file": ("screenshot.png", io.BytesIO(b"fake image data"), "image/png")},
                data={"project_id": "proj-123"},
                headers={"Authorization": "Bearer mock-token"},
            )
            assert res21.status_code == 429
            assert "Retry-After" in res21.headers
            assert "Rate limit exceeded" in res21.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_global_unhandled_exception_handler():
    """Unhandled server errors return 500 with user-safe message."""
    test_client = TestClient(app, raise_server_exceptions=False)
    with patch("main.get_user_passport", side_effect=RuntimeError("Unexpected database crash")):
        res = test_client.get("/users/user-123/passport")
        assert res.status_code == 500
        assert res.json() == {"detail": "Something went wrong. Please try again."}

