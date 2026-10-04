import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_PROJECT_INVITES_DB,
    reset_join_rate_limiter,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    reset_join_rate_limiter()
    DEV_PROJECT_INVITES_DB.clear()
    app.dependency_overrides.clear()
    yield
    reset_join_rate_limiter()
    DEV_PROJECT_INVITES_DB.clear()
    app.dependency_overrides.clear()


def test_generate_invite_returns_existing_code_if_set():
    """If project.invite_code is already set, generate_project_invite returns it without updating."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={
            "id": "proj-existing",
            "name": "Existing Code Project",
            "created_by": "user-lead",
            "invite_code": "BC-EXIST123",
        }
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # Member check
    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-existing", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-existing/invite", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["invite_code"] == "BC-EXIST123"
        assert data.get("invite_url") is None
        # Verify update was NOT called because code was already set
        assert mock_proj_table.update.call_count == 0


def test_generate_invite_creates_and_persists_when_not_set():
    """If project.invite_code is None, generate_project_invite generates one and updates projects table."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={
            "id": "proj-new",
            "name": "New Project",
            "created_by": "user-lead",
            "invite_code": None,
        }
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    mock_update = MagicMock()
    mock_update.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-new"}])
    mock_proj_table.update.return_value = mock_update

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-new", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-new/invite", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["invite_code"].startswith("BC-")
        assert data.get("invite_url") is None
        # Verify update was called with the generated invite_code
        mock_proj_table.update.assert_called_once()
        update_args = mock_proj_table.update.call_args[0][0]
        assert update_args["invite_code"] == data["invite_code"]


def test_generate_invite_retries_on_unique_violation():
    """If update hits unique violation on invite_code, it retries up to 5 times."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-retry", "name": "Retry Project", "created_by": "user-lead", "invite_code": None}
    )

    # Fail twice with unique violation, then succeed on 3rd attempt
    call_count = 0

    def mock_update_exec():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("duplicate key value violates unique constraint 'projects_invite_code_key'")
        return MagicMock(data=[{"id": "proj-retry"}])

    mock_update = MagicMock()
    mock_update.eq.return_value.execute.side_effect = mock_update_exec
    mock_proj_table.update.return_value = mock_update

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-retry", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-retry/invite", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        assert call_count == 3
        assert resp.json()["invite_code"].startswith("BC-")


def test_generate_invite_fails_after_5_unique_violations():
    """If all 5 attempts fail with unique violation, returns 500."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-fail-unique", "name": "Unique Fail", "created_by": "user-lead", "invite_code": None}
    )

    mock_update = MagicMock()
    mock_update.eq.return_value.execute.side_effect = Exception("23505 unique constraint violation")
    mock_proj_table.update.return_value = mock_update

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-fail-unique", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-fail-unique/invite", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 500
        assert "unique invite code" in resp.json()["detail"].lower()


def test_regenerate_invite_code_overwrites_code_for_team_lead():
    """Team lead can regenerate invite code, which overwrites projects.invite_code."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-regen", "name": "Regen Project", "created_by": "user-lead", "invite_code": "BC-OLDCODE"}
    )
    mock_update = MagicMock()
    mock_update.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-regen"}])
    mock_proj_table.update.return_value = mock_update

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-regen", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-regen/invite/regenerate", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["invite_code"] != "BC-OLDCODE"
        assert data["invite_code"].startswith("BC-")
        mock_proj_table.update.assert_called_once()
        assert mock_proj_table.update.call_args[0][0]["invite_code"] == data["invite_code"]


def test_regenerate_invite_code_forbidden_for_non_lead():
    """Non-lead project member receives 403 on regenerate."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-regen-403", "name": "403 Project", "created_by": "user-lead", "invite_code": "BC-EXIST"}
    )

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-regen-403", "user_id": "user-regular", "role": "member"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-regular", email="reg@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-regen-403/invite/regenerate", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 403
        assert "Only the Team Lead" in resp.json()["detail"]


def test_join_case_insensitive_lookup():
    """Look up projects where upper(invite_code) = upper(submitted code)."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.ilike.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "proj-case-1",
                "name": "Case Project",
                "invite_code": "BC-UPPER99",
                "created_by": "user-creator",
            }
        ]
    )

    mock_member_table = MagicMock()
    # Not already a member
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_member_table.insert.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-case-1", "user_id": "user-joiner", "role": "member"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-joiner", email="joiner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # Submitting in lowercase
        resp = client.post("/projects/join", json={"invite_code": "bc-upper99"}, headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Successfully joined project"
        assert resp.json()["project"]["id"] == "proj-case-1"


def test_join_invalid_code_generic_404():
    """Invalid invite code returns a generic 404 'Invalid invite code'."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.ilike.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_proj_table

    mock_user = MagicMock(id="user-joiner", email="joiner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/join", json={"invite_code": "BC-DOESNOTEXIST"}, headers={"Authorization": "Bearer token"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Invalid invite code"


def test_join_rate_limit_10_per_minute_per_user():
    """Rate-limit POST /projects/join to 10/minute per user."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.ilike.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_proj_table

    user_a = MagicMock(id="user-rate-limited", email="ratelimited@example.com")
    app.dependency_overrides[get_current_user] = lambda: user_a

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # First 10 requests should succeed or return 404 (not 429)
        for i in range(10):
            resp = client.post(
                "/projects/join",
                json={"invite_code": f"BC-CODE-{i}"},
                headers={"Authorization": "Bearer token"},
            )
            assert resp.status_code == 404

        # 11th request MUST be rejected with 429 Too Many Requests
        resp11 = client.post(
            "/projects/join",
            json={"invite_code": "BC-CODE-11"},
            headers={"Authorization": "Bearer token"},
        )
        assert resp11.status_code == 429
        assert "Rate limit exceeded" in resp11.json()["detail"] or "Too many join attempts" in resp11.json()["detail"]
        assert "Retry-After" in resp11.headers

        # Different user (User B) should NOT be blocked
        user_b = MagicMock(id="user-fresh", email="fresh@example.com")
        app.dependency_overrides[get_current_user] = lambda: user_b
        resp_b = client.post(
            "/projects/join",
            json={"invite_code": "BC-CODE-B"},
            headers={"Authorization": "Bearer token"},
        )
        assert resp_b.status_code == 404


def test_non_dev_paths_do_not_touch_dev_invites_cache():
    """Non-development operations do not populate DEV_PROJECT_INVITES_DB."""
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-non-dev", "name": "Non Dev", "created_by": "user-lead", "invite_code": None}
    )
    mock_proj_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-non-dev"}])

    mock_member_table = MagicMock()
    mock_member_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-non-dev", "user_id": "user-lead", "role": "owner"}]
    )

    def table_router(name):
        if name == "projects":
            return mock_proj_table
        elif name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECT_INVITES_DB.clear()
    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.post("/projects/proj-non-dev/invite", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        # DEV_PROJECT_INVITES_DB must remain completely empty!
        assert len(DEV_PROJECT_INVITES_DB) == 0


def test_github_installations_last_generated_at_written():
    """Draft generation writes github_installations.last_generated_at."""
    mock_supabase = MagicMock()

    mock_proj = MagicMock()
    mock_proj.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-gh", "name": "GH Proj", "created_by": "user-123"}
    )

    mock_mem = MagicMock()
    mock_mem.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"project_id": "proj-gh", "user_id": "user-123", "role": "owner"}]
    )

    mock_inst = MagicMock()
    mock_inst.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "inst-1",
            "project_id": "proj-gh",
            "installation_id": "123456",
            "repo_full_name": "buildcrew/app",
            "connected_at": "2026-08-01T00:00:00Z",
        }]
    )
    mock_inst.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_contrib = MagicMock()
    mock_contrib.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_contrib.insert.return_value.execute.return_value = MagicMock(data=[])

    def table_router(name):
        if name == "projects":
            return mock_proj
        elif name == "project_members":
            return mock_mem
        elif name == "github_installations":
            return mock_inst
        elif name == "contributions":
            return mock_contrib
        elif name == "profiles":
            mock_p = MagicMock()
            mock_p.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "user-123", "email": "lead@buildcrew.io"}])
            return mock_p
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.fetch_repository_commits", return_value=[]), \
         patch("services.github_service.fetch_repository_pulls", return_value=[]), \
         patch("services.github_service.fetch_repository_issues", return_value=[]):
        resp = client.post("/projects/proj-gh/generate-draft", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 200
        mock_inst.update.assert_called_once()
        update_call_args = mock_inst.update.call_args[0][0]
        assert "last_generated_at" in update_call_args
