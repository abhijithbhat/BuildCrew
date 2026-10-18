import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import httpx
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_current_user
from routers.auth import DEV_USER_NAMES_DB
from routers.projects import (
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_ROLE_AGREEMENTS_DB,
    DEV_CONTRIBUTIONS_DB,
    DEV_CONFIRMATIONS_DB,
    DEV_CONFIRMATION_REQUESTS_DB,
)
from routers.contributions import (
    _get_project_member_ids,
    _get_contribution_votes,
    _recompute_contribution_status,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_databases():
    """Clear in-memory databases and dependency overrides before each test."""
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()
    DEV_USER_NAMES_DB.clear()
    app.dependency_overrides.clear()
    yield
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()
    DEV_USER_NAMES_DB.clear()
    app.dependency_overrides.clear()


class MockQuery:
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._single = False

    def select(self, *args, **kwargs):
        return self

    def insert(self, data, *args, **kwargs):
        if isinstance(data, list):
            self._data = data
        else:
            self._data = [data]
        return self

    def upsert(self, data, *args, **kwargs):
        if isinstance(data, list):
            self._data = data
        else:
            self._data = [data]
        return self

    def update(self, data, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def neq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        res = MagicMock()
        if self._single:
            if isinstance(self._data, list):
                res.data = self._data[0] if self._data else None
            else:
                res.data = self._data
        else:
            res.data = self._data if isinstance(self._data, list) else ([self._data] if self._data else [])
        return res


# ==============================================================================
# 1. Votes read times out during confirm -> 503 and status/dispute_state unchanged
# ==============================================================================

def test_votes_read_timeout_during_confirm_returns_503_and_status_unchanged():
    mock_supabase = MagicMock()

    proj_data = {"id": "proj-fail-1", "name": "Secure App", "created_by": "lead-1"}
    contrib_data = {
        "id": "c-timeout-1",
        "project": "proj-fail-1",
        "contributor": "lead-1",
        "title": "Database Engine",
        "category": "backend",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "source_type": "manual",
        "created_at": "2026-10-01T12:00:00Z",
        "updated_at": "2026-10-01T12:00:00Z",
    }
    members_data = [{"user_id": "lead-1"}, {"user_id": "teammate-2"}]

    def table_router(table_name):
        if table_name == "projects":
            return MockQuery(proj_data)
        elif table_name == "project_members":
            return MockQuery(members_data)
        elif table_name == "contributions":
            return MockQuery([contrib_data])
        elif table_name == "confirmations":
            q = MockQuery([])
            q.execute = MagicMock(side_effect=httpx.ReadTimeout("Upstream read timed out"))
            return q
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    # Run in production mode: is_dev_mode() is False
    with patch("core.database.is_dev_mode", return_value=False), \
         patch("routers.contributions.is_dev_mode", return_value=False), \
         patch("routers.projects.is_dev_mode", return_value=False), \
         patch("routers.contributions.get_supabase_client", return_value=mock_supabase), \
         patch("routers.projects.get_supabase_client", return_value=mock_supabase):

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="teammate-2", email="t2@buildcrew.io")
        response = client.post("/contributions/c-timeout-1/confirm")

        assert response.status_code == 503
        assert "Service temporarily unavailable" in response.json()["detail"] or "unavailable" in response.json()["detail"].lower()
        # Verify status and dispute_state are unchanged
        assert contrib_data["verification_status"] == "self-declared"
        assert contrib_data["dispute_state"] == "none"
        # Verify no dev store was touched
        assert len(DEV_CONFIRMATIONS_DB) == 0


# ==============================================================================
# 2. Confirmer leaves -> item stays peer-confirmed and stays on public passport
# ==============================================================================

def test_confirmer_leaves_item_stays_peer_confirmed_and_on_public_passport_dev_mode():
    DEV_USER_NAMES_DB["author-1"] = "Alice Author"
    DEV_USER_NAMES_DB["confirmer-2"] = "Bob Confirmer"
    DEV_PROJECTS_DB["proj-hist-1"] = {
        "id": "proj-hist-1",
        "name": "Historical App",
        "created_by": "author-1",
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"id": "pm-1", "project_id": "proj-hist-1", "user_id": "author-1", "role": "lead"},
        {"id": "pm-2", "project_id": "proj-hist-1", "user_id": "confirmer-2", "role": "member"},
    ])

    cid = "c-hist-item-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-hist-1",
        "contributor": "author-1",
        "title": "Auth Architecture",
        "category": "security",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Confirmer confirms the item
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="confirmer-2", email="bob@buildcrew.io")
    conf_res = client.post(f"/contributions/{cid}/confirm")
    assert conf_res.status_code == 200
    assert conf_res.json()["verification_status"] == "peer-confirmed"

    # Author publishes the item to passport
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    pub_res = client.post(f"/contributions/{cid}/publish")
    assert pub_res.status_code == 200
    assert pub_res.json()["visibility"] == "public"

    # Confirmer leaves the project
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="confirmer-2", email="bob@buildcrew.io")
    leave_res = client.post("/projects/proj-hist-1/leave")
    assert leave_res.status_code == 200

    # Confirmer is no longer in DEV_PROJECT_MEMBERS_DB
    remaining_members = [m["user_id"] for m in DEV_PROJECT_MEMBERS_DB if m.get("project_id") == "proj-hist-1"]
    assert "confirmer-2" not in remaining_members

    # Verify item status remains peer-confirmed (confirmations are historical facts!)
    c_record = next(c for c in DEV_CONTRIBUTIONS_DB if c["id"] == cid)
    assert c_record["verification_status"] == "peer-confirmed"
    assert c_record["visibility"] == "public"

    # Query public project-scoped passport with format=json
    passport_res = client.get("/passport/author-1/proj-hist-1?format=json")
    assert passport_res.status_code == 200
    passport_data = passport_res.json()
    assert passport_data["confirmed_count"] == 1
    items = passport_data["contributions"]
    assert len(items) == 1
    assert items[0]["id"] == cid
    assert items[0]["verification_status"] == "peer-confirmed"


def test_confirmer_account_deletion_leaves_stored_status_unchanged():
    """A confirmer's account deletion (vote row cascaded away) leaves stored status unchanged."""
    contrib = {
        "id": "c-cascaded-1",
        "project": "proj-c-1",
        "contributor": "author-1",
        "verification_status": "peer-confirmed",
        "dispute_state": "none",
        "visibility": "public",
        "confirmed_by": "deleted-user-99",
    }

    mock_supabase = MagicMock()
    # No votes in database (cascaded away when user deleted account)
    def table_router(table_name):
        if table_name == "projects":
            return MockQuery({"id": "proj-c-1", "created_by": "author-1"})
        elif table_name == "project_members":
            return MockQuery([{"user_id": "author-1"}])
        elif table_name == "confirmations":
            return MockQuery([])
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    recomputed = _recompute_contribution_status(mock_supabase, contrib)
    assert recomputed["verification_status"] == "peer-confirmed"
    assert recomputed["dispute_state"] == "none"
    assert recomputed["confirmed_by"] == "deleted-user-99"


# ==============================================================================
# 3. Disputer leaves -> dispute lapses and author can reopen
# ==============================================================================

def test_disputer_leaves_dispute_lapses_and_author_can_reopen_dev_mode():
    DEV_USER_NAMES_DB["author-1"] = "Alice Author"
    DEV_USER_NAMES_DB["disputer-2"] = "Bob Disputer"
    DEV_PROJECTS_DB["proj-disp-1"] = {
        "id": "proj-disp-1",
        "name": "Dispute Test App",
        "created_by": "author-1",
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"id": "pm-1", "project_id": "proj-disp-1", "user_id": "author-1", "role": "lead"},
        {"id": "pm-2", "project_id": "proj-disp-1", "user_id": "disputer-2", "role": "member"},
    ])

    cid = "c-disp-item-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-disp-1",
        "contributor": "author-1",
        "title": "API Gateway Implementation",
        "category": "code",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Disputer disputes the contribution
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="disputer-2", email="bob@buildcrew.io")
    disp_res = client.post(f"/contributions/{cid}/dispute", json={"reason": "Incomplete unit tests"})
    assert disp_res.status_code == 200
    assert disp_res.json()["verification_status"] == "needs-review"

    # Author tries to reopen while disputer is still on the team -> 409
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    reopen_fail = client.post(f"/contributions/{cid}/reopen")
    assert reopen_fail.status_code == 409
    assert "active dispute from Bob Disputer still exists" in reopen_fail.json()["detail"]

    # Disputer leaves the project
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="disputer-2", email="bob@buildcrew.io")
    leave_res = client.post("/projects/proj-disp-1/leave")
    assert leave_res.status_code == 200

    # Author reopens contribution -> dispute lapses, 200 OK!
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    reopen_success = client.post(f"/contributions/{cid}/reopen")
    assert reopen_success.status_code == 200
    data = reopen_success.json()
    assert data["verification_status"] == "self-declared"
    assert data["dispute_state"] == "none"


# ==============================================================================
# 4. Strict Publish Guard: non-source-verified item with active dispute returns 409
# ==============================================================================

def test_publish_non_source_verified_with_active_dispute_returns_409():
    DEV_USER_NAMES_DB["author-1"] = "Alice Author"
    DEV_USER_NAMES_DB["member-2"] = "Bob Member"
    DEV_PROJECTS_DB["proj-pub-1"] = {
        "id": "proj-pub-1",
        "name": "Pub Test App",
        "created_by": "author-1",
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"id": "pm-1", "project_id": "proj-pub-1", "user_id": "author-1", "role": "lead"},
        {"id": "pm-2", "project_id": "proj-pub-1", "user_id": "member-2", "role": "member"},
    ])

    cid = "c-pub-disp-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-pub-1",
        "contributor": "author-1",
        "title": "Manual Test Document",
        "category": "testing",
        "source_type": "manual",
        "verification_status": "peer-confirmed",
        "visibility": "private",
        "dispute_state": "disputed",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })
    DEV_CONFIRMATIONS_DB.append({
        "id": "conf-disp-1",
        "contribution_id": cid,
        "confirmed_by_user_id": "member-2",
        "action": "dispute",
        "notes": "Testing incomplete",
        "confirmed_at": "2026-10-01T11:00:00Z",
    })

    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    pub_res = client.post(f"/contributions/{cid}/publish")
    assert pub_res.status_code == 409
    assert "currently disputed" in pub_res.json()["detail"]


# ==============================================================================
# 5. Production mode: fail closed, no DEV store is touched, updates raise
# ==============================================================================

def test_no_dev_store_touched_in_production_mode():
    mock_supabase = MagicMock()

    proj_data = {"id": "proj-prod-1", "name": "Production App", "created_by": "lead-prod"}
    contrib_data = {
        "id": "c-prod-1",
        "project": "proj-prod-1",
        "contributor": "lead-prod",
        "title": "Prod Code",
        "category": "code",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "source_type": "manual",
        "created_at": "2026-10-01T12:00:00Z",
        "updated_at": "2026-10-01T12:00:00Z",
    }
    members_data = [{"user_id": "lead-prod"}, {"user_id": "member-prod-2"}]
    votes_data = []

    def table_router(table_name):
        if table_name == "projects":
            return MockQuery(proj_data)
        elif table_name == "project_members":
            return MockQuery(members_data)
        elif table_name == "contributions":
            return MockQuery([contrib_data])
        elif table_name == "confirmations":
            q = MockQuery(votes_data)
            def do_upsert(data, *args, **kwargs):
                item = data if isinstance(data, dict) else data[0]
                votes_data[:] = [
                    v for v in votes_data
                    if not (v.get("contribution_id") == item.get("contribution_id") and v.get("confirmed_by_user_id") == item.get("confirmed_by_user_id"))
                ]
                votes_data.append(item)
                return q
            q.upsert = do_upsert
            return q
        elif table_name == "profiles":
            return MockQuery([{"id": "member-prod-2", "display_name": "Prod Reviewer"}])
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    # Ensure DEV stores are empty
    DEV_CONFIRMATIONS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_PROJECTS_DB.clear()

    with patch("core.database.is_dev_mode", return_value=False), \
         patch("routers.contributions.is_dev_mode", return_value=False), \
         patch("routers.projects.is_dev_mode", return_value=False), \
         patch("routers.contributions.get_supabase_client", return_value=mock_supabase), \
         patch("routers.projects.get_supabase_client", return_value=mock_supabase):

        # Member confirms item
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-prod-2", email="m2@prod.io")
        res_conf = client.post("/contributions/c-prod-1/confirm")
        assert res_conf.status_code == 200

        # Verify DEV_CONFIRMATIONS_DB was NOT appended to
        assert len(DEV_CONFIRMATIONS_DB) == 0

        # Verify DEV_CONTRIBUTIONS_DB was NOT populated
        assert len(DEV_CONTRIBUTIONS_DB) == 0

        # Member disputes item
        res_disp = client.post("/contributions/c-prod-1/dispute", json={"reason": "Prod dispute test"})
        assert res_disp.status_code == 200
        assert len(DEV_CONFIRMATIONS_DB) == 0


def test_recompute_status_update_failure_raises_in_production():
    """When is_dev_mode() is False, the status UPDATE inside _recompute_contribution_status must raise."""
    mock_supabase = MagicMock()
    proj_data = {"id": "proj-upd-fail", "created_by": "lead-1"}
    members_data = [{"user_id": "lead-1"}, {"user_id": "member-2"}]
    contrib = {
        "id": "c-upd-fail",
        "project": "proj-upd-fail",
        "contributor": "lead-1",
        "verification_status": "self-declared",
        "dispute_state": "none",
        "visibility": "private",
    }
    votes_data = [
        {
            "id": "v-1",
            "contribution_id": "c-upd-fail",
            "confirmed_by_user_id": "member-2",
            "action": "confirm",
            "confirmed_at": "2026-10-01T12:00:00Z",
        }
    ]

    def table_router(table_name):
        if table_name == "projects":
            return MockQuery(proj_data)
        elif table_name == "project_members":
            return MockQuery(members_data)
        elif table_name == "confirmations":
            return MockQuery(votes_data)
        elif table_name == "contributions":
            q = MockQuery([])
            q.update = MagicMock(return_value=q)
            q.eq = MagicMock(return_value=q)
            q.execute = MagicMock(side_effect=RuntimeError("Database connection dropped during status UPDATE"))
            return q
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    with patch("core.database.is_dev_mode", return_value=False), \
         patch("routers.contributions.is_dev_mode", return_value=False):
        with pytest.raises(RuntimeError, match="Database connection dropped during status UPDATE"):
            _recompute_contribution_status(mock_supabase, contrib)
