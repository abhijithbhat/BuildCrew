import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_CONTRIBUTIONS_DB,
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    _match_author_to_member,
)
from services import github_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_state():
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    github_service.DEV_GITHUB_INSTALLATIONS_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    github_service.DEV_GITHUB_INSTALLATIONS_DB.clear()


# ==============================================================================
# 1. Author Matching Engine Unit Tests
# ==============================================================================

def test_author_matching_by_github_username():
    members = [
        {"user_id": "u-1", "github_username": "alice-gh", "email": "alice@corp.com", "display_name": "Alice Smith"},
        {"user_id": "u-2", "github_username": "bob-gh", "email": "bob@corp.com", "display_name": "Bob Jones"},
    ]
    matched = _match_author_to_member(
        author_login="alice-gh",
        author_email="unknown@random.org",
        author_name="Alice S",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-1"


def test_author_matching_by_github_username_case_insensitive():
    members = [
        {"user_id": "u-1", "github_username": "Alice-GH", "email": "alice@corp.com", "display_name": "Alice Smith"},
    ]
    matched = _match_author_to_member(
        author_login="alice-gh",
        author_email="different@email.com",
        author_name="Alice",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-1"


def test_author_matching_by_email():
    members = [
        {"user_id": "u-1", "github_username": "alice-gh", "email": "alice@corp.com", "display_name": "Alice Smith"},
        {"user_id": "u-2", "github_username": "bob-gh", "email": "bob@corp.com", "display_name": "Bob Jones"},
    ]
    matched = _match_author_to_member(
        author_login="some-unregistered-handle",
        author_email="bob@corp.com",
        author_name="Robert",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-2"


def test_author_matching_by_email_case_insensitive():
    members = [
        {"user_id": "u-2", "github_username": "bob-gh", "email": "Bob@Corp.COM", "display_name": "Bob Jones"},
    ]
    matched = _match_author_to_member(
        author_login="unmatched",
        author_email="bob@corp.com",
        author_name="",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-2"


def test_author_matching_by_github_noreply_email():
    members = [
        {"user_id": "u-1", "github_username": "dev-alice", "email": "alice@corp.com", "display_name": "Alice"},
    ]
    # Standard GitHub privacy email: 12345+dev-alice@users.noreply.github.com
    matched = _match_author_to_member(
        author_login=None,
        author_email="987654+dev-alice@users.noreply.github.com",
        author_name="Alice S",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-1"


def test_author_matching_by_email_local_prefix():
    members = [
        {"user_id": "u-3", "github_username": "charlie_code", "email": "charlie@buildcrew.io", "display_name": "Charlie"},
    ]
    matched = _match_author_to_member(
        author_login=None,
        author_email="charlie@anotherdomain.com",
        author_name="C. D.",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-3"


def test_author_matching_by_name():
    members = [
        {"user_id": "u-1", "github_username": "alice-gh", "email": "alice@corp.com", "display_name": "Alice Smith"},
    ]
    matched = _match_author_to_member(
        author_login="",
        author_email="other@corp.com",
        author_name="Alice Smith",
        members=members,
        fallback_user_id="fallback-uid",
    )
    assert matched == "u-1"


def test_author_matching_fallback():
    members = [
        {"user_id": "u-1", "github_username": "alice-gh", "email": "alice@corp.com", "display_name": "Alice Smith"},
    ]
    matched = _match_author_to_member(
        author_login="unknown-bot",
        author_email="bot@service.com",
        author_name="Automated Bot",
        members=members,
        fallback_user_id="lead-user-id",
    )
    assert matched == "lead-user-id"


# ==============================================================================
# 2. Endpoint Authorization & Error Handling Tests
# ==============================================================================

def test_generate_draft_unauthenticated():
    response = client.post("/projects/proj-123/generate-draft")
    assert response.status_code in (401, 403)


def test_generate_draft_project_not_found():
    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.post("/projects/non-existent-proj/generate-draft")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_generate_draft_forbidden_non_member():
    mock_user = MagicMock(id="user-999", email="stranger@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Create project owned by user-123
    DEV_PROJECTS_DB["proj-100"] = {
        "id": "proj-100",
        "name": "Secret Project",
        "created_by": "user-123",
    }

    response = client.post("/projects/proj-100/generate-draft")
    assert response.status_code == 403
    assert "member" in response.json()["detail"].lower()


def test_generate_draft_no_github_repository_connected():
    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-100"] = {
        "id": "proj-100",
        "name": "Test Project",
        "created_by": "user-123",
    }

    response = client.post("/projects/proj-100/generate-draft")
    assert response.status_code == 400
    assert "not connected to a github repository" in response.json()["detail"].lower()


# ==============================================================================
# 3. Successful Draft Generation & Source-Verified Status Tests
# ==============================================================================

def test_generate_draft_success_dev_mode():
    mock_user = MagicMock(id="user-123", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Set up project and members in Dev DB
    DEV_PROJECTS_DB["proj-100"] = {
        "id": "proj-100",
        "name": "BuildCrew App",
        "created_by": "user-123",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-100",
        "user_id": "user-456",
        "role": "contributor",
    })

    # Link GitHub repo
    github_service.DEV_GITHUB_INSTALLATIONS_DB["proj-100"] = {
        "id": "inst-rec-1",
        "project_id": "proj-100",
        "installation_id": "inst-12345",
        "repo_full_name": "buildcrew/buildcrew-core",
        "connected_at": "2026-08-15T00:00:00Z",
    }

    response = client.post("/projects/proj-100/generate-draft")
    assert response.status_code == 200
    data = response.json()

    assert data["project_id"] == "proj-100"
    assert data["generated_count"] > 0
    assert "Successfully generated" in data["message"]
    assert len(data["contributions"]) > 0

    # Verify all generated records have status 'source-verified'
    for c in data["contributions"]:
        assert c["verification_status"] == "source-verified"
        assert c["project"] == "proj-100"
        assert c["evidence_link"] is not None
        assert c["source_type"] in ("github_commit", "github_pr", "github_issue")

    # Verify deduplication on subsequent call: running generate-draft again should not create duplicate records
    second_response = client.post("/projects/proj-100/generate-draft")
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["generated_count"] == 0


def test_list_project_contributions_dev_mode():
    mock_user = MagicMock(id="user-123", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-200"] = {
        "id": "proj-200",
        "name": "Test Project",
        "created_by": "user-123",
    }

    # Generate drafts first
    github_service.DEV_GITHUB_INSTALLATIONS_DB["proj-200"] = {
        "id": "inst-rec-2",
        "project_id": "proj-200",
        "installation_id": "inst-99999",
        "repo_full_name": "buildcrew/test-repo",
        "connected_at": "2026-08-15T00:00:00Z",
    }

    client.post("/projects/proj-200/generate-draft")

    # List contributions
    response = client.get("/projects/proj-200/contributions")
    assert response.status_code == 200
    res_data = response.json()

    assert res_data["project_id"] == "proj-200"
    assert res_data["total_count"] > 0
    assert res_data["draft_count"] > 0
    assert len(res_data["contributions"]) == res_data["total_count"]


def test_generate_draft_supabase_mode():
    mock_user = MagicMock(id="user-123", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()

    # Mock projects table query
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_select.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-supabase-1", "name": "Cloud Project", "created_by": "user-123"}
    )
    mock_proj_table.select.return_value = mock_proj_select

    # Mock project_members table query
    mock_members_table = MagicMock()
    mock_members_select = MagicMock()
    mock_members_select.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "user-123", "role": "owner"}]
    )
    mock_members_select.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "user_id": "user-123",
                "profiles": {
                    "email": "lead@buildcrew.io",
                    "display_name": "BuildCrew Lead",
                    "github_username": "buildcrew-dev",
                }
            }
        ]
    )
    mock_members_table.select.return_value = mock_members_select

    # Mock contributions table query
    mock_contrib_table = MagicMock()
    mock_contrib_select = MagicMock()
    mock_contrib_select.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_contrib_table.select.return_value = mock_contrib_select
    mock_contrib_table.insert.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "contrib-uuid-1",
                "contributor": "user-123",
                "project": "proj-supabase-1",
                "title": "feat: Supabase integration test",
                "category": "code",
                "description": "Git commit by buildcrew-dev",
                "date_range": "2026-08-16T12:00:00Z",
                "source_type": "github_commit",
                "evidence_link": "https://github.com/buildcrew/test/commit/abc",
                "verification_status": "source-verified",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": "2026-08-16T12:00:00Z",
                "updated_at": "2026-08-16T12:00:00Z",
            }
        ]
    )

    # Mock github_installations query
    mock_inst_table = MagicMock()
    mock_inst_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "inst-1",
                "project_id": "proj-supabase-1",
                "installation_id": "4635635",
                "repo_full_name": "buildcrew/buildcrew-app",
                "connected_at": "2026-08-15T00:00:00Z",
            }
        ]
    )
    mock_inst_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_members_table
        elif table_name == "contributions":
            return mock_contrib_table
        elif table_name == "github_installations":
            return mock_inst_table
        elif table_name == "profiles":
            mock_p = MagicMock()
            mock_p.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "user-123", "email": "lead@buildcrew.io", "display_name": "Lead"}]
            )
            return mock_p
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase), \
         patch("services.github_service.get_supabase_client", return_value=mock_supabase):
        response = client.post("/projects/proj-supabase-1/generate-draft")
        assert response.status_code == 200
        assert response.json()["generated_count"] >= 1


def test_list_contributions_unauthenticated():
    response = client.get("/projects/proj-100/contributions")
    assert response.status_code in (401, 403)


def test_list_contributions_project_not_found():
    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.get("/projects/non-existent-proj/contributions")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_list_contributions_forbidden_non_member():
    mock_user = MagicMock(id="stranger-123", email="stranger@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-secret"] = {
        "id": "proj-secret",
        "name": "Classified Project",
        "created_by": "creator-456",
    }

    response = client.get("/projects/proj-secret/contributions")
    assert response.status_code == 403
    assert "member" in response.json()["detail"].lower()


def test_list_contributions_with_filters():
    mock_user = MagicMock(id="user-123", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-filter"] = {
        "id": "proj-filter",
        "name": "Filter Test Project",
        "created_by": "user-123",
    }

    DEV_CONTRIBUTIONS_DB.extend([
        {
            "id": "c-1",
            "project": "proj-filter",
            "contributor": "user-123",
            "title": "feat: initial commit",
            "category": "code",
            "verification_status": "source-verified",
            "created_at": "2026-08-18T10:00:00Z",
            "updated_at": "2026-08-18T10:00:00Z",
        },
        {
            "id": "c-2",
            "project": "proj-filter",
            "contributor": "user-456",
            "title": "fix: bug in auth",
            "category": "pull_request",
            "verification_status": "confirmed",
            "created_at": "2026-08-18T11:00:00Z",
            "updated_at": "2026-08-18T11:00:00Z",
        },
        {
            "id": "c-3",
            "project": "proj-filter",
            "contributor": "user-123",
            "title": "docs: update API spec",
            "category": "documentation",
            "verification_status": "source-verified",
            "created_at": "2026-08-18T12:00:00Z",
            "updated_at": "2026-08-18T12:00:00Z",
        },
    ])

    # 1. Test all contributions
    res = client.get("/projects/proj-filter/contributions")
    assert res.status_code == 200
    data = res.json()
    assert data["total_count"] == 3
    assert data["draft_count"] == 2
    assert data["confirmed_count"] == 1

    # 2. Filter by status: source-verified
    res_status = client.get("/projects/proj-filter/contributions?status=source-verified")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["total_count"] == 2
    assert all(c["verification_status"] == "source-verified" for c in data_status["contributions"])

    # 3. Filter by contributor: user-456
    res_contrib = client.get("/projects/proj-filter/contributions?contributor=user-456")
    assert res_contrib.status_code == 200
    data_contrib = res_contrib.json()
    assert data_contrib["total_count"] == 1
    assert data_contrib["contributions"][0]["contributor"] == "user-456"

    # 4. Filter by category: pull_request
    res_cat = client.get("/projects/proj-filter/contributions?category=pull_request")
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert data_cat["total_count"] == 1
    assert data_cat["contributions"][0]["category"] == "pull_request"


def test_list_contributions_supabase_mode():
    mock_user = MagicMock(id="user-123", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()

    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-supabase-2", "name": "Supabase List Proj", "created_by": "user-123"}
    )

    mock_contrib_table = MagicMock()
    mock_select_chain = MagicMock()
    mock_select_chain.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "c-sb-1",
                "project": "proj-supabase-2",
                "contributor": "user-123",
                "title": "feat: Supabase list test",
                "category": "code",
                "verification_status": "source-verified",
                "created_at": "2026-08-18T10:00:00Z",
                "updated_at": "2026-08-18T10:00:00Z",
                "profiles": {
                    "display_name": "Supabase User",
                    "email": "user@supabase.io",
                }
            }
        ]
    )
    mock_select_chain.eq.return_value.execute.return_value = MagicMock(
        data=[{"verification_status": "source-verified"}]
    )
    mock_contrib_table.select.return_value = mock_select_chain

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "contributions":
            return mock_contrib_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get("/projects/proj-supabase-2/contributions")
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj-supabase-2"
        assert data["total_count"] == 1
        assert data["contributions"][0]["contributor_name"] == "Supabase User"

