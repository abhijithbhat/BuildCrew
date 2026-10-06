"""
Tests for slowapi rate limiting and 12-character minimum password enforcement.
Verifies:
- 11th login attempt is blocked with HTTP 429 and Retry-After header.
- 11th login attempt for one email is 429 even when X-Forwarded-For changes on every request.
- Different email is unaffected.
- X-Forwarded-For is ignored everywhere; X-Real-IP is used in production.
- 11-character password rejected on /auth/signup and /auth/reset-password with 422.
- 12-character password accepted on /auth/signup and /auth/reset-password.
- /auth/signup (3/hr per email, 20/hr per IP, 200/hr globally) and /auth/forgot-password (3/hr per email, 20/hr per IP).
- /auth/reset-password (10/15min per email, 60/15min per IP) returns 429 after 10 wrong codes.
- /auth/verify-otp (10 per 15 min per email, 60 per 15 min per IP).
- /projects/join 11th attempt blocked (10 per minute per user).
- /contributions/upload-evidence 21st attempt blocked (20 per hour per user).
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
    mock_pub = MagicMock()
    mock_otp_resp = MagicMock()
    mock_otp_resp.user = MagicMock(id="11111111-1111-4111-8111-111111111111")
    mock_otp_resp.session = None
    mock_pub.auth.verify_otp.return_value = mock_otp_resp

    mock_admin = MagicMock()
    mock_admin.auth.admin.update_user_by_id.return_value = MagicMock()

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth.get_supabase_client", return_value=mock_admin):
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
# Rate Limiting Tests
# ---------------------------------------------------------------------------


def test_login_rate_limit_11th_attempt_blocked():
    """
    /auth/login allows 10 per 15 min per email (and 60 per 15 min per IP).
    The 11th attempt for the same email must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        target_email = "target_login@example.com"
        headers = {"X-Real-IP": "198.51.100.1"}

        # First 10 attempts: rejected with 401 (not rate limited)
        for i in range(10):
            res = client.post(
                "/auth/login",
                json={"email": target_email, "password": "WrongPassword123"},
                headers=headers,
            )
            assert res.status_code == 401, f"Attempt {i+1} got unexpected status {res.status_code}"

        # 11th attempt: MUST be blocked with 429
        res11 = client.post(
            "/auth/login",
            json={"email": target_email, "password": "WrongPassword123"},
            headers=headers,
        )
        assert res11.status_code == 429
        assert "Retry-After" in res11.headers
        assert int(res11.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res11.json()["detail"]

        # Different email from the SAME IP is NOT blocked
        res_diff_email = client.post(
            "/auth/login",
            json={"email": "other_user@example.com", "password": "WrongPassword123"},
            headers=headers,
        )
        assert res_diff_email.status_code == 401


def test_login_rate_limit_11th_attempt_blocked_with_rotating_x_forwarded_for():
    """
    The 11th login attempt for one email is 429 even when X-Forwarded-For changes
    on every request. A different email is unaffected. X-Forwarded-For is ignored.
    429 carries Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    with patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        target_email = "rotating_ip_user@example.com"

        # 10 attempts with rotating spoofed X-Forwarded-For headers
        for i in range(10):
            res = client.post(
                "/auth/login",
                json={"email": target_email, "password": "WrongPassword123"},
                headers={"X-Forwarded-For": f"198.51.100.{i + 10}"},
            )
            assert res.status_code == 401, f"Attempt {i+1} got unexpected status {res.status_code}"

        # 11th attempt with yet another X-Forwarded-For header: MUST be blocked by email key
        res11 = client.post(
            "/auth/login",
            json={"email": target_email, "password": "WrongPassword123"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert res11.status_code == 429
        assert "Retry-After" in res11.headers
        assert int(res11.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res11.json()["detail"]

        # A different email is unaffected (not blocked)
        res_diff = client.post(
            "/auth/login",
            json={"email": "different_account@example.com", "password": "WrongPassword123"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert res_diff.status_code == 401


def test_x_forwarded_for_is_ignored_and_x_real_ip_used():
    """
    get_real_client_ip reads ONLY X-Real-IP in production (returns 'unknown' if missing).
    X-Forwarded-For is never read anywhere.
    In development, request.client.host is used.
    """
    from core.rate_limit import get_real_client_ip
    from starlette.datastructures import Headers

    # 1. Production: X-Forwarded-For present, X-Real-IP missing -> returns 'unknown'
    req1 = MagicMock()
    req1.headers = Headers({"x-forwarded-for": "198.51.100.1"})
    req1.client = MagicMock(host="10.0.0.1")
    with patch("core.config.settings.ENVIRONMENT", "production"):
        assert get_real_client_ip(req1) == "unknown"

    # 2. Production: X-Real-IP present -> returns X-Real-IP (X-Forwarded-For ignored)
    req2 = MagicMock()
    req2.headers = Headers({"x-forwarded-for": "198.51.100.1", "x-real-ip": "203.0.113.44"})
    with patch("core.config.settings.ENVIRONMENT", "production"):
        assert get_real_client_ip(req2) == "203.0.113.44"

    # 3. Production: Neither header present -> returns 'unknown'
    req3 = MagicMock()
    req3.headers = Headers({})
    with patch("core.config.settings.ENVIRONMENT", "production"):
        assert get_real_client_ip(req3) == "unknown"

    # 4. Development: uses request.client.host, X-Forwarded-For ignored
    req_dev = MagicMock()
    req_dev.headers = Headers({"x-forwarded-for": "198.51.100.1"})
    req_dev.client = MagicMock(host="127.0.0.1")
    with patch("core.config.settings.ENVIRONMENT", "development"):
        assert get_real_client_ip(req_dev) == "127.0.0.1"


def test_reset_password_rate_limit_10_wrong_codes():
    """
    /auth/reset-password returns 429 after 10 wrong codes for one email.
    429 carries Retry-After. A different email is unaffected.
    """
    mock_pub = MagicMock()
    mock_pub.auth.verify_otp.side_effect = Exception("Invalid or expired code")

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub):
        target_email = "reset_victim@example.com"
        headers = {"X-Real-IP": "198.51.100.77"}

        # 10 wrong OTP codes for target email -> 400
        for i in range(10):
            res = client.post(
                "/auth/reset-password",
                json={
                    "email": target_email,
                    "token": f"00000{i}",
                    "new_password": "NewValidPassword123",
                },
                headers=headers,
            )
            assert res.status_code == 400, f"Attempt {i+1} got unexpected status {res.status_code}"

        # 11th attempt -> 429
        res11 = client.post(
            "/auth/reset-password",
            json={
                "email": target_email,
                "token": "999999",
                "new_password": "NewValidPassword123",
            },
            headers=headers,
        )
        assert res11.status_code == 429
        assert "Retry-After" in res11.headers
        assert int(res11.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res11.json()["detail"]

        # Different email is unaffected (returns 400 for wrong code, not 429)
        res_diff = client.post(
            "/auth/reset-password",
            json={
                "email": "reset_other@example.com",
                "token": "000001",
                "new_password": "NewValidPassword123",
            },
            headers=headers,
        )
        assert res_diff.status_code == 400


def test_signup_rate_limit_3_per_hour_per_email_and_ip():
    """
    /auth/signup allows 3 per hour per email, 20 per hour per IP, and 200 per hour globally.
    4th attempt for the same email is blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.user = MagicMock(id="user-sub", identities=[MagicMock()])
    mock_supabase.auth.sign_up.return_value = mock_response

    headers = {"X-Real-IP": "203.0.113.10"}
    target_email = "signup_limit@example.com"

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        # First 3 attempts for same email succeed
        for i in range(3):
            res = client.post(
                "/auth/signup",
                json={
                    "email": target_email,
                    "password": "ValidPassword123",
                    "name": f"User {i}",
                },
                headers=headers,
            )
            assert res.status_code == 201

        # 4th attempt for same email is rate-limited by email
        res4 = client.post(
            "/auth/signup",
            json={
                "email": target_email,
                "password": "ValidPassword123",
                "name": "User 4",
            },
            headers=headers,
        )
        assert res4.status_code == 429
        assert "Retry-After" in res4.headers
        assert int(res4.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res4.json()["detail"]

        # A different email from the same IP succeeds
        res_diff_email = client.post(
            "/auth/signup",
            json={
                "email": "signup_diff@example.com",
                "password": "ValidPassword123",
                "name": "Different User",
            },
            headers=headers,
        )
        assert res_diff_email.status_code == 201


def test_forgot_password_rate_limit_3_per_hour_per_email_and_ip():
    """
    /auth/forgot-password allows 3 per hour per email (and 20 per hour per IP).
    The 4th attempt for the same email must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.reset_password_for_email.return_value = None

    headers = {"X-Real-IP": "203.0.113.50"}
    target_email = "forgot_target@example.com"

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_supabase):
        for i in range(3):
            res = client.post(
                "/auth/forgot-password",
                json={"email": target_email},
                headers=headers,
            )
            assert res.status_code == 200

        res4 = client.post(
            "/auth/forgot-password",
            json={"email": target_email},
            headers=headers,
        )
        assert res4.status_code == 429
        assert "Retry-After" in res4.headers
        assert int(res4.headers["Retry-After"]) > 0
        assert "Rate limit exceeded" in res4.json()["detail"]

        # Different email is not blocked
        res_diff = client.post(
            "/auth/forgot-password",
            json={"email": "forgot_different@example.com"},
            headers=headers,
        )
        assert res_diff.status_code == 200


def test_verify_otp_rate_limit_10_per_15min_per_email_and_ip():
    """
    /auth/verify-otp allows 10 per 15 min per email (and 60 per 15 min per IP).
    The 11th attempt for the same email must be blocked with HTTP 429 and Retry-After.
    """
    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp.side_effect = Exception("Token has expired or is invalid")

    headers = {"X-Real-IP": "198.51.100.99"}
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
        assert int(res11.headers["Retry-After"]) > 0
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

