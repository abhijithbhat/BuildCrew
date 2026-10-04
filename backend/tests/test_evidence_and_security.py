from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from core.config import settings
from core.dependencies import get_current_user
from main import app
from schemas.contribution import (
    ContributionCreate,
    ContributionResponse,
    ContributionUpdate,
    ManualContributionCreate,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Schemas: evidence_link validation & sanitization
# ---------------------------------------------------------------------------

def test_evidence_link_create_valid_http_and_https():
    """Valid http and https URLs with hostnames are accepted and trimmed."""
    c1 = ContributionCreate(
        contributor="user-1",
        project="proj-1",
        title="Valid HTTP",
        evidence_link="  http://example.com/evidence/1  ",
    )
    assert c1.evidence_link == "http://example.com/evidence/1"

    c2 = ManualContributionCreate(
        title="Valid HTTPS",
        evidence_link="  https://github.com/buildcrew/consensus/pull/42  ",
    )
    assert c2.evidence_link == "https://github.com/buildcrew/consensus/pull/42"


def test_evidence_link_create_invalid_schemes_raise_422():
    """Non-http(s) schemes raise 422 with the exact required detail message."""
    invalid_links = [
        "ftp://files.example.com/proof.pdf",
        "javascript:alert('xss')",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "not-a-valid-url",
    ]
    for bad_link in invalid_links:
        with pytest.raises(Exception) as exc_info:
            ContributionCreate(
                contributor="user-1",
                project="proj-1",
                title="Bad Link",
                evidence_link=bad_link,
            )
        assert "Evidence link must start with http:// or https://" in str(exc_info.value)


def test_evidence_link_missing_hostname_raises_422():
    """URLs lacking a valid hostname raise 422."""
    for bad_link in ["http://", "https://", "https:///path/only", "http://  "]:
        with pytest.raises(Exception) as exc_info:
            ManualContributionCreate(
                title="No Hostname",
                evidence_link=bad_link,
            )
        assert "Evidence link must start with http:// or https://" in str(exc_info.value)


def test_evidence_link_exceeding_2048_chars_raises_422():
    """URLs exceeding 2048 chars raise 422."""
    long_link = "https://example.com/" + ("a" * 2035)
    assert len(long_link) > 2048
    with pytest.raises(Exception) as exc_info:
        ContributionCreate(
            contributor="user-1",
            project="proj-1",
            title="Too Long",
            evidence_link=long_link,
        )
    assert "Evidence link must start with http:// or https://" in str(exc_info.value)


def test_evidence_link_update_validation():
    """ContributionUpdate validates evidence_link using the same rules."""
    u_valid = ContributionUpdate(evidence_link=" https://buildcrew.io/evidence ")
    assert u_valid.evidence_link == "https://buildcrew.io/evidence"

    with pytest.raises(Exception) as exc_info:
        ContributionUpdate(evidence_link="ftp://bad.com")
    assert "Evidence link must start with http:// or https://" in str(exc_info.value)


def test_existing_rows_skip_rendering_non_http_link():
    """ContributionResponse sanitizes invalid existing links to None so they are not rendered."""
    res_bad = ContributionResponse(
        id="c-1",
        contributor="u-1",
        project="p-1",
        title="Old Row with Bad Link",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        evidence_link="javascript:alert(1)",
    )
    assert res_bad.evidence_link is None

    res_good = ContributionResponse(
        id="c-2",
        contributor="u-1",
        project="p-1",
        title="Old Row with Valid Link",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        evidence_link="https://github.com/buildcrew/repo/commit/123",
    )
    assert res_good.evidence_link == "https://github.com/buildcrew/repo/commit/123"


def test_post_contribution_invalid_evidence_link_returns_422():
    """API endpoint POST /contributions returns 422 when evidence_link is invalid."""
    mock_user = MagicMock(id="user-validator-1", email="val@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = client.post(
            "/contributions",
            json={
                "project_id": "proj-any",
                "title": "Invalid Evidence Test",
                "evidence_link": "ftp://malicious.com/file",
            },
        )
        assert response.status_code == 422
        assert "Evidence link must start with http:// or https://" in response.text
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 2. passport.html: robots meta & evidence anchor rendering
# ---------------------------------------------------------------------------

def test_passport_html_has_robots_noindex_nofollow():
    """Verify passport.html template contains <meta name="robots" content="noindex, nofollow">."""
    from core.templates import TEMPLATES_DIR
    import os
    template_path = os.path.join(TEMPLATES_DIR, "passport.html")
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta name="robots" content="noindex, nofollow">' in content


def test_passport_html_renders_evidence_anchor_only_for_http_or_https():
    """Verify passport.html renders the evidence anchor ONLY when evidence_link starts with http(s)."""
    from core.templates import templates

    # Context with a valid https link
    context_valid = {
        "passport": {
            "display_name": "Alice Builder",
            "project_name": "Alpha Project",
            "confirmed_count": 1,
            "contributions": [
                {
                    "title": "Smart Contract Deliverable",
                    "evidence_link": "https://github.com/buildcrew/contracts/commit/abc",
                    "created_at": "2026-01-01",
                }
            ],
        },
        "user_id": "user-1",
        "project_id": "proj-1",
    }
    rendered_valid = templates.get_template("passport.html").render(context_valid)
    assert 'href="https://github.com/buildcrew/contracts/commit/abc"' in rendered_valid
    assert "View Verified Deliverable Evidence" in rendered_valid

    # Context with a non-http link (e.g. javascript or ftp)
    context_invalid = {
        "passport": {
            "display_name": "Bob Builder",
            "project_name": "Beta Project",
            "confirmed_count": 1,
            "contributions": [
                {
                    "title": "Non-HTTP Deliverable",
                    "evidence_link": "javascript:alert(1)",
                    "created_at": "2026-01-01",
                }
            ],
        },
        "user_id": "user-2",
        "project_id": "proj-2",
    }
    rendered_invalid = templates.get_template("passport.html").render(context_invalid)
    assert "javascript:alert(1)" not in rendered_invalid
    assert "View Verified Deliverable Evidence" not in rendered_invalid


# ---------------------------------------------------------------------------
# 3. Security Headers Middleware
# ---------------------------------------------------------------------------

def test_security_headers_present_on_health_endpoint():
    """Security headers are set on standard API responses."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"


def test_security_headers_present_on_docs_404_in_production(monkeypatch):
    """Security headers are present even on gated 404 docs responses in production."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    res = client.get("/docs")
    assert res.status_code == 404
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Permissions-Policy") == "camera=(), microphone=(), geolocation=()"


# ---------------------------------------------------------------------------
# 4. POST /contributions/upload-evidence: chunk reading, size, extensions, MIME
# ---------------------------------------------------------------------------

def test_upload_evidence_allowed_extensions():
    """All allowlisted extensions are accepted."""
    mock_user = MagicMock(id="dev-uploader-ext", email="ext@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    allowed = ["png", "jpg", "jpeg", "webp", "gif", "pdf", "txt", "md", "docx", "pptx", "xlsx"]
    try:
        for ext in allowed:
            filename = f"test_doc.{ext}"
            files = {"file": (filename, b"Sample file content for testing", "application/octet-stream")}
            res = client.post("/contributions/upload-evidence", files=files)
            assert res.status_code == 201, f"Failed for allowed extension .{ext}: {res.text}"
            data = res.json()
            assert data["filename"] == f"test_doc.{ext}"
    finally:
        app.dependency_overrides.clear()


def test_upload_evidence_disallowed_extension_returns_415():
    """Files with non-whitelisted extensions return 415 Unsupported Media Type."""
    mock_user = MagicMock(id="dev-uploader-bad-ext", email="badext@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    disallowed = ["malicious.exe", "script.sh", "payload.zip", "test.py", "archive.tar.gz", "noext"]
    try:
        for fname in disallowed:
            files = {"file": (fname, b"print('hello')", "application/octet-stream")}
            res = client.post("/contributions/upload-evidence", files=files)
            assert res.status_code == 415, f"Expected 415 for {fname}, got {res.status_code}"
            assert "Unsupported file extension" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_upload_evidence_content_type_guessed_server_side_ignoring_client():
    """Client-sent Content-Type header is ignored and guessed server-side from extension."""
    mock_user = MagicMock(id="dev-uploader-mime", email="mime@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # Client lies and says PDF is an image/png
        files = {"file": ("architecture.pdf", b"%PDF-1.4 spec", "image/png")}
        res = client.post("/contributions/upload-evidence", files=files)
        assert res.status_code == 201
        assert res.json()["file_type"] == "application/pdf"

        # Client lies and says PNG is text/plain
        files2 = {"file": ("wireframe.png", b"\x89PNG\r\n\x1a\n", "text/plain")}
        res2 = client.post("/contributions/upload-evidence", files=files2)
        assert res2.status_code == 201
        assert res2.json()["file_type"] == "image/png"
    finally:
        app.dependency_overrides.clear()


def test_upload_evidence_exceeding_25mb_returns_413():
    """Uploads exceeding 25MB are aborted with 413 without reading the entire body."""
    mock_user = MagicMock(id="dev-uploader-oversize", email="huge@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        # 26 MB of data with allowed extension .pdf
        large_bytes = b"X" * (26 * 1024 * 1024)
        files = {"file": ("huge_spec.pdf", large_bytes, "application/pdf")}
        res = client.post("/contributions/upload-evidence", files=files)
        assert res.status_code == 413
        assert "25MB" in res.json()["detail"] or "exceeds" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_upload_evidence_in_production_never_falls_back_to_disk_returns_503(monkeypatch):
    """In production mode, upstream Supabase storage failure returns 503 and never falls back to disk."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", False)

    mock_user = MagicMock(id="user-prod-uploader", email="prod@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_supabase.storage.from_.return_value.upload.side_effect = Exception("Supabase Storage unreachable")

    with patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
        try:
            files = {"file": ("prod_evidence.png", b"\x89PNG\r\n\x1a\n", "image/png")}
            res = client.post("/contributions/upload-evidence", files=files)
            assert res.status_code == 503
            assert "Storage service unavailable" in res.json()["detail"]
        finally:
            app.dependency_overrides.clear()
