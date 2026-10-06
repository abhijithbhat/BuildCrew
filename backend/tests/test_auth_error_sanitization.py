import logging
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from main import app

client = TestClient(app)

RAW_EXCEPTION_SNIPPET = (
    "Traceback (most recent call last):\n"
    "  File \"/usr/local/lib/python3.12/site-packages/gotrue/api.py\", line 42, in request\n"
    "gotrue.errors.AuthApiError: [Errno 111] Connection failed to db.internal.supabase.co:5432"
)


# ==============================================================================
# 1. SIGNUP ERROR HANDLING & SANITIZATION
# ==============================================================================

def test_signup_existing_account_returns_409():
    """Signup with already registered user returns 409 without raw exception text."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_up.side_effect = Exception(
            f"User already registered on host auth.supabase.internal. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False):
            response = client.post(
                "/auth/signup",
                json={"email": "existing@example.com", "password": "SecurePassword123!"},
            )
            assert response.status_code == 409
            data = response.json()
            assert data["detail"] == "An account with this email already exists. Please log in."
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text


def test_signup_generic_failure_returns_400_and_sanitizes_raw_error(caplog):
    """Signup failure returns 400 'Request failed. Please try again.' and logs warning."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_up.side_effect = Exception(
            f"Fatal error on backend-worker-node-4.prod.supabase.io: {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/signup",
                json={"email": "newuser@example.com", "password": "SecurePassword123!"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "Request failed. Please try again."

            # Assert no sensitive/raw details in response body
            assert "backend-worker-node-4" not in response.text
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            # Assert real error was logged with logger.warning
            assert any(
                record.levelno == logging.WARNING
                and "Signup failed for newuser@example.com" in record.message
                and "backend-worker-node-4" in record.message
                for record in caplog.records
            )


# ==============================================================================
# 2. VERIFY-OTP ERROR HANDLING & SANITIZATION
# ==============================================================================

@pytest.mark.parametrize(
    "raw_otp_error",
    [
        "Token has expired or is invalid",
        "Token expired",
        "Invalid token provided",
        "OTP has expired",
        "Invalid verification code",
    ],
)
def test_verify_otp_invalid_or_expired_code_returns_400(raw_otp_error, caplog):
    """Expired or invalid OTP -> 400 'Invalid or expired code.' and logs warning."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.verify_otp.side_effect = Exception(
            f"{raw_otp_error} [auth-cluster-9.supabase.net] {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/verify-otp",
                json={"email": "otp@example.com", "token": "999888", "type": "signup"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "Invalid or expired code."
            assert "auth-cluster-9" not in response.text
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Verify OTP failed for otp@example.com" in record.message
                for record in caplog.records
            )


def test_verify_otp_generic_error_returns_400_and_sanitizes(caplog):
    """Verify OTP unexpected/generic failure -> 400 'Request failed. Please try again.'."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.verify_otp.side_effect = Exception(
            f"Internal database corruption at primary.db.internal.host:5432. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/verify-otp",
                json={"email": "otp@example.com", "token": "123123", "type": "signup"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "Request failed. Please try again."
            assert "primary.db.internal.host" not in response.text
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Verify OTP failed for otp@example.com" in record.message
                for record in caplog.records
            )


# ==============================================================================
# 3. FORGOT-PASSWORD ERROR HANDLING & SANITIZATION
# ==============================================================================

def test_forgot_password_email_not_confirmed_returns_401(caplog):
    """Forgot password with unconfirmed email returns 401 'Please verify your email first.'."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.reset_password_for_email.side_effect = Exception(
            f"Email not confirmed for user. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/forgot-password",
                json={"email": "unconfirmed@example.com"},
            )
            assert response.status_code == 401
            data = response.json()
            assert data["detail"] == "Please verify your email first."
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Forgot password failed for unconfirmed@example.com" in record.message
                for record in caplog.records
            )


def test_forgot_password_generic_error_returns_400_and_sanitizes(caplog):
    """Forgot password generic failure returns 400 'Request failed. Please try again.'."""
    with patch("routers.auth.get_supabase_pub_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.reset_password_for_email.side_effect = Exception(
            f"SMTP mailserver gateway timeout at smtp.internal.supabase.co:587. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/forgot-password",
                json={"email": "forgot@example.com"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "Request failed. Please try again."
            assert "smtp.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Forgot password failed for forgot@example.com" in record.message
                for record in caplog.records
            )


# ==============================================================================
# 4. RESET-PASSWORD ERROR HANDLING & SANITIZATION
# ==============================================================================

def test_reset_password_expired_or_invalid_code_returns_400(caplog):
    """Reset password invalid OTP code returns 400 'Invalid or expired code.'."""
    mock_pub = MagicMock()
    mock_pub.auth.verify_otp.side_effect = Exception(
        f"Token has expired or is invalid. {RAW_EXCEPTION_SNIPPET}"
    )

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth._is_dev_fallback_error", return_value=False), \
         caplog.at_level(logging.WARNING):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "reset@example.com",
                "token": "000000",
                "new_password": "NewValidPassword123!",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Invalid or expired code."
        assert "db.internal.supabase.co" not in response.text
        assert "Traceback" not in response.text
        assert "gotrue" not in response.text

        assert any(
            record.levelno == logging.WARNING
            and "Reset password failed for reset@example.com" in record.message
            for record in caplog.records
        )


def test_reset_password_generic_verify_error_returns_400_and_sanitizes(caplog):
    """Reset password generic verify failure returns 400 'Request failed. Please try again.'."""
    mock_pub = MagicMock()
    mock_pub.auth.verify_otp.side_effect = Exception(
        f"Upstream auth node unreachable at edge.supabase.co:443. {RAW_EXCEPTION_SNIPPET}"
    )

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_pub), \
         patch("routers.auth._is_dev_fallback_error", return_value=False), \
         caplog.at_level(logging.WARNING):
        response = client.post(
            "/auth/reset-password",
            json={
                "email": "reset@example.com",
                "token": "112233",
                "new_password": "NewValidPassword123!",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "Request failed. Please try again."
        assert "edge.supabase.co" not in response.text
        assert "Traceback" not in response.text
        assert "gotrue" not in response.text

        assert any(
            record.levelno == logging.WARNING
            and "Reset password failed for reset@example.com" in record.message
            for record in caplog.records
        )


# ==============================================================================
# 5. LOGIN ERROR HANDLING & SANITIZATION
# ==============================================================================

def test_login_invalid_credentials_returns_401(caplog):
    """'Invalid login credentials' returns 401 'Invalid email or password.'."""
    with patch("routers.auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            f"Invalid login credentials on host auth-1.supabase.co. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/login",
                json={"email": "login@example.com", "password": "WrongPassword123!"},
            )
            assert response.status_code == 401
            data = response.json()
            assert data["detail"] == "Invalid email or password."
            assert "auth-1.supabase.co" not in response.text
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Login failed for login@example.com" in record.message
                and "Invalid login credentials" in record.message
                for record in caplog.records
            )


def test_login_email_not_confirmed_returns_401(caplog):
    """'Email not confirmed' returns 401 'Please verify your email first.'."""
    with patch("routers.auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            f"Email not confirmed for account login-unconfirmed@example.com. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/login",
                json={"email": "login-unconfirmed@example.com", "password": "ValidPassword123!"},
            )
            assert response.status_code == 401
            data = response.json()
            assert data["detail"] == "Please verify your email first."
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Login failed for login-unconfirmed@example.com" in record.message
                for record in caplog.records
            )


def test_login_generic_error_returns_400_and_sanitizes(caplog):
    """Login unexpected failure returns 400 'Request failed. Please try again.'."""
    with patch("routers.auth.get_supabase_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception(
            f"Unhandled internal failure at db-pool-42.internal:5432. {RAW_EXCEPTION_SNIPPET}"
        )
        mock_get_client.return_value = mock_client

        with patch("routers.auth._is_dev_fallback_error", return_value=False), \
             caplog.at_level(logging.WARNING):
            response = client.post(
                "/auth/login",
                json={"email": "login-broken@example.com", "password": "ValidPassword123!"},
            )
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "Request failed. Please try again."
            assert "db-pool-42.internal" not in response.text
            assert "db.internal.supabase.co" not in response.text
            assert "Traceback" not in response.text
            assert "gotrue" not in response.text

            assert any(
                record.levelno == logging.WARNING
                and "Login failed for login-broken@example.com" in record.message
                for record in caplog.records
            )
