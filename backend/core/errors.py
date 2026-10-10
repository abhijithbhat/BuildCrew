"""
BuildCrew centralized route exception mapping helper.

Handles unexpected exceptions caught in route handlers:
- Preserves real HTTPExceptions (e.g. 400, 401, 403, 404, 409, 422) untouched.
- Maps upstream network/timeout issues (httpx.TransportError, httpx.TimeoutException,
  postgrest 5xx APIError, or error messages containing 'timed out', 'timeout',
  'bad gateway', '502', '503') to HTTP 503 "Service temporarily unavailable. Please try again."
  with Retry-After: 5.
- Maps all other unexpected internal errors to HTTP 500 with the provided generic message.
- Logs unexpected and upstream failures using logger.exception.
"""

from typing import Optional
from fastapi import HTTPException, status
import httpx
from core.logging import logger

try:
    from postgrest.exceptions import APIError
except ImportError:
    APIError = None


def handle_route_error(
    exc: Exception,
    generic_message: str,
    log_message: Optional[str] = None,
) -> HTTPException:
    """
    Map an exception to a production-grade HTTPException:
    1. If exc is an HTTPException (real 4xx/5xx from validation/business logic),
       leave it untouched.
    2. If exc is a network or upstream timeout/gateway failure, log and return 503.
    3. Otherwise, log and return 500 with the original generic message.
    """
    if isinstance(exc, HTTPException):
        # Keep real 4xx / existing HTTP exceptions untouched
        return exc

    log_text = log_message or generic_message

    # Check for upstream transport/timeout/5xx errors
    is_transport = isinstance(exc, (httpx.TransportError, httpx.TimeoutException))

    is_postgrest_5xx = False
    if APIError and isinstance(exc, APIError):
        code_str = str(getattr(exc, "code", "") or "").strip()
        if code_str.isdigit() and 500 <= int(code_str) <= 599:
            is_postgrest_5xx = True
        elif code_str.startswith("5"):
            is_postgrest_5xx = True

    msg_lower = (
        f"{str(exc)} {getattr(exc, 'message', '')} {getattr(exc, 'details', '')}"
    ).lower()
    has_timeout_str = any(
        pattern in msg_lower
        for pattern in ["timed out", "timeout", "bad gateway", "502", "503"]
    )

    if is_transport or is_postgrest_5xx or has_timeout_str:
        logger.exception(f"{log_text} (upstream 503 mapping): {exc}")
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again.",
            headers={"Retry-After": "5"},
        )

    logger.exception(f"{log_text}: {exc}")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=generic_message,
    )


def raise_route_error(
    exc: Exception,
    generic_message: str,
    log_message: Optional[str] = None,
) -> None:
    """Convenience helper that immediately raises the mapped HTTPException."""
    raise handle_route_error(exc, generic_message, log_message)
