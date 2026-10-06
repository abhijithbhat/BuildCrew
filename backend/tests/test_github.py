import json
import time
import pytest
import jwt
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from main import app, startup_check
from core.config import settings
from core.dependencies import get_current_user
from routers.projects import DEV_PROJECTS_DB, DEV_PROJECT_MEMBERS_DB
from services import github_service
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


# ---------------------------------------------------------------------------
# Production Mode Security & Hardening Tests (monkeypatched)
# ---------------------------------------------------------------------------

@pytest.fixture
def prod_mode(monkeypatch):
    """Fixture ensuring production mode is active with secrets configured."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH", "false")
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "test_production_secret_key_1234567890")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "test_github_client_id_123")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "test_github_client_secret_123")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "test_production_webhook_secret_1234567890")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyzcompany.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "supabase_service_role_key_test")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "supabase_anon_key_test")


def test_production_callback_without_state_returns_400_and_no_db_write(prod_mode):
    """Production callback without state returns 400 and store_installation is never called."""
    with patch("services.github_service.store_installation") as mock_store:
        for path in ["/github/callback", "/callback", "/api/github/callback", "/setup", "/github/setup", "/"]:
            resp = client.get(f"{path}?installation_id=12345")
            assert resp.status_code == 400
            assert "Missing state parameter" in resp.text
            mock_store.assert_not_called()


def test_production_callback_forged_or_expired_state(prod_mode):
    """Production callback with forged or expired state returns 400 and no db write."""
    with patch("services.github_service.store_installation") as mock_store:
        # 1. Forged state (signed with wrong secret)
        forged_token = jwt.encode(
            {"pid": "proj-1", "uid": "lead-1", "exp": int(time.time()) + 900},
            "wrong_app_secret_key_32_bytes_long_sha256",
            algorithm="HS256",
        )
        resp_forged = client.get(f"/github/callback?installation_id=12345&state={forged_token}")
        assert resp_forged.status_code == 400
        assert "Invalid State" in resp_forged.text
        mock_store.assert_not_called()

        # 2. Expired state (signed with correct secret, but in the past)
        expired_token = jwt.encode(
            {"pid": "proj-1", "uid": "lead-1", "exp": int(time.time()) - 300},
            settings.APP_SECRET_KEY,
            algorithm="HS256",
        )
        resp_expired = client.get(f"/github/callback?installation_id=12345&state={expired_token}")
        assert resp_expired.status_code == 400
        assert "Session Expired" in resp_expired.text
        mock_store.assert_not_called()


def test_production_callback_valid_state_non_lead_returns_403(prod_mode):
    """Production callback with valid state but caller is not the project lead returns 403."""
    valid_token = jwt.encode(
        {"pid": "proj-1", "uid": "attacker-user-id", "exp": int(time.time()) + 900},
        settings.APP_SECRET_KEY,
        algorithm="HS256",
    )

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "legit-lead-id", "name": "Legit Project"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.store_installation") as mock_store:
        resp = client.get(f"/github/callback?installation_id=12345&state={valid_token}")
        assert resp.status_code == 403
        assert "Only the Team Lead can modify GitHub repository settings." in resp.text
        mock_store.assert_not_called()


def test_production_callback_missing_code_returns_400(prod_mode):
    """Production callback without code returns 400 and store_installation is never called."""
    valid_token = jwt.encode(
        {"pid": "proj-1", "uid": "lead-user-id", "exp": int(time.time()) + 900},
        settings.APP_SECRET_KEY,
        algorithm="HS256",
    )
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "BuildCrew Core"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.store_installation") as mock_store:

        resp = client.get(f"/github/callback?installation_id=12345&state={valid_token}")
        assert resp.status_code == 400
        assert "Missing authorization code" in resp.text
        mock_store.assert_not_called()

        resp_json = client.get(
            f"/github/callback?installation_id=12345&state={valid_token}",
            headers={"Accept": "application/json"},
        )
        assert resp_json.status_code == 400
        assert "Missing authorization code" in resp_json.json()["detail"]
        mock_store.assert_not_called()


def test_production_callback_installation_not_in_user_list_returns_403(prod_mode):
    """Production callback where installation_id is not in user's installations returns 403 and no write."""
    valid_token = jwt.encode(
        {"pid": "proj-1", "uid": "lead-user-id", "exp": int(time.time()) + 900},
        settings.APP_SECRET_KEY,
        algorithm="HS256",
    )
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "BuildCrew Core"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.get") as mock_get, \
         patch("services.github_service.store_installation") as mock_store:

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "ghu_user_token_abc"},
        )
        # Mock user installations returning a DIFFERENT installation id (e.g. 99999 instead of 12345)
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"installations": [{"id": 99999}]},
        )

        resp = client.get(f"/github/callback?installation_id=12345&state={valid_token}&code=oauth_code_123")
        assert resp.status_code == 403
        assert "Installation ID is not authorized" in resp.text
        mock_store.assert_not_called()

        resp_json = client.get(
            f"/github/callback?installation_id=12345&state={valid_token}&code=oauth_code_123",
            headers={"Accept": "application/json"},
        )
        assert resp_json.status_code == 403
        assert "Installation ID is not authorized" in resp_json.json()["detail"]
        mock_store.assert_not_called()


def test_production_callback_valid_state_links_installation(prod_mode):
    """Production callback with mocked GitHub responses: id in list -> links successfully."""
    valid_token = jwt.encode(
        {"pid": "proj-1", "uid": "lead-user-id", "exp": int(time.time()) + 900},
        settings.APP_SECRET_KEY,
        algorithm="HS256",
    )

    mock_supabase = MagicMock()
    # Mock projects query and installations queries
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "BuildCrew Core"}]
    )
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"name": "BuildCrew Core"}
    )

    mock_repos = [{"full_name": "buildcrew/buildcrew-core"}]

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("httpx.AsyncClient.post") as mock_post, \
         patch("httpx.AsyncClient.get") as mock_get, \
         patch("services.github_service.get_installation_repositories", AsyncMock(return_value=mock_repos)), \
         patch("services.github_service.store_installation") as mock_store:

        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "ghu_user_token_valid"},
        )
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"installations": [{"id": 12345}, {"id": 88888}]},
        )
        mock_store.return_value = {
            "id": "inst-rec-1",
            "project_id": "proj-1",
            "installation_id": "12345",
            "repo_full_name": "buildcrew/buildcrew-core",
        }

        # HTML response
        resp = client.get(f"/github/callback?installation_id=12345&state={valid_token}&code=valid_code_789")
        assert resp.status_code == 200
        assert "GitHub Connected!" in resp.text
        assert "buildcrew/buildcrew-core" in resp.text
        mock_store.assert_called_once_with(
            project_id="proj-1",
            installation_id="12345",
            repo_full_name="buildcrew/buildcrew-core",
        )

        mock_store.reset_mock()

        # JSON response
        resp_json = client.get(
            f"/github/callback?installation_id=12345&state={valid_token}&code=valid_code_789",
            headers={"Accept": "application/json"},
        )
        assert resp_json.status_code == 200
        assert resp_json.json()["status"] == "success"
        assert resp_json.json()["repo_linked"] == "buildcrew/buildcrew-core"
        mock_store.assert_called_once_with(
            project_id="proj-1",
            installation_id="12345",
            repo_full_name="buildcrew/buildcrew-core",
        )


def test_production_get_install_url_creates_signed_jwt_state(prod_mode):
    """GET /projects/{id}/github/install-url creates signed JWT state token in production."""
    mock_user = MagicMock(id="lead-user-id", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "App"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase):
        resp = client.get(
            "/projects/proj-1/github/install-url",
            headers={"Authorization": "Bearer token"},
        )
        assert resp.status_code == 200
        url = resp.json()["url"]
        assert "state=" in url
        state_token = url.split("state=")[1]
        decoded = jwt.decode(state_token, settings.APP_SECRET_KEY, algorithms=["HS256"])
        assert decoded["pid"] == "proj-1"
        assert decoded["uid"] == "lead-user-id"
        assert decoded["exp"] > time.time()


def test_production_repositories_for_project_with_no_installation_returns_empty(prod_mode):
    """In production, /projects/{id}/github/repositories returns empty list when no installation exists."""
    mock_user = MagicMock(id="lead-user-id", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-uninstalled", "created_by": "lead-user-id", "name": "Fresh Project"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_project_installation", return_value=None), \
         patch("services.github_service.get_installation_id_for_lead", return_value=None):
        resp = client.get(
            "/projects/proj-uninstalled/github/repositories",
            headers={"Authorization": "Bearer token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"connected": False, "repositories": []}


def test_production_select_repository_outside_installation_returns_400(prod_mode):
    """In production, select-repository checks that repo_full_name is in granted repos, else 400."""
    mock_user = MagicMock(id="lead-user-id", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "Core Project"}]
    )

    allowed_repos = [{"full_name": "lead-org/approved-repo"}]

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_project_installation", return_value={"installation_id": "inst-555"}), \
         patch("services.github_service.get_installation_repositories", AsyncMock(return_value=allowed_repos)), \
         patch("services.github_service.store_installation") as mock_store:

        # 1. Unapproved repository -> 400
        resp_bad = client.post(
            "/projects/proj-1/github/select-repository",
            json={"repo_full_name": "attacker-org/unapproved-repo"},
            headers={"Authorization": "Bearer token"},
        )
        assert resp_bad.status_code == 400
        assert "not in the granted repositories" in resp_bad.json()["detail"]
        mock_store.assert_not_called()

        # 2. Approved repository -> 200
        mock_store.return_value = {
            "id": "rec-1",
            "project_id": "proj-1",
            "installation_id": "inst-555",
            "repo_full_name": "lead-org/approved-repo",
        }
        resp_good = client.post(
            "/projects/proj-1/github/select-repository",
            json={"repo_full_name": "lead-org/approved-repo"},
            headers={"Authorization": "Bearer token"},
        )
        assert resp_good.status_code == 200
        assert resp_good.json()["success"] is True
        mock_store.assert_called_once_with(
            project_id="proj-1",
            installation_id="inst-555",
            repo_full_name="lead-org/approved-repo",
        )


def test_production_post_install_no_installation_returns_400(prod_mode):
    """In production, POST /github/install returns 400 when neither project nor lead installation exists."""
    mock_user = MagicMock(id="lead-user-id", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "proj-1", "created_by": "lead-user-id", "name": "Core Project"}]
    )

    with patch("routers.github.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_project_installation", return_value=None), \
         patch("services.github_service.get_installation_id_for_lead", return_value=None):

        resp = client.post(
            "/projects/proj-1/github/install",
            json={"repo_full_name": "some/repo"},
            headers={"Authorization": "Bearer token"},
        )
        assert resp.status_code == 400
        assert "No active GitHub App installation found" in resp.json()["detail"]


@pytest.mark.anyio
async def test_production_no_token_raises_502_and_no_drafts_created(prod_mode):
    """In production, no token raises 502 and generate-draft creates no drafts."""
    # 1. Direct function calls raise HTTPException 502
    with patch("services.github_service.get_installation_access_token", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_commits:
            await github_service.fetch_repository_commits("org/repo", "inst-123")
        assert exc_commits.value.status_code == 502
        assert "GitHub is unavailable" in exc_commits.value.detail

        with pytest.raises(HTTPException) as exc_pulls:
            await github_service.fetch_repository_pulls("org/repo", "inst-123")
        assert exc_pulls.value.status_code == 502

        with pytest.raises(HTTPException) as exc_issues:
            await github_service.fetch_repository_issues("org/repo", "inst-123")
        assert exc_issues.value.status_code == 502

    # 2. generate-draft endpoint raises/returns 502 and does NOT insert drafts
    mock_user = MagicMock(id="user-1", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    # Mock project query
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-1", "created_by": "user-1", "name": "Prod App"}
    )
    # Mock project member check
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "user-1", "project_id": "proj-1"}]
    )

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_project_installation", return_value={"installation_id": "inst-123", "repo_full_name": "org/repo"}), \
         patch("services.github_service.get_installation_access_token", AsyncMock(return_value=None)):

        resp = client.post(
            "/projects/proj-1/generate-draft",
            headers={"Authorization": "Bearer token"},
        )
        assert resp.status_code == 502
        assert "GitHub is unavailable" in resp.json()["detail"]
        # Ensure insert was never called on contributions table
        for call in mock_supabase.table.call_args_list:
            if call[0][0] == "contributions":
                assert not mock_supabase.table.return_value.insert.called


def test_production_unsigned_or_invalid_webhook_returns_401(prod_mode):
    """In production, unsigned or invalid webhooks return 401 Unauthorized."""
    import hashlib
    import hmac

    payload = {"repository": {"full_name": "org/repo"}, "commits": []}
    body_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature header -> 401
    resp_no_sig = client.post(
        "/webhooks/github",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
    )
    assert resp_no_sig.status_code == 401
    assert "Missing webhook signature" in resp_no_sig.json()["detail"]

    # 2. Invalid signature header -> 401
    resp_bad_sig = client.post(
        "/webhooks/github",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=invalidhashvalue1234567890",
        },
    )
    assert resp_bad_sig.status_code == 401
    assert "Invalid webhook signature" in resp_bad_sig.json()["detail"]

    # 3. Valid signature header -> 200
    valid_sig = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    resp_valid = client.post(
        "/webhooks/github",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": valid_sig,
        },
    )
    assert resp_valid.status_code == 200


@pytest.mark.anyio
async def test_production_startup_fails_without_secret_keys(monkeypatch):
    """startup_check fails with RuntimeError if APP_SECRET_KEY or GITHUB_WEBHOOK_SECRET missing in production."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "ALLOW_DEV_AUTH", False)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "serv-key")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "pub-key")

    # Missing APP_SECRET_KEY
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "valid-webhook-secret")
    with pytest.raises(RuntimeError) as exc_a:
        await startup_check()
    assert "APP_SECRET_KEY" in str(exc_a.value)

    # Missing GITHUB_WEBHOOK_SECRET
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "valid-app-secret")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    with pytest.raises(RuntimeError) as exc_b:
        await startup_check()
    assert "GITHUB_WEBHOOK_SECRET" in str(exc_b.value)

    # Both present -> succeeds without error
    monkeypatch.setattr(settings, "APP_SECRET_KEY", "valid-app-secret")
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "valid-webhook-secret")
    await startup_check()


@pytest.mark.anyio
async def test_github_service_exchange_code_and_get_user_installations():
    """Verify exchange_code_for_user_token and get_user_installations service methods."""
    # 1. Missing credentials returns None
    with patch.object(settings, "GITHUB_CLIENT_ID", ""), patch.object(settings, "GITHUB_CLIENT_SECRET", ""):
        token = await github_service.exchange_code_for_user_token("code-123")
        assert token is None

    # 2. Successful exchange
    with patch.object(settings, "GITHUB_CLIENT_ID", "client-id-123"), \
         patch.object(settings, "GITHUB_CLIENT_SECRET", "client-secret-123"), \
         patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "ghu_valid_oauth_token"},
        )
        token = await github_service.exchange_code_for_user_token("code-123")
        assert token == "ghu_valid_oauth_token"

    # 3. Successful get_user_installations
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"installations": [{"id": 55555}, {"id": 66666}]},
        )
        installations = await github_service.get_user_installations("ghu_valid_oauth_token")
        assert len(installations) == 2
        assert installations[0]["id"] == 55555

    # 4. Empty token returns empty list
    assert await github_service.get_user_installations("") == []




