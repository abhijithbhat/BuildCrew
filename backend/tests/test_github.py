import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from core.dependencies import get_current_user
from routers.projects import DEV_PROJECTS_DB, DEV_PROJECT_MEMBERS_DB
from services.github_service import DEV_GITHUB_INSTALLATIONS_DB

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_state():
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_GITHUB_INSTALLATIONS_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_GITHUB_INSTALLATIONS_DB.clear()


def test_github_callback_missing_installation_id():
    """Callback without installation_id should return 400 Bad Request HTML error."""
    response = client.get("/github/callback")
    assert response.status_code == 400
    assert "Connection Incomplete" in response.text


def test_github_callback_success_html():
    """Callback with installation_id returns 200 OK with success screen."""
    response = client.get("/github/callback?installation_id=999888")
    assert response.status_code == 200
    assert "GitHub Connected!" in response.text
    assert "Installation Successful" in response.text


def test_github_callback_json_response():
    """Callback with JSON accept header returns structured payload."""
    response = client.get(
        "/github/callback?installation_id=999888&state=proj-123",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["installation_id"] == "999888"
    assert data["project_id"] == "proj-123"


def test_get_install_url():
    """Verify endpoint provides valid GitHub App installation URL."""
    mock_user = MagicMock(id="user-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "BuildCrew Core",
        "created_by": "user-1",
    }

    response = client.get(
        "/projects/proj-1/github/install-url",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "github.com/apps/" in data["url"]
    assert "state=proj-1" in data["url"]


def test_link_github_installation_team_lead():
    """Team Lead can successfully link a GitHub installation to their project."""
    mock_user = MagicMock(id="lead-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "BuildCrew App",
        "created_by": "lead-1",
    }

    payload = {
        "installation_id": "inst-12345",
        "repo_full_name": "buildcrew/mobile-flutter",
    }

    response = client.post(
        "/projects/proj-1/github/install",
        json=payload,
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["installation_id"] == "inst-12345"
    assert data["repo_full_name"] == "buildcrew/mobile-flutter"
    assert data["project_id"] == "proj-1"


def test_get_project_github_installation():
    """Verify fetching connected installation details for a project."""
    mock_user = MagicMock(id="lead-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "BuildCrew App",
        "created_by": "lead-1",
    }

    # When unconnected
    response = client.get(
        "/projects/proj-1/github/installation",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    assert response.json()["connected"] is False

    # Link installation
    DEV_GITHUB_INSTALLATIONS_DB["proj-1"] = {
        "id": "inst-rec-1",
        "project_id": "proj-1",
        "installation_id": "554433",
        "repo_full_name": "buildcrew/backend",
        "connected_at": "2026-08-19T10:00:00Z",
    }

    response = client.get(
        "/projects/proj-1/github/installation",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["installation"]["repo_full_name"] == "buildcrew/backend"


def test_unlink_github_installation_by_lead():
    """Team lead can unlink the repository."""
    mock_user = MagicMock(id="lead-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "BuildCrew App",
        "created_by": "lead-1",
    }
    DEV_GITHUB_INSTALLATIONS_DB["proj-1"] = {
        "id": "inst-rec-1",
        "project_id": "proj-1",
        "installation_id": "554433",
        "repo_full_name": "buildcrew/backend",
        "connected_at": "2026-08-19T10:00:00Z",
    }

    response = client.delete(
        "/projects/proj-1/github/installation",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "proj-1" not in DEV_GITHUB_INSTALLATIONS_DB


def test_get_commits_pulls_issues():
    """Test commit, pull request, and issue endpoints."""
    mock_user = MagicMock(id="lead-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "BuildCrew App",
        "created_by": "lead-1",
    }
    DEV_GITHUB_INSTALLATIONS_DB["proj-1"] = {
        "id": "inst-rec-1",
        "project_id": "proj-1",
        "installation_id": "554433",
        "repo_full_name": "buildcrew/backend",
        "connected_at": "2026-08-19T10:00:00Z",
    }

    # Commits with default branch
    resp_commits = client.get(
        "/projects/proj-1/github/commits",
        headers={"Authorization": "Bearer token"},
    )
    assert resp_commits.status_code == 200
    assert len(resp_commits.json()["commits"]) > 0
    assert resp_commits.json()["branch"] == "default"

    # Commits with specified branch
    resp_branch = client.get(
        "/projects/proj-1/github/commits?branch=develop",
        headers={"Authorization": "Bearer token"},
    )
    assert resp_branch.status_code == 200
    assert resp_branch.json()["branch"] == "develop"


    # Pull Requests
    resp_pulls = client.get(
        "/projects/proj-1/github/pulls?state=open",
        headers={"Authorization": "Bearer token"},
    )
    assert resp_pulls.status_code == 200
    pulls_data = resp_pulls.json()
    assert len(pulls_data["pulls"]) > 0
    first_pr = pulls_data["pulls"][0]
    assert "head_branch" in first_pr
    assert "base_branch" in first_pr
    assert "user_avatar" in first_pr


    # Issues
    resp_issues = client.get(
        "/projects/proj-1/github/issues?state=open",
        headers={"Authorization": "Bearer token"},
    )
    assert resp_issues.status_code == 200
    issues_data = resp_issues.json()
    assert len(issues_data["issues"]) > 0
    first_issue = issues_data["issues"][0]
    assert "number" in first_issue
    assert "title" in first_issue
    assert "comments" in first_issue
    assert "labels" in first_issue
    assert "user_avatar" in first_issue



@pytest.mark.anyio
async def test_get_installation_access_token_mock_and_cache():
    """Verify get_installation_access_token generates token and caches it properly."""
    from services.github_service import (
        _INSTALLATION_TOKEN_CACHE,
        generate_app_jwt,
        get_installation_access_token,
    )

    _INSTALLATION_TOKEN_CACHE.clear()

    # When generate_app_jwt returns a signed JWT or mock
    with patch("services.github_service.generate_app_jwt", return_value="mock-app-jwt-123"):
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"token": "ghs_testToken12345"}
            mock_post.return_value = mock_resp

            # First call -> hits GitHub API
            token1 = await get_installation_access_token("install-999")
            assert token1 == "ghs_testToken12345"
            assert "install-999" in _INSTALLATION_TOKEN_CACHE
            assert mock_post.call_count == 1

            # Second call -> uses in-memory cache without hitting GitHub API
            token2 = await get_installation_access_token("install-999")
            assert token2 == "ghs_testToken12345"
            assert mock_post.call_count == 1  # Still 1 because cached!


def test_github_webhook_push_event():
    """Verify GitHub webhook push event parses payload and logs commits."""
    from core.config import settings

    payload = {
        "ref": "refs/heads/main",
        "repository": {"full_name": "buildcrew/mobile-flutter"},
        "sender": {"login": "octocat"},
        "commits": [
            {
                "id": "c1a2b3c4d5e6",
                "message": "fix: update network endpoint fallback\n\nDetailed notes here",
                "author": {"name": "Mona Lisa Octocat"},
            }
        ],
    }

    with patch.object(settings, "GITHUB_WEBHOOK_SECRET", ""):
        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={
                "X-GitHub-Event": "push",
                "X-GitHub-Delivery": "delivery-uuid-12345",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["event"] == "push"
        assert data["repository"] == "buildcrew/mobile-flutter"
        assert data["commits_count"] == 1


def test_github_webhook_ping_event():
    """Verify GitHub webhook ping event returns pong."""
    from core.config import settings

    payload = {
        "zen": "Approachable is better than simple.",
        "hook_id": 987654,
    }
    with patch.object(settings, "GITHUB_WEBHOOK_SECRET", ""):
        response = client.post(
            "/webhooks/github",
            json=payload,
            headers={"X-GitHub-Event": "ping"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Pong!"



def test_github_webhook_hmac_signature_verification():
    """Verify HMAC signature validation when GITHUB_WEBHOOK_SECRET is set."""
    import hashlib
    import hmac
    import json
    from core.config import settings

    test_secret = "test_super_secret_webhook_key_123"
    payload = {"repository": {"full_name": "buildcrew/api"}, "commits": []}
    body_bytes = json.dumps(payload).encode("utf-8")

    # Correct signature
    valid_sig = "sha256=" + hmac.new(test_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    with patch.object(settings, "GITHUB_WEBHOOK_SECRET", test_secret):
        # 1. Valid signature -> 200 OK
        resp_valid = client.post(
            "/webhooks/github",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": valid_sig,
                "X-GitHub-Event": "push",
            },
        )
        assert resp_valid.status_code == 200

        # 2. Invalid signature -> 401 Unauthorized
        resp_invalid = client.post(
            "/webhooks/github",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_hash_signature_000000000",
                "X-GitHub-Event": "push",
            },
        )
        assert resp_invalid.status_code == 401

        # 3. Missing signature header -> 401 Unauthorized
        resp_missing = client.post(
            "/webhooks/github",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
            },
        )
        assert resp_missing.status_code == 401


