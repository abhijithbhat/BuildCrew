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

import re
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
    2. Map PostgREST/Postgres errors by code (APIError.code or SQLSTATE):
       - PGRST116 (0 rows) -> 404 'Not found'
       - 22P02 (invalid uuid) -> 404 'Not found'
       - 23505 (unique constraint violation) -> 409 'Conflict'
       - 23503 (foreign key constraint violation) -> 409 'Conflict'
       - 42501 (permission denied/RLS) and PGRST3xx -> 500 generic (log it)
    3. If exc is a transport-level upstream failure (DNS, connection, timeouts,
       502/503/504 as whole status codes, 'service unavailable', 'bad gateway'),
       log and return 503 with Retry-After: 5.
    4. Anything unexpected -> 500 generic with the original generic message.
    """
    if isinstance(exc, HTTPException):
        # Keep real 4xx / existing HTTP exceptions untouched
        return exc

    log_text = log_message or generic_message

    # 1. Extract PostgREST / Postgres error code (APIError.code or SQLSTATE)
    code = getattr(exc, "code", None)
    if code is None and hasattr(exc, "args") and exc.args and isinstance(exc.args[0], dict):
        code = exc.args[0].get("code")
    code_str = str(code or "").strip().upper() if code is not None else ""

    combined_msg = f"{str(exc)} {getattr(exc, 'message', '')} {getattr(exc, 'details', '')}"
    if not code_str:
        m_code = re.search(r"\b(PGRST\d{3}|22P02|23505|23503|42501)\b", combined_msg, re.IGNORECASE)
        if m_code:
            code_str = m_code.group(1).upper()

    # Map PostgREST/Postgres errors by code
    if code_str == "PGRST116":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if code_str == "22P02" or "invalid input syntax for type uuid" in combined_msg.lower():
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if code_str == "23505":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict",
        )
    if code_str == "23503":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict",
        )
    if code_str == "42501" or bool(re.match(r"^PGRST3\d\d$", code_str)):
        logger.exception(f"{log_text} (Postgres/PostgREST {code_str}): {exc}")
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=generic_message,
        )

    # 2. Check for upstream transport-level problems
    is_transport_exc = isinstance(exc, (httpx.TransportError, httpx.TimeoutException))

    # Whole HTTP status codes (502, 503, 504)
    status_attr = getattr(exc, "status_code", None)
    resp_status = getattr(getattr(exc, "response", None), "status_code", None)
    has_status_5xx = (
        code_str in ("502", "503", "504")
        or status_attr in (502, 503, 504)
        or resp_status in (502, 503, 504)
        or bool(re.search(r"(?<![0-9a-zA-Z_-])(502|503|504)(?![0-9a-zA-Z_-])", combined_msg))
    )

    msg_lower = combined_msg.lower()
    has_transport_str = any(
        pattern in msg_lower
        for pattern in (
            "nodename nor servname provided",
            "gai_error",
            "name or service not known",
            "failed to connect",
            "cannot connect",
            "connection refused",
            "connection reset",
            "connection failed",
            "connection closed",
            "connection error",
            "client disconnected",
            "timed out",
            "timeout",
            "service unavailable",
            "bad gateway",
        )
    )

    if is_transport_exc or has_status_5xx or has_transport_str:
        logger.exception(f"{log_text} (upstream 503 mapping): {exc}")
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again.",
            headers={"Retry-After": "5"},
        )

    # 3. Anything unexpected -> 500 generic
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
