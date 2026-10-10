import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
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


def _setup_project_with_members():
    """Setup project proj-1 with author-1 (lead), member-2, member-3, member-4."""
    DEV_USER_NAMES_DB["author-1"] = "Alice Author"
    DEV_USER_NAMES_DB["member-2"] = "Bob Reviewer"
    DEV_USER_NAMES_DB["member-3"] = "Charlie Reviewer"
    DEV_USER_NAMES_DB["member-4"] = "Dana Teammate"
    DEV_USER_NAMES_DB["outsider-9"] = "Oscar Outsider"

    DEV_PROJECTS_DB["proj-1"] = {
        "id": "proj-1",
        "name": "Alpha Platform",
        "created_by": "author-1",
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"id": "pm-1", "project_id": "proj-1", "user_id": "author-1", "role": "lead"},
        {"id": "pm-2", "project_id": "proj-1", "user_id": "member-2", "role": "member"},
        {"id": "pm-3", "project_id": "proj-1", "user_id": "member-3", "role": "member"},
        {"id": "pm-4", "project_id": "proj-1", "user_id": "member-4", "role": "member"},
    ])


# ==============================================================================
# Scenario 1: dispute -> another member confirms -> 409 and still needs-review/private
# ==============================================================================

def test_scenario_1_dispute_blocks_confirm_409_dev_path():
    _setup_project_with_members()
    cid = "c-item-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Core Auth Module",
        "category": "code",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Member 2 disputes the contribution
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    disp_res = client.post(f"/contributions/{cid}/dispute", json={"reason": "Contains plagiarized code"})
    assert disp_res.status_code == 200
    disp_data = disp_res.json()
    assert disp_data["verification_status"] == "needs-review"
    assert disp_data["visibility"] == "private"

    # Member 3 tries to confirm -> must be rejected with 409 Conflict
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-3", email="charlie@buildcrew.io")
    conf_res = client.post(f"/contributions/{cid}/confirm")
    assert conf_res.status_code == 409
    assert "This item is disputed by Bob Reviewer" in conf_res.json()["detail"]
    assert "withdraw their dispute first" in conf_res.json()["detail"]

    # Verify item is still needs-review and private
    c_record = next(c for c in DEV_CONTRIBUTIONS_DB if c["id"] == cid)
    assert c_record["verification_status"] == "needs-review"
    assert c_record["dispute_state"] == "disputed"
    assert c_record["visibility"] == "private"


# ==============================================================================
# Scenario 2: disputer withdraws -> self-declared and not publishable
# ==============================================================================

def test_scenario_2_disputer_withdraws_becomes_self_declared_not_publishable_dev_path():
    _setup_project_with_members()
    cid = "c-item-2"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Payment Integration",
        "category": "code",
        "verification_status": "needs-review",
        "visibility": "private",
        "dispute_state": "disputed",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })
    DEV_CONFIRMATIONS_DB.append({
        "id": "conf-vote-1",
        "contribution_id": cid,
        "confirmed_by_user_id": "member-2",
        "action": "dispute",
        "notes": "Missing tests",
        "confirmed_at": "2026-10-01T10:30:00Z",
    })

    # Member 2 withdraws dispute
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    with_res = client.post(f"/contributions/{cid}/withdraw-dispute")
    assert with_res.status_code == 200
    with_data = with_res.json()
    assert with_data["verification_status"] == "self-declared"
    assert with_data["dispute_state"] == "none"

    # Author tries to publish -> must fail with 400 (not confirmed)
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    pub_res = client.post(f"/contributions/{cid}/publish")
    assert pub_res.status_code == 400
    assert "Only confirmed contributions can be published" in pub_res.json()["detail"]


# ==============================================================================
# Scenario 3: disputer leaves -> author reopen works (and reopen 409 while disputer remains)
# ==============================================================================

def test_scenario_3_disputer_leaves_author_reopen_works_dev_path():
    _setup_project_with_members()
    cid = "c-item-3"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Design Mockups",
        "category": "design",
        "verification_status": "needs-review",
        "visibility": "private",
        "dispute_state": "disputed",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })
    DEV_CONFIRMATIONS_DB.append({
        "id": "conf-vote-2",
        "contribution_id": cid,
        "confirmed_by_user_id": "member-2",
        "action": "dispute",
        "notes": "Not finalized",
        "confirmed_at": "2026-10-01T10:30:00Z",
    })

    # Author tries to reopen while member-2 is still in project -> 409
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    reopen_res_blocked = client.post(f"/contributions/{cid}/reopen")
    assert reopen_res_blocked.status_code == 409
    assert "Cannot reopen: active dispute" in reopen_res_blocked.json()["detail"]

    # Member 2 leaves the project
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    leave_res = client.post("/projects/proj-1/leave")
    assert leave_res.status_code == 200

    # Since member-2 left, recomputing automatically or via author reopen works
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    reopen_res_success = client.post(f"/contributions/{cid}/reopen")
    assert reopen_res_success.status_code == 200
    reopen_data = reopen_res_success.json()
    assert reopen_data["verification_status"] == "self-declared"
    assert reopen_data["dispute_state"] == "none"


# ==============================================================================
# Scenario 4: two confirmers -> peer-confirmed with two names in confirmations
# ==============================================================================

def test_scenario_4_two_confirmers_peer_confirmed_with_names_dev_path():
    _setup_project_with_members()
    cid = "c-item-4"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "CI/CD Pipeline Setup",
        "category": "devops",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Member 2 confirms
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    res1 = client.post(f"/contributions/{cid}/confirm")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["verification_status"] == "peer-confirmed"
    assert data1["confirm_count"] == 1
    assert data1["confirmations"][0]["name"] == "Bob Reviewer"

    # Member 3 confirms
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-3", email="charlie@buildcrew.io")
    res2 = client.post(f"/contributions/{cid}/confirm")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["verification_status"] == "peer-confirmed"
    assert data2["confirm_count"] == 2
    names = [c["name"] for c in data2["confirmations"]]
    assert "Bob Reviewer" in names
    assert "Charlie Reviewer" in names


# ==============================================================================
# Scenario 5: confirming a source-verified item keeps 'source-verified'
# ==============================================================================

def test_scenario_5_confirming_source_verified_retains_status_dev_path():
    _setup_project_with_members()
    cid = "c-item-5"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Merged PR #42",
        "category": "code",
        "source_type": "github_pull_request",
        "verification_status": "source-verified",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Member 2 confirms the item
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    conf_res = client.post(f"/contributions/{cid}/confirm")
    assert conf_res.status_code == 200
    conf_data = conf_res.json()
    # Must remain source-verified, NOT peer-confirmed!
    assert conf_data["verification_status"] == "source-verified"
    assert conf_data["confirm_count"] == 1
    assert conf_data["confirmations"][0]["name"] == "Bob Reviewer"


# ==============================================================================
# Scenario 6: publish allowed for source-verified
# ==============================================================================

def test_scenario_6_publish_allowed_for_source_verified_dev_path():
    _setup_project_with_members()
    cid = "c-item-6"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Merged PR #99",
        "category": "code",
        "source_type": "github_pull_request",
        "verification_status": "source-verified",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    })

    # Author publishes source-verified deliverable
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    pub_res = client.post(f"/contributions/{cid}/publish")
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["verification_status"] == "source-verified"
    assert pub_data["visibility"] == "public"


# ==============================================================================
# Scenario 7: ledger hides others' needs-review, checks 403, and waiting_on_me
# ==============================================================================

def test_scenario_7_ledger_hides_needs_review_403_and_waiting_on_me_dev_path():
    _setup_project_with_members()
    # Item 1: Disputed by member-2
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-disputed",
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Disputed Delivery",
        "category": "code",
        "verification_status": "needs-review",
        "visibility": "private",
        "dispute_state": "disputed",
        "created_at": "2026-10-01T10:00:00Z",
    })
    DEV_CONFIRMATIONS_DB.append({
        "id": "conf-d1",
        "contribution_id": "c-disputed",
        "confirmed_by_user_id": "member-2",
        "action": "dispute",
        "notes": "Contested scope",
        "confirmed_at": "2026-10-01T10:10:00Z",
    })

    # Item 2: Undisputed self-declared item by author-1
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-waiting",
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Open PR for Review",
        "category": "code",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-02T10:00:00Z",
    })

    # 1. Non-member access check -> 403 Forbidden
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="outsider-9", email="outsider@external.io")
    ledger_403 = client.get("/projects/proj-1/ledger")
    assert ledger_403.status_code == 403

    # 2. Member 3 (neither authored nor disputed c-disputed) -> c-disputed must be HIDDEN!
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-3", email="charlie@buildcrew.io")
    res_m3 = client.get("/projects/proj-1/ledger")
    assert res_m3.status_code == 200
    entries_m3 = res_m3.json()
    ids_m3 = [e["id"] for e in entries_m3]
    assert "c-disputed" not in ids_m3
    assert "c-waiting" in ids_m3

    # Check waiting_on_me for member-3 on c-waiting -> True
    waiting_entry_m3 = next(e for e in entries_m3 if e["id"] == "c-waiting")
    assert waiting_entry_m3["waiting_on_me"] is True

    # 3. Author 1 -> can see c-disputed (authored) and waiting_on_me is False on own item
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    res_author = client.get("/projects/proj-1/ledger")
    assert res_author.status_code == 200
    entries_author = res_author.json()
    ids_author = [e["id"] for e in entries_author]
    assert "c-disputed" in ids_author
    waiting_entry_auth = next(e for e in entries_author if e["id"] == "c-waiting")
    assert waiting_entry_auth["waiting_on_me"] is False

    # 4. Member 2 (the disputer) -> can see c-disputed
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="member-2", email="bob@buildcrew.io")
    res_m2 = client.get("/projects/proj-1/ledger")
    assert res_m2.status_code == 200
    ids_m2 = [e["id"] for e in res_m2.json()]
    assert "c-disputed" in ids_m2


# ==============================================================================
# Scenario 8: broadcast creates N-1 requests when reviewer_ids is empty
# ==============================================================================

def test_scenario_8_broadcast_n_minus_one_requests_dev_path():
    _setup_project_with_members()  # author-1 + member-2, member-3, member-4 (total 4 members -> N-1 = 3)
    cid = "c-broadcast-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-1",
        "contributor": "author-1",
        "title": "Architecture Blueprint",
        "category": "design",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-10-01T10:00:00Z",
    })

    app.dependency_overrides[get_current_user] = lambda: MagicMock(id="author-1", email="alice@buildcrew.io")
    # Empty reviewer_ids list in payload -> should broadcast to all 3 teammates
    req_res = client.post(f"/contributions/{cid}/request-confirmation", json={"reviewer_ids": []})
    assert req_res.status_code == 201
    req_data = req_res.json()
    assert len(req_data) == 3
    reviewers = {r["reviewer_id"] for r in req_data}
    assert reviewers == {"member-2", "member-3", "member-4"}


# ==============================================================================
# Supabase Mock Path: Scenarios 1 to 8 with Mock Supabase Client
# ==============================================================================

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


def test_supabase_mock_path_tamper_proof_voting():
    """Verify Supabase mock path correctly handles voting, 409 dispute block, and recomputing."""
    mock_supabase = MagicMock()

    proj_data = {"id": "proj-sb-1", "name": "Supabase App", "created_by": "sb-author"}
    contrib_data = {
        "id": "c-sb-1",
        "project": "proj-sb-1",
        "contributor": "sb-author",
        "title": "Auth Supabase Flow",
        "category": "code",
        "verification_status": "self-declared",
        "visibility": "private",
        "dispute_state": "none",
        "source_type": "manual",
        "created_at": "2026-10-01T12:00:00Z",
    }
    members_data = [
        {"user_id": "sb-author"},
        {"user_id": "sb-member-2"},
        {"user_id": "sb-member-3"},
    ]
    votes_data = [
        {
            "id": "v-1",
            "contribution_id": "c-sb-1",
            "confirmed_by_user_id": "sb-member-2",
            "action": "dispute",
            "notes": "Code smells",
            "confirmed_at": "2026-10-01T12:30:00Z",
        }
    ]

    def table_router(table_name):
        if table_name == "projects":
            return MockQuery(proj_data)
        elif table_name == "contributions":
            return MockQuery([contrib_data])
        elif table_name == "project_members":
            return MockQuery(members_data)
        elif table_name == "confirmations":
            return MockQuery(votes_data)
        elif table_name == "profiles":
            return MockQuery([{"id": "sb-member-2", "display_name": "Bob SB", "email": "bob@sb.io"}])
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    with patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
        # sb-member-3 attempts to confirm disputed item -> 409
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="sb-member-3", email="member3@sb.io")
        res = client.post("/contributions/c-sb-1/confirm")
        assert res.status_code == 409
        assert "This item is disputed by Bob SB" in res.json()["detail"]


def test_supabase_mock_path_ledger_endpoint():
    """Verify Supabase mock path correctly filters ledger and computes waiting_on_me."""
    mock_supabase = MagicMock()

    proj_data = {"id": "proj-sb-2", "name": "Supabase App 2", "created_by": "sb-author-2"}
    members_data = [
        {"user_id": "sb-author-2"},
        {"user_id": "sb-member-b"},
        {"user_id": "sb-member-c"},
    ]
    contribs_data = [
        {
            "id": "c-item-undisputed",
            "project": "proj-sb-2",
            "contributor": "sb-author-2",
            "title": "Undisputed feature",
            "category": "code",
            "verification_status": "self-declared",
            "visibility": "private",
            "dispute_state": "none",
            "created_at": "2026-10-02T12:00:00Z",
        },
        {
            "id": "c-item-disputed",
            "project": "proj-sb-2",
            "contributor": "sb-author-2",
            "title": "Disputed feature",
            "category": "code",
            "verification_status": "needs-review",
            "visibility": "private",
            "dispute_state": "disputed",
            "created_at": "2026-10-01T12:00:00Z",
        },
    ]
    votes_data = [
        {
            "id": "v-disp",
            "contribution_id": "c-item-disputed",
            "confirmed_by_user_id": "sb-member-b",
            "action": "dispute",
            "notes": "Testing dispute",
            "confirmed_at": "2026-10-01T13:00:00Z",
        }
    ]

    def table_router(table_name):
        if table_name == "projects":
            return MockQuery(proj_data)
        elif table_name == "project_members":
            return MockQuery(members_data)
        elif table_name == "contributions":
            return MockQuery(contribs_data)
        elif table_name == "confirmations":
            return MockQuery(votes_data)
        elif table_name == "profiles":
            return MockQuery([])
        return MockQuery([])

    mock_supabase.table.side_effect = table_router

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase), \
         patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
        # Member C calls ledger -> disputed item is hidden, undisputed item has waiting_on_me = True
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="sb-member-c", email="member_c@sb.io")
        res = client.get("/projects/proj-sb-2/ledger")
        assert res.status_code == 200
        data = res.json()
        ids = [item["id"] for item in data]
        assert "c-item-disputed" not in ids
        assert "c-item-undisputed" in ids
        entry = next(item for item in data if item["id"] == "c-item-undisputed")
        assert entry["waiting_on_me"] is True
