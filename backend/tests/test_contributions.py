import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_CONFIRMATION_REQUESTS_DB,
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
    DEV_CONFIRMATION_REQUESTS_DB.clear()
    github_service.DEV_GITHUB_INSTALLATIONS_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()
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


# ==============================================================================
# 5. Step 1: Manual Non-Code Contribution Creation Tests (POST /contributions)
# ==============================================================================

def test_create_manual_contribution_success_dev_mode():
    mock_user = MagicMock(id="dev-designer-1", email="designer@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-manual-1"] = {
        "id": "proj-manual-1",
        "name": "Design System Revamp",
        "created_by": "dev-designer-1",
    }

    payload = {
        "project_id": "proj-manual-1",
        "title": "Created high-fidelity Figma mobile mockups",
        "category": "design",
        "description": "Designed 12 core screens with dark mode aesthetics and tokens.",
        "evidence_link": "https://figma.com/file/mockup123",
        "date_range": "2026-08-21",
    }

    response = client.post("/contributions", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "Created high-fidelity Figma mobile mockups"
    assert data["category"] == "design"
    assert data["description"] == "Designed 12 core screens with dark mode aesthetics and tokens."
    assert data["evidence_link"] == "https://figma.com/file/mockup123"
    assert data["verification_status"] == "self-declared"
    assert data["source_type"] == "manual"
    assert data["contributor"] == "dev-designer-1"
    assert data["project"] == "proj-manual-1"
    assert data["dispute_state"] == "none"
    assert data["contributor_name"] == "designer@buildcrew.io"
    assert "id" in data

    # Verify it is in DEV_CONTRIBUTIONS_DB
    assert any(c["id"] == data["id"] for c in DEV_CONTRIBUTIONS_DB)


def test_create_manual_contribution_project_alias_endpoint():
    mock_user = MagicMock(id="dev-researcher-1", email="researcher@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-alias-1"] = {
        "id": "proj-alias-1",
        "name": "Market Research Project",
        "created_by": "dev-researcher-1",
    }

    payload = {
        "title": "User Interview Analysis Report",
        "category": "research",
        "description": "Interviewed 10 beta testers and compiled pain points summary.",
        "evidence_link": "https://docs.google.com/document/d/report123",
    }

    response = client.post("/projects/proj-alias-1/contributions", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "User Interview Analysis Report"
    assert data["category"] == "research"
    assert data["verification_status"] == "self-declared"
    assert data["project"] == "proj-alias-1"


def test_create_manual_contribution_empty_title_validation():
    mock_user = MagicMock(id="dev-user-1", email="dev@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-val-1"] = {
        "id": "proj-val-1",
        "name": "Validation Test Project",
        "created_by": "dev-user-1",
    }

    payload = {
        "project_id": "proj-val-1",
        "title": "   ",
        "category": "documentation",
    }

    response = client.post("/contributions", json=payload)
    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"]


def test_create_manual_contribution_missing_project_validation():
    mock_user = MagicMock(id="dev-user-1", email="dev@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    payload = {
        "title": "Wrote documentation",
        "category": "documentation",
    }

    response = client.post("/contributions", json=payload)
    assert response.status_code == 400
    assert "Project ID is required" in response.json()["detail"]


def test_create_manual_contribution_non_member_forbidden():
    mock_user = MagicMock(id="outsider-user-99", email="outsider@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-secret-1"] = {
        "id": "proj-secret-1",
        "name": "Secret Project",
        "created_by": "project-owner-1",
    }

    payload = {
        "project_id": "proj-secret-1",
        "title": "Attempted unauthorized contribution",
        "category": "testing",
    }

    response = client.post("/contributions", json=payload)
    assert response.status_code == 403
    assert "must be a member" in response.json()["detail"]


def test_create_manual_contribution_project_not_found():
    mock_user = MagicMock(id="dev-user-1", email="dev@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-existing"] = {
        "id": "proj-existing",
        "name": "Existing Proj",
        "created_by": "dev-user-1",
    }

    payload = {
        "project_id": "non-existent-proj-999",
        "title": "Valid contribution on missing project",
        "category": "devops",
    }

    response = client.post("/contributions", json=payload)
    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]


def test_create_manual_contribution_supabase_mode():
    mock_user = MagicMock(id="user-sb-10", email="writer@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()

    mock_proj_table = MagicMock()
    mock_proj_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "proj-sb-10", "name": "Supabase Docs", "created_by": "user-sb-10"}
    )

    mock_profile_table = MagicMock()
    mock_profile_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"id": "user-sb-10", "display_name": "Writer Pro", "email": "writer@buildcrew.io"}
    )

    mock_contrib_table = MagicMock()
    mock_contrib_table.insert.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "c-sb-manual-1",
                "contributor": "user-sb-10",
                "project": "proj-sb-10",
                "title": "Wrote API Documentation",
                "category": "documentation",
                "description": "Comprehensive markdown guides for auth & contributions API",
                "date_range": "2026-08-21",
                "source_type": "manual",
                "evidence_link": "https://buildcrew.io/docs/api",
                "verification_status": "self-declared",
                "confirmed_by": None,
                "visibility": "public",
                "dispute_state": "none",
                "created_at": "2026-08-21T12:00:00Z",
                "updated_at": "2026-08-21T12:00:00Z",
            }
        ]
    )

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "profiles":
            return mock_profile_table
        elif table_name == "contributions":
            return mock_contrib_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    with patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
        payload = {
            "project_id": "proj-sb-10",
            "title": "Wrote API Documentation",
            "category": "documentation",
            "description": "Comprehensive markdown guides for auth & contributions API",
            "evidence_link": "https://buildcrew.io/docs/api",
        }
        response = client.post("/contributions", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "c-sb-manual-1"
        assert data["title"] == "Wrote API Documentation"
        assert data["verification_status"] == "self-declared"
        assert data["contributor_name"] == "Writer Pro"


def test_manual_and_github_contributions_coexist_in_stream():
    """Verify manual non-code contributions and GitHub auto-imported commits stream seamlessly side-by-side."""
    mock_user = MagicMock(id="dev-fullstack-1", email="fullstack@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-stream-1"] = {
        "id": "proj-stream-1",
        "name": "OmniStream Project",
        "created_by": "dev-fullstack-1",
    }

    # 1. Log manual contribution
    manual_payload = {
        "project_id": "proj-stream-1",
        "title": "Created Architecture Deck",
        "category": "presentation",
        "description": "Pitch deck for stakeholders",
        "evidence_link": "https://slides.com/deck123",
    }
    m_res = client.post("/contributions", json=manual_payload)
    assert m_res.status_code == 201

    # 2. Add an auto-imported code commit
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-gh-stream-1",
        "project": "proj-stream-1",
        "contributor": "dev-fullstack-1",
        "title": "feat: Implemented WebSocket synchronization",
        "category": "code",
        "source_type": "github_commit",
        "verification_status": "source-verified",
        "evidence_link": "https://github.com/org/repo/commit/abc1234",
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-08-21T10:00:00Z",
        "updated_at": "2026-08-21T10:00:00Z",
    })

    # 3. Query GET /projects/{project_id}/contributions
    stream_res = client.get("/projects/proj-stream-1/contributions")
    assert stream_res.status_code == 200
    stream_data = stream_res.json()
    assert stream_data["total_count"] == 2

    categories = [c["category"] for c in stream_data["contributions"]]
    assert "presentation" in categories
    assert "code" in categories

    statuses = [c["verification_status"] for c in stream_data["contributions"]]
    assert "self-declared" in statuses
    assert "source-verified" in statuses


# ==============================================================================
# 6. Step 2: Evidence Upload Tests (POST /contributions/upload-evidence)
# ==============================================================================

def test_upload_evidence_image_dev_fallback():
    mock_user = MagicMock(id="dev-uploader-1", email="uploader@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    dummy_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    files = {"file": ("mockup_screen.png", dummy_png_bytes, "image/png")}

    response = client.post("/contributions/upload-evidence", files=files)
    assert response.status_code == 201
    data = response.json()

    assert "mockup_screen.png" in data["filename"]
    assert data["file_type"] == "image/png"
    assert data["size_bytes"] == len(dummy_png_bytes)
    assert "/static/evidence/dev-uploader-1/" in data["url"] or "evidence" in data["url"]
    assert "storage_path" in data


def test_upload_evidence_pdf_document_dev_fallback():
    mock_user = MagicMock(id="dev-uploader-2", email="docs@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    dummy_pdf_bytes = b"%PDF-1.4\n%...\n%%EOF"
    files = {"file": ("architecture_spec.pdf", dummy_pdf_bytes, "application/pdf")}

    response = client.post("/contributions/upload-evidence", files=files)
    assert response.status_code == 201
    data = response.json()

    assert "architecture_spec.pdf" in data["filename"]
    assert data["file_type"] == "application/pdf"
    assert data["size_bytes"] == len(dummy_pdf_bytes)


def test_upload_evidence_supabase_mode():
    mock_user = MagicMock(id="user-sb-storage-1", email="sb_uploader@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_supabase = MagicMock()
    mock_storage = MagicMock()
    mock_bucket = MagicMock()

    mock_bucket.upload.return_value = {"Key": "evidence/user-sb-storage-1/test.png"}
    mock_bucket.get_public_url.return_value = "https://xyz.supabase.co/storage/v1/object/public/evidence/user-sb-storage-1/test.png"
    mock_storage.from_.return_value = mock_bucket
    mock_supabase.storage = mock_storage

    with patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
        dummy_png = b"\x89PNG\r\n\x1a\n"
        files = {"file": ("test.png", dummy_png, "image/png")}

        response = client.post("/contributions/upload-evidence", files=files)
        assert response.status_code == 201
        data = response.json()

        assert "https://xyz.supabase.co/storage/v1/object/public/evidence/" in data["url"]
        assert data["filename"] == "test.png"
        assert data["size_bytes"] == len(dummy_png)
        mock_bucket.upload.assert_called_once()
        mock_bucket.get_public_url.assert_called_once()


def test_upload_evidence_empty_file_fails():
    mock_user = MagicMock(id="dev-uploader-1", email="uploader@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    files = {"file": ("empty.png", b"", "image/png")}
    response = client.post("/contributions/upload-evidence", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_evidence_oversized_file_fails():
    mock_user = MagicMock(id="dev-uploader-1", email="uploader@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Mock huge file exceeding 25MB
    large_bytes = b"0" * (26 * 1024 * 1024)
    files = {"file": ("huge_file.zip", large_bytes, "application/zip")}
    response = client.post("/contributions/upload-evidence", files=files)
    assert response.status_code == 400
    assert "25MB" in response.json()["detail"] or "exceeds" in response.json()["detail"].lower()


def test_upload_evidence_and_create_contribution_e2e():
    """End-to-end flow: Upload screenshot -> use URL in POST /contributions -> verify in project stream."""
    mock_user = MagicMock(id="dev-designer-e2e", email="designer@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-upload-e2e"] = {
        "id": "proj-upload-e2e",
        "name": "Design System 2.0",
        "created_by": "dev-designer-e2e",
    }

    # 1. Upload evidence file
    screen_png = b"\x89PNG\r\n\x1a\nDesignTokensScreenshot"
    files = {"file": ("design_tokens.png", screen_png, "image/png")}
    upload_res = client.post("/contributions/upload-evidence", files=files)
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    evidence_url = upload_data["url"]
    assert evidence_url

    # 2. Create contribution referencing the uploaded URL
    contrib_payload = {
        "project_id": "proj-upload-e2e",
        "title": "Designed Design Tokens System",
        "category": "design",
        "description": "Defined typography, spacing, and dark theme color palette tokens.",
        "evidence_link": evidence_url,
    }
    contrib_res = client.post("/contributions", json=contrib_payload)
    assert contrib_res.status_code == 201
    contrib_data = contrib_res.json()
    assert contrib_data["evidence_link"] == evidence_url
    assert contrib_data["verification_status"] == "self-declared"

    # 3. Verify in project stream
    list_res = client.get("/projects/proj-upload-e2e/contributions")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total_count"] == 1
    assert list_data["contributions"][0]["evidence_link"] == evidence_url


def test_delete_contribution_unauthenticated():
    app.dependency_overrides.clear()
    response = client.delete("/contributions/c-to-delete-123")
    assert response.status_code in (401, 403)


def test_delete_contribution_not_found():
    mock_user = MagicMock(id="user-del-1", email="del@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.delete("/contributions/non-existent-contrib-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_contribution_forbidden_for_other_user():
    mock_user = MagicMock(id="user-stranger", email="stranger@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-del-auth"] = {
        "id": "proj-del-auth",
        "name": "Secret Project",
        "created_by": "user-lead-owner",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-author-protected",
        "project": "proj-del-auth",
        "contributor": "user-original-author",
        "title": "Confidential UI Spec",
        "category": "design",
        "verification_status": "self-declared",
    })

    response = client.delete("/contributions/c-author-protected")
    assert response.status_code == 403
    assert "authorized" in response.json()["detail"].lower()


def test_delete_contribution_success_by_author():
    mock_user = MagicMock(id="user-author-1", email="author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-del-author"] = {
        "id": "proj-del-author",
        "name": "Author Project",
        "created_by": "user-team-lead",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-author-self",
        "project": "proj-del-author",
        "contributor": "user-author-1",
        "title": "My Mistaken Contribution",
        "category": "design",
        "verification_status": "self-declared",
    })

    response = client.delete("/contributions/c-author-self")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["id"] == "c-author-self"
    assert not any(c["id"] == "c-author-self" for c in DEV_CONTRIBUTIONS_DB)


def test_delete_contribution_success_by_team_lead():
    mock_user = MagicMock(id="user-team-lead-boss", email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-del-lead"] = {
        "id": "proj-del-lead",
        "name": "Lead Governed Project",
        "created_by": "user-team-lead-boss",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-member-entry",
        "project": "proj-del-lead",
        "contributor": "user-teammate-2",
        "title": "Teammate Log Entry",
        "category": "documentation",
        "verification_status": "self-declared",
    })

    # Test deletion via project alias endpoint as well
    response = client.delete("/projects/proj-del-lead/contributions/c-member-entry")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert not any(c["id"] == "c-member-entry" for c in DEV_CONTRIBUTIONS_DB)


def test_list_project_contributions_includes_self_declared_in_draft_count():
    """Verify that manually logged 'self-declared' contributions are counted in draft_count."""
    mock_user = MagicMock(id="user-member-charlie", email="charlie@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    DEV_PROJECTS_DB["proj-draft-count-test"] = {
        "id": "proj-draft-count-test",
        "name": "Draft Counting Test Project",
        "created_by": "user-member-charlie",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-draft-count-test",
        "user_id": "user-member-charlie",
    })

    # Add a manually logged self-declared contribution
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-manual-deck",
        "project": "proj-draft-count-test",
        "contributor": "user-member-charlie",
        "title": "Investor Pitch Deck",
        "category": "presentation",
        "verification_status": "self-declared",
        "visibility": "public",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    })

    response = client.get("/projects/proj-draft-count-test/contributions")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    # Must be counted in draft_count!
    assert data["draft_count"] == 1
    assert data["confirmed_count"] == 0


def test_stable_dev_user_id_deterministic():
    """Verify that stable_dev_user_id produces identical deterministic IDs across runs and case variations."""
    from core.dependencies import stable_dev_user_id

    id1 = stable_dev_user_id("alice@buildcrew.io")
    id2 = stable_dev_user_id("Alice@BuildCrew.IO ")
    id3 = stable_dev_user_id("bob@buildcrew.io")

    assert id1 == id2
    assert id1.startswith("dev-user-")
    assert id1 != id3


# ==============================================================================
# 9. Request Confirmation Endpoint Tests
# ==============================================================================

def test_request_confirmation_success_by_author():
    """Author can successfully request peer confirmation from project teammates."""
    author_user = MagicMock(id="user-author-1", email="author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    DEV_PROJECTS_DB["proj-peer-1"] = {
        "id": "proj-peer-1",
        "name": "Peer Review Project",
        "created_by": "user-author-1",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-peer-1",
        "user_id": "user-teammate-bob",
    })
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-design-spec",
        "project": "proj-peer-1",
        "contributor": "user-author-1",
        "title": "Figma Design System Architecture",
        "category": "design",
        "verification_status": "self-declared",
        "evidence_link": "https://figma.com/design-spec",
    })

    payload = {"reviewer_ids": ["user-teammate-bob"]}
    response = client.post("/contributions/c-design-spec/request-confirmation", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["contribution_id"] == "c-design-spec"
    assert data[0]["reviewer_id"] == "user-teammate-bob"
    assert data[0]["requested_by"] == "user-author-1"
    assert data[0]["status"] == "pending"
    assert data[0]["contribution_title"] == "Figma Design System Architecture"
    assert data[0]["project_name"] == "Peer Review Project"

    # Verify persisted in DEV_CONFIRMATION_REQUESTS_DB
    assert any(
        r["contribution_id"] == "c-design-spec" and r["reviewer_id"] == "user-teammate-bob"
        for r in DEV_CONFIRMATION_REQUESTS_DB
    )
    # Verify contribution status transitioned to confirmation-pending
    target_contrib = next(c for c in DEV_CONTRIBUTIONS_DB if c["id"] == "c-design-spec")
    assert target_contrib["verification_status"] == "confirmation-pending"


def test_request_confirmation_fails_if_not_author():
    """Non-author teammate cannot request peer confirmation for someone else's contribution."""
    imposter_user = MagicMock(id="user-imposter-99", email="imposter@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: imposter_user

    DEV_PROJECTS_DB["proj-peer-2"] = {
        "id": "proj-peer-2",
        "name": "Peer Review Project 2",
        "created_by": "user-real-author",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-peer-2",
        "user_id": "user-imposter-99",
    })
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-peer-2",
        "user_id": "user-reviewer-1",
    })
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-author-deliverable",
        "project": "proj-peer-2",
        "contributor": "user-real-author",
        "title": "Backend Migration Script",
        "verification_status": "self-declared",
    })

    payload = {"reviewer_ids": ["user-reviewer-1"]}
    response = client.post("/contributions/c-author-deliverable/request-confirmation", json=payload)
    assert response.status_code == 403
    assert "Only the author of a contribution can request peer confirmation" in response.json()["detail"]


def test_request_confirmation_fails_if_reviewer_not_project_member():
    """Author cannot request confirmation from an external user who is not in the project."""
    author_user = MagicMock(id="user-author-2", email="author2@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    DEV_PROJECTS_DB["proj-peer-3"] = {
        "id": "proj-peer-3",
        "name": "Isolated Project",
        "created_by": "user-author-2",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-author-item",
        "project": "proj-peer-3",
        "contributor": "user-author-2",
        "title": "Security Audit Report",
        "verification_status": "self-declared",
    })

    payload = {"reviewer_ids": ["user-external-stranger"]}
    response = client.post("/contributions/c-author-item/request-confirmation", json=payload)
    assert response.status_code == 403
    assert "not a verified member" in response.json()["detail"]




def test_request_confirmation_fails_on_self_request():
    """Author cannot request peer confirmation from themselves."""
    author_user = MagicMock(id="user-author-3", email="author3@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    DEV_PROJECTS_DB["proj-peer-4"] = {
        "id": "proj-peer-4",
        "name": "Self Test Project",
        "created_by": "user-author-3",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-self-item",
        "project": "proj-peer-4",
        "contributor": "user-author-3",
        "title": "Self Check Task",
        "verification_status": "self-declared",
    })

    payload = {"reviewer_ids": ["user-author-3"]}
    response = client.post("/contributions/c-self-item/request-confirmation", json=payload)
    assert response.status_code == 400
    assert "You cannot request confirmation from yourself" in response.json()["detail"]


def test_request_confirmation_empty_reviewers():
    """Reject empty reviewer list with 400."""
    author_user = MagicMock(id="user-author-4", email="author4@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    payload = {"reviewer_ids": []}
    response = client.post("/contributions/any-id/request-confirmation", json=payload)
    assert response.status_code == 400
    assert "At least one teammate reviewer must be selected" in response.json()["detail"]


# ==============================================================================
# 10. Confirm Contribution Endpoint Tests
# ==============================================================================

def test_confirm_contribution_success_by_teammate():
    """Teammate can confirm another member's contribution, updating status to peer-confirmed."""
    reviewer_user = MagicMock(id="user-teammate-reviewer", email="reviewer@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: reviewer_user

    DEV_PROJECTS_DB["proj-confirm-1"] = {
        "id": "proj-confirm-1",
        "name": "Confirmation Workflow Project",
        "created_by": "user-author-dan",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-confirm-1",
        "user_id": "user-teammate-reviewer",
    })
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-confirm-target",
        "project": "proj-confirm-1",
        "contributor": "user-author-dan",
        "title": "API Gateway Setup",
        "category": "devops",
        "verification_status": "self-declared",
        "confirmed_by": None,
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    })
    DEV_CONFIRMATION_REQUESTS_DB.append({
        "id": "req-1",
        "contribution_id": "c-confirm-target",
        "project_id": "proj-confirm-1",
        "requested_by": "user-author-dan",
        "reviewer_id": "user-teammate-reviewer",
        "status": "pending",
    })

    response = client.post("/contributions/c-confirm-target/confirm")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "c-confirm-target"
    assert data["verification_status"] == "peer-confirmed"
    assert data["confirmed_by"] == "user-teammate-reviewer"

    # Verify requests DB updated
    matching_req = [r for r in DEV_CONFIRMATION_REQUESTS_DB if r["id"] == "req-1"][0]
    assert matching_req["status"] == "confirmed"


def test_confirm_contribution_fails_on_author_self_confirmation():
    """Author cannot confirm their own contribution."""
    author_user = MagicMock(id="user-author-dan", email="author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    DEV_PROJECTS_DB["proj-confirm-2"] = {
        "id": "proj-confirm-2",
        "name": "Self Confirm Project",
        "created_by": "user-author-dan",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-self-confirm",
        "project": "proj-confirm-2",
        "contributor": "user-author-dan",
        "title": "Solo Research",
        "verification_status": "self-declared",
    })

    response = client.post("/contributions/c-self-confirm/confirm")
    assert response.status_code == 403
    assert "Authors cannot confirm their own contributions" in response.json()["detail"]


def test_confirm_contribution_fails_if_not_project_member():
    """Non-member cannot confirm a contribution in a project they don't belong to."""
    stranger_user = MagicMock(id="user-stranger-x", email="stranger@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: stranger_user

    DEV_PROJECTS_DB["proj-confirm-3"] = {
        "id": "proj-confirm-3",
        "name": "Secret Project",
        "created_by": "user-real-leader",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-secret-item",
        "project": "proj-confirm-3",
        "contributor": "user-real-leader",
        "title": "Secret Feature",
        "verification_status": "self-declared",
    })

    response = client.post("/contributions/c-secret-item/confirm")
    assert response.status_code == 403
    assert "You must be a member of this project to confirm contributions" in response.json()["detail"]


def test_confirm_contribution_not_found():
    """Return 404 when contribution ID does not exist."""
    user = MagicMock(id="user-random", email="random@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: user

    response = client.post("/contributions/c-does-not-exist/confirm")
    assert response.status_code == 404
    assert "Contribution not found" in response.json()["detail"]


# ==============================================================================
# 11. Dispute Contribution Endpoint Tests
# ==============================================================================

def test_dispute_contribution_success_by_teammate():
    """Teammate can dispute a contribution, setting needs-review, dispute_state: disputed, and visibility: private."""
    reviewer_user = MagicMock(id="user-teammate-qa", email="qa@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: reviewer_user

    DEV_PROJECTS_DB["proj-dispute-1"] = {
        "id": "proj-dispute-1",
        "name": "Dispute Workflow Project",
        "created_by": "user-author-sam",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-dispute-1",
        "user_id": "user-teammate-qa",
    })
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-dispute-target",
        "project": "proj-dispute-1",
        "contributor": "user-author-sam",
        "title": "Unfinished Auth Flow",
        "category": "code",
        "verification_status": "self-declared",
        "dispute_state": "none",
        "visibility": "public",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    })
    DEV_CONFIRMATION_REQUESTS_DB.append({
        "id": "req-dispute-1",
        "contribution_id": "c-dispute-target",
        "project_id": "proj-dispute-1",
        "requested_by": "user-author-sam",
        "reviewer_id": "user-teammate-qa",
        "status": "pending",
    })

    response = client.post("/contributions/c-dispute-target/dispute")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "c-dispute-target"
    assert data["verification_status"] == "needs-review"
    assert data["dispute_state"] == "disputed"
    assert data["visibility"] == "private"

    # Verify requests DB updated
    matching_req = [r for r in DEV_CONFIRMATION_REQUESTS_DB if r["id"] == "req-dispute-1"][0]
    assert matching_req["status"] == "disputed"


def test_dispute_contribution_fails_on_author_self_dispute():
    """Author cannot dispute their own contribution."""
    author_user = MagicMock(id="user-author-sam", email="sam@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author_user

    DEV_PROJECTS_DB["proj-dispute-2"] = {
        "id": "proj-dispute-2",
        "name": "Self Dispute Project",
        "created_by": "user-author-sam",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-self-dispute",
        "project": "proj-dispute-2",
        "contributor": "user-author-sam",
        "title": "Solo Work",
        "verification_status": "self-declared",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    })

    response = client.post("/contributions/c-self-dispute/dispute")
    assert response.status_code == 403
    assert "Authors cannot dispute their own contributions" in response.json()["detail"]


def test_dispute_contribution_fails_if_not_project_member():
    """Non-member cannot dispute a contribution in a project they don't belong to."""
    stranger_user = MagicMock(id="user-stranger-qa", email="stranger-qa@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: stranger_user

    DEV_PROJECTS_DB["proj-dispute-3"] = {
        "id": "proj-dispute-3",
        "name": "Private Project",
        "created_by": "user-real-leader-2",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-private-item",
        "project": "proj-dispute-3",
        "contributor": "user-real-leader-2",
        "title": "Internal Spec",
        "verification_status": "self-declared",
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z",
    })

    response = client.post("/contributions/c-private-item/dispute")
    assert response.status_code == 403
    assert "You must be a member of this project to dispute contributions" in response.json()["detail"]


def test_dispute_contribution_not_found():
    """Return 404 when contribution ID does not exist."""
    user = MagicMock(id="user-random-qa", email="random-qa@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: user

    response = client.post("/contributions/c-does-not-exist-qa/dispute")
    assert response.status_code == 404
    assert "Contribution not found" in response.json()["detail"]


# ==============================================================================
# 12. Pending Confirmations Endpoint Tests
# ==============================================================================

def test_get_pending_confirmations_empty_when_no_requests():
    """Returns total_count: 0 and empty list when current user has no pending reviews."""
    reviewer_user = MagicMock(id="user-empty-inbox", email="empty@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: reviewer_user

    response = client.get("/contributions/pending-confirmations")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["requests"] == []


def test_get_pending_confirmations_returns_assigned_pending_requests():
    """Returns requests assigned to current user with enriched metadata."""
    reviewer_user = MagicMock(id="user-reviewer-jen", email="jen@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: reviewer_user

    DEV_PROJECTS_DB["proj-pending-1"] = {
        "id": "proj-pending-1",
        "name": "Design System 2.0",
        "created_by": "user-author-leo",
    }
    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-pending-item-1",
        "project": "proj-pending-1",
        "contributor": "user-author-leo",
        "title": "Figma Color Palette",
        "category": "design",
        "description": "Added 30+ accessible colors",
        "evidence_link": "https://figma.com/file/colors",
        "verification_status": "self-declared",
        "created_at": "2026-08-25T10:00:00Z",
        "updated_at": "2026-08-25T10:00:00Z",
    })
    DEV_CONFIRMATION_REQUESTS_DB.append({
        "id": "req-pending-1",
        "contribution_id": "c-pending-item-1",
        "project_id": "proj-pending-1",
        "requested_by": "user-author-leo",
        "reviewer_id": "user-reviewer-jen",
        "status": "pending",
        "created_at": "2026-08-25T10:05:00Z",
        "updated_at": "2026-08-25T10:05:00Z",
    })

    response = client.get("/contributions/pending-confirmations")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    req = data["requests"][0]
    assert req["id"] == "req-pending-1"
    assert req["contribution_id"] == "c-pending-item-1"
    assert req["reviewer_id"] == "user-reviewer-jen"
    assert req["contribution_title"] == "Figma Color Palette"
    assert req["project_name"] == "Design System 2.0"
    assert req["category"] == "design"
    assert req["evidence_link"] == "https://figma.com/file/colors"


def test_get_pending_confirmations_excludes_confirmed_and_other_users():
    """Excludes non-pending requests and requests assigned to other reviewers."""
    target_user = MagicMock(id="user-lead-sarah", email="sarah@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: target_user

    # Request assigned to Sarah but already confirmed
    DEV_CONFIRMATION_REQUESTS_DB.append({
        "id": "req-already-done",
        "contribution_id": "c-done",
        "project_id": "proj-1",
        "requested_by": "user-a",
        "reviewer_id": "user-lead-sarah",
        "status": "confirmed",
    })
    # Request assigned to someone else
    DEV_CONFIRMATION_REQUESTS_DB.append({
        "id": "req-other-guy",
        "contribution_id": "c-other",
        "project_id": "proj-1",
        "requested_by": "user-a",
        "reviewer_id": "user-other-guy",
        "status": "pending",
    })

    response = client.get("/contributions/pending-confirmations")
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert data["requests"] == []


# ==============================================================================
# 13. End-to-End Confirmation & Dispute Collaboration Flow
# ==============================================================================

def test_peer_confirmation_and_dispute_complete_flow():
    """
    E2E integration test:
    1. User A logs manual deliverable in project.
    2. User A requests confirmation from User B.
    3. User B fetches pending confirmations and sees request.
    4. User B confirms deliverable -> verified peer-confirmed.
    5. User A logs a second deliverable and requests confirmation from User B.
    6. User B disputes second deliverable -> verified needs-review and private.
    """
    user_a = MagicMock(id="user-author-alex", email="alex@buildcrew.io")
    user_b = MagicMock(id="user-reviewer-sara", email="sara@buildcrew.io")

    # Project setup
    DEV_PROJECTS_DB["proj-flow-1"] = {
        "id": "proj-flow-1",
        "name": "Full Flow App",
        "created_by": "user-author-alex",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-flow-1",
        "user_id": "user-reviewer-sara",
    })

    # Step 1: User A logs first deliverable
    app.dependency_overrides[get_current_user] = lambda: user_a
    contrib1_resp = client.post(
        "/projects/proj-flow-1/contributions",
        json={
            "title": "Clean Architecture Spec",
            "category": "documentation",
            "description": "System architecture diagram and RFC doc",
            "evidence_link": "https://buildcrew.io/rfc-spec",
        },
    )
    assert contrib1_resp.status_code == 201
    c1_id = contrib1_resp.json()["id"]

    # Step 2: User A requests confirmation from User B
    req_resp = client.post(
        f"/contributions/{c1_id}/request-confirmation",
        json={"reviewer_ids": ["user-reviewer-sara"]},
    )
    assert req_resp.status_code == 201
    assert len(req_resp.json()) == 1

    # Step 3: User B fetches pending confirmations
    app.dependency_overrides[get_current_user] = lambda: user_b
    pending_resp = client.get("/contributions/pending-confirmations")
    assert pending_resp.status_code == 200
    pending_data = pending_resp.json()
    assert pending_data["total_count"] == 1
    assert pending_data["requests"][0]["contribution_id"] == c1_id

    # Step 4: User B confirms deliverable
    confirm_resp = client.post(f"/contributions/{c1_id}/confirm")
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["verification_status"] == "peer-confirmed"
    assert confirm_resp.json()["confirmed_by"] == "user-reviewer-sara"

    # Verify inbox is now empty for User B
    empty_pending = client.get("/contributions/pending-confirmations")
    assert empty_pending.status_code == 200
    assert empty_pending.json()["total_count"] == 0

    # Step 5: User A logs second deliverable
    app.dependency_overrides[get_current_user] = lambda: user_a
    contrib2_resp = client.post(
        "/projects/proj-flow-1/contributions",
        json={
            "title": "Incomplete Auth Patch",
            "category": "code",
            "description": "Unfinished auth code without tests",
        },
    )
    assert contrib2_resp.status_code == 201
    c2_id = contrib2_resp.json()["id"]

    # User A requests confirmation
    client.post(
        f"/contributions/{c2_id}/request-confirmation",
        json={"reviewer_ids": ["user-reviewer-sara"]},
    )

    # Step 6: User B disputes second deliverable
    app.dependency_overrides[get_current_user] = lambda: user_b
    dispute_resp = client.post(f"/contributions/{c2_id}/dispute")
    assert dispute_resp.status_code == 200
    data2 = dispute_resp.json()
    assert data2["verification_status"] == "needs-review"
    assert data2["dispute_state"] == "disputed"
    assert data2["visibility"] == "private"

    # Verify author User A can still see their disputed item in their project review feed
    app.dependency_overrides[get_current_user] = lambda: user_a
    author_proj_resp = client.get("/projects/proj-flow-1/contributions")
    assert author_proj_resp.status_code == 200
    author_contrib_ids = [c["id"] for c in author_proj_resp.json()["contributions"]]
    assert c2_id in author_contrib_ids

    # Verify reviewer User B does NOT see the disputed item in the project contributions feed
    app.dependency_overrides[get_current_user] = lambda: user_b
    reviewer_proj_resp = client.get("/projects/proj-flow-1/contributions")
    assert reviewer_proj_resp.status_code == 200
    reviewer_contrib_ids = [c["id"] for c in reviewer_proj_resp.json()["contributions"]]
    assert c2_id not in reviewer_contrib_ids


def test_needs_review_excluded_from_public_and_passport_queries():
    """
    Phase 12 Legal-Safety Barrier Test:
    Guarantees that ANY contribution with status 'needs-review' or 'disputed'
    is strictly and unconditionally excluded from:
    1. /users/{user_id}/passport (public passport query)
    2. /contributions/passport/{user_id} (alias public passport query)
    3. /contributions/public (public stream query)
    4. /projects/{project_id}/contributions/public (public project stream)
    5. /projects/{project_id}/contributions (teammate non-author query)
    6. Tampered items where visibility='public' but verification_status='needs-review'
    7. Author personal query shows the disputed item exclusively to author for resolution.
    """
    author = MagicMock(id="user-builder-zoe", email="zoe@buildcrew.io")
    reviewer = MagicMock(id="user-reviewer-max", email="max@buildcrew.io")

    proj_id = "proj-legal-safety-1"
    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Decentralized Credential Protocol",
        "created_by": "user-builder-zoe",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": proj_id,
        "user_id": "user-reviewer-max",
    })

    # 1. Author logs first deliverable (valid work)
    app.dependency_overrides[get_current_user] = lambda: author
    resp1 = client.post(
        f"/projects/{proj_id}/contributions",
        json={
            "title": "Smart Contract Audited Token Vault",
            "category": "code",
            "description": "ERC-4626 vault with invariant fuzz testing",
            "visibility": "public",
        },
    )
    assert resp1.status_code == 201
    good_contrib_id = resp1.json()["id"]

    # 2. Author logs second deliverable (contested deliverable)
    resp2 = client.post(
        f"/projects/{proj_id}/contributions",
        json={
            "title": "Fictitious Marketing Campaign",
            "category": "other",
            "description": "Unverified external marketing claims",
            "visibility": "public",
        },
    )
    assert resp2.status_code == 201
    disputed_contrib_id = resp2.json()["id"]

    # 3. Request confirmation for both
    client.post(
        f"/contributions/{good_contrib_id}/request-confirmation",
        json={"reviewer_ids": ["user-reviewer-max"]},
    )
    client.post(
        f"/contributions/{disputed_contrib_id}/request-confirmation",
        json={"reviewer_ids": ["user-reviewer-max"]},
    )

    # 4. Reviewer confirms deliverable 1 -> peer-confirmed
    app.dependency_overrides[get_current_user] = lambda: reviewer
    confirm_res = client.post(f"/contributions/{good_contrib_id}/confirm")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["verification_status"] == "peer-confirmed"

    # 5. Reviewer disputes deliverable 2 -> needs-review & disputed
    dispute_res = client.post(f"/contributions/{disputed_contrib_id}/dispute")
    assert dispute_res.status_code == 200
    assert dispute_res.json()["verification_status"] == "needs-review"
    assert dispute_res.json()["dispute_state"] == "disputed"

    # Clear dependency overrides to simulate unauthenticated public visitor
    app.dependency_overrides.clear()

    # TEST A: Public builder passport endpoint GET /users/{user_id}/passport
    passport_resp = client.get(f"/users/{author.id}/passport")
    assert passport_resp.status_code == 200
    passport_data = passport_resp.json()
    passport_ids = [c["id"] for c in passport_data["contributions"]]
    assert good_contrib_id in passport_ids
    assert disputed_contrib_id not in passport_ids, "Disputed contribution must be excluded from /users/{id}/passport"
    assert passport_data["total_contributions"] == 1
    assert passport_data["confirmed_count"] == 1

    # TEST B: Alias public builder passport endpoint GET /contributions/passport/{user_id}
    passport_alias_resp = client.get(f"/contributions/passport/{author.id}")
    assert passport_alias_resp.status_code == 200
    alias_ids = [c["id"] for c in passport_alias_resp.json()["contributions"]]
    assert good_contrib_id in alias_ids
    assert disputed_contrib_id not in alias_ids, "Disputed contribution must be excluded from /contributions/passport/{id}"

    # TEST C: Public contributions stream GET /contributions/public
    public_stream_resp = client.get(f"/contributions/public?user_id={author.id}")
    assert public_stream_resp.status_code == 200
    public_ids = [c["id"] for c in public_stream_resp.json()["contributions"]]
    assert good_contrib_id in public_ids
    assert disputed_contrib_id not in public_ids, "Disputed contribution must be excluded from /contributions/public"

    # TEST D: Public project contributions stream GET /projects/{project_id}/contributions/public
    proj_public_resp = client.get(f"/projects/{proj_id}/contributions/public")
    assert proj_public_resp.status_code == 200
    proj_public_ids = [c["id"] for c in proj_public_resp.json()["contributions"]]
    assert good_contrib_id in proj_public_ids
    assert disputed_contrib_id not in proj_public_ids, "Disputed contribution must be excluded from /projects/{id}/contributions/public"

    # TEST E: Teammate Reviewer Max views project contributions feed -> disputed item is NOT visible
    app.dependency_overrides[get_current_user] = lambda: reviewer
    teammate_feed_resp = client.get(f"/projects/{proj_id}/contributions")
    assert teammate_feed_resp.status_code == 200
    teammate_ids = [c["id"] for c in teammate_feed_resp.json()["contributions"]]
    assert good_contrib_id in teammate_ids
    assert disputed_contrib_id not in teammate_ids, "Teammate must not see disputed needs-review contribution"

    # TEST F: Tamper Simulation — even if database row mistakenly has visibility='public',
    # status 'needs-review' MUST guarantee exclusion from all public and passport queries
    for c in DEV_CONTRIBUTIONS_DB:
        if c.get("id") == disputed_contrib_id:
            c["visibility"] = "public"  # Maliciously or accidentally set to public
            break

    app.dependency_overrides.clear()
    tamper_passport_resp = client.get(f"/users/{author.id}/passport")
    assert tamper_passport_resp.status_code == 200
    tamper_ids = [c["id"] for c in tamper_passport_resp.json()["contributions"]]
    assert disputed_contrib_id not in tamper_ids, "Tampered needs-review item with visibility='public' must STILL be excluded!"

    tamper_public_resp = client.get(f"/projects/{proj_id}/contributions/public")
    assert tamper_public_resp.status_code == 200
    tamper_proj_ids = [c["id"] for c in tamper_public_resp.json()["contributions"]]
    assert disputed_contrib_id not in tamper_proj_ids, "Tampered needs-review item must STILL be excluded from public project view!"

    # TEST G: Author Zoe views project contributions feed -> author CAN see their disputed item
    app.dependency_overrides[get_current_user] = lambda: author
    author_feed_resp = client.get(f"/projects/{proj_id}/contributions")
    assert author_feed_resp.status_code == 200
    author_ids = [c["id"] for c in author_feed_resp.json()["contributions"]]
    assert good_contrib_id in author_ids
    assert disputed_contrib_id in author_ids, "Author must be able to view their own disputed deliverable in their dashboard"


def test_disputed_contribution_needs_review_excluded_from_visibility_public_queries_regardless_of_flags():
    """
    Guarantees that:
    1. A contribution is created.
    2. A teammate disputes it, transitioning status to 'needs-review' (and dispute_state to 'disputed').
    3. The contribution is confirmed to be strictly excluded from a query filtered to visibility='public'.
    4. Assert it NEVER appears in that result set regardless of any other flag set on it
       (e.g., visibility='public', is_confirmed=True, featured=True, is_published=True,
       confidence_score=1.0, tier='tier_1', status='approved', etc.).
    """
    author = MagicMock(id="user-author-clara", email="clara@buildcrew.io")
    peer = MagicMock(id="user-peer-marcus", email="marcus@buildcrew.io")

    proj_id = "proj-dispute-exclusion-test"
    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Zero Knowledge Verification Engine",
        "created_by": author.id,
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": proj_id,
        "user_id": peer.id,
    })

    # 1. Create deliverable 1 (to be disputed)
    app.dependency_overrides[get_current_user] = lambda: author
    create_res1 = client.post(
        f"/projects/{proj_id}/contributions",
        json={
            "title": "ZK Rollup Circuit Proof Implementation",
            "category": "code",
            "description": "Plonk proof generation circuit implementation with constraint checks",
            "visibility": "public",
        },
    )
    assert create_res1.status_code == 201
    disputed_id = create_res1.json()["id"]

    # Also create deliverable 2 (valid baseline item that gets peer-confirmed)
    create_res2 = client.post(
        f"/projects/{proj_id}/contributions",
        json={
            "title": "Benchmarking Framework for Rollup Prover",
            "category": "code",
            "description": "End-to-end circuit latency benchmarks",
            "visibility": "public",
        },
    )
    assert create_res2.status_code == 201
    valid_id = create_res2.json()["id"]

    # 2. Peer disputes deliverable 1 -> verification_status becomes 'needs-review'
    app.dependency_overrides[get_current_user] = lambda: peer
    dispute_res = client.post(f"/contributions/{disputed_id}/dispute")
    assert dispute_res.status_code == 200
    dispute_data = dispute_res.json()
    assert dispute_data["verification_status"] == "needs-review"
    assert dispute_data["dispute_state"] == "disputed"

    # Peer confirms deliverable 2 -> peer-confirmed
    confirm_res = client.post(f"/contributions/{valid_id}/confirm")
    assert confirm_res.status_code == 200
    assert confirm_res.json()["verification_status"] == "peer-confirmed"

    # 3. Confirm exclusion from query filtered to visibility='public'
    pub_query_res = client.get(f"/projects/{proj_id}/contributions?visibility=public")
    assert pub_query_res.status_code == 200
    returned_ids = [c["id"] for c in pub_query_res.json()["contributions"]]
    assert disputed_id not in returned_ids, "Disputed needs-review item must be excluded from visibility='public' query!"
    assert valid_id in returned_ids, "Valid deliverable must be present in query results."

    # 4. Rigorous Flag Independence Assertion:
    # Assert it NEVER appears in visibility='public' results regardless of any other flag on it.
    conflicting_flag_permutations = [
        # Flag Permutation A: Database row visibility forced to 'public'
        {"visibility": "public"},
        # Flag Permutation B: visibility='public' with high confidence score and featured flag
        {"visibility": "public", "featured": True, "confidence_score": 1.0},
        # Flag Permutation C: visibility='public' with is_confirmed=True and status='approved'
        {"visibility": "public", "is_confirmed": True, "status": "approved"},
        # Flag Permutation D: visibility='public' with tier='featured', starred=True, and is_verified=True
        {"visibility": "public", "tier": "featured", "starred": True, "is_verified": True},
        # Flag Permutation E: visibility='public' with dispute_state cleared/None and is_published=True
        {"visibility": "public", "is_published": True, "dispute_state": None},
        # Flag Permutation F: Kitchen-sink of positive flags while status remains 'needs-review'
        {
            "visibility": "public",
            "is_published": True,
            "featured": True,
            "starred": True,
            "is_verified": True,
            "is_confirmed": True,
            "status": "approved",
            "tier": "tier_1",
            "confidence_score": 0.99,
        },
    ]

    for flags in conflicting_flag_permutations:
        # Mutate the in-memory database row with the conflicting flags while keeping status='needs-review'
        for c in DEV_CONTRIBUTIONS_DB:
            if c.get("id") == disputed_id:
                c.update(flags)
                c["verification_status"] = "needs-review"
                break

        # A. Query filtered to visibility='public' as Peer
        app.dependency_overrides[get_current_user] = lambda: peer
        peer_query = client.get(f"/projects/{proj_id}/contributions?visibility=public")
        assert peer_query.status_code == 200
        peer_ids = [c["id"] for c in peer_query.json()["contributions"]]
        assert disputed_id not in peer_ids, f"Leaked to peer in visibility=public under flags: {flags}"
        assert valid_id in peer_ids

        # B. Query filtered to visibility='public' as Author
        app.dependency_overrides[get_current_user] = lambda: author
        author_pub_query = client.get(f"/projects/{proj_id}/contributions?visibility=public")
        assert author_pub_query.status_code == 200
        author_pub_ids = [c["id"] for c in author_pub_query.json()["contributions"]]
        assert disputed_id not in author_pub_ids, f"Leaked to author in visibility=public under flags: {flags}"
        assert valid_id in author_pub_ids

        # C. Dedicated Public Project Stream endpoint GET /projects/{project_id}/contributions/public
        app.dependency_overrides.clear()
        pub_stream_res = client.get(f"/projects/{proj_id}/contributions/public")
        assert pub_stream_res.status_code == 200
        stream_ids = [c["id"] for c in pub_stream_res.json()["contributions"]]
        assert disputed_id not in stream_ids, f"Leaked in public project stream under flags: {flags}"
        assert valid_id in stream_ids

        # D. Global Public Contributions endpoint GET /contributions/public
        global_stream_res = client.get(f"/contributions/public?project_id={proj_id}")
        assert global_stream_res.status_code == 200
        global_ids = [c["id"] for c in global_stream_res.json()["contributions"]]
        assert disputed_id not in global_ids, f"Leaked in global public stream under flags: {flags}"
        assert valid_id in global_ids

        # E. Public Builder Passport endpoint GET /users/{user_id}/passport
        passport_res = client.get(f"/users/{author.id}/passport")
        assert passport_res.status_code == 200
        passport_ids = [c["id"] for c in passport_res.json()["contributions"]]
        assert disputed_id not in passport_ids, f"Leaked in user passport under flags: {flags}"
        assert valid_id in passport_ids

        # F. Alias Public Builder Passport endpoint GET /contributions/passport/{user_id}
        alias_passport_res = client.get(f"/contributions/passport/{author.id}")
        assert alias_passport_res.status_code == 200
        alias_ids = [c["id"] for c in alias_passport_res.json()["contributions"]]
        assert disputed_id not in alias_ids, f"Leaked in alias passport under flags: {flags}"
        assert valid_id in alias_ids


def test_publish_confirmed_contribution_success():
    """Publish endpoint toggles visibility to public for a confirmed deliverable."""
    author = MagicMock(id="user-publish-author", email="author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author

    contrib_id = "c-publish-confirmed-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": contrib_id,
        "project": "proj-publish-1",
        "contributor": author.id,
        "title": "Smart Contract Auditing",
        "category": "security",
        "verification_status": "confirmed",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z",
    })

    res = client.post(f"/contributions/{contrib_id}/publish")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == contrib_id
    assert data["visibility"] == "public"

    # Confirm updated in DB
    updated = next(c for c in DEV_CONTRIBUTIONS_DB if c["id"] == contrib_id)
    assert updated["visibility"] == "public"


def test_publish_peer_confirmed_contribution_success():
    """Publish endpoint toggles visibility to public for a peer-confirmed deliverable."""
    author = MagicMock(id="user-publish-peer-author", email="peer_author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author

    contrib_id = "c-publish-peer-confirmed-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": contrib_id,
        "project": "proj-publish-1",
        "contributor": author.id,
        "title": "Flutter Architecture Refactor",
        "category": "frontend",
        "verification_status": "peer-confirmed",
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z",
    })

    res = client.post(f"/contributions/{contrib_id}/publish")
    assert res.status_code == 200
    data = res.json()
    assert data["visibility"] == "public"


def test_publish_unconfirmed_contribution_fails_with_400():
    """Strict Defense-in-Depth Guard: Unconfirmed (pending, self-declared) cannot be published."""
    author = MagicMock(id="user-publish-unconfirmed-author", email="unconfirmed@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author

    for status_val in ["pending", "self-declared", "draft", "source-verified"]:
        cid = f"c-unconfirmed-{status_val}"
        DEV_CONTRIBUTIONS_DB.append({
            "id": cid,
            "project": "proj-publish-1",
            "contributor": author.id,
            "title": f"Feature {status_val}",
            "category": "code",
            "verification_status": status_val,
            "visibility": "private",
            "dispute_state": "none",
            "created_at": "2026-09-01T10:00:00Z",
            "updated_at": "2026-09-01T10:00:00Z",
        })

        res = client.post(f"/contributions/{cid}/publish")
        assert res.status_code == 400, f"Expected 400 for status {status_val}, got {res.status_code}"
        assert "Only confirmed contributions can be published" in res.json()["detail"]


def test_publish_disputed_or_needs_review_fails_with_400():
    """Disputed / needs-review contributions must NEVER be publishable."""
    author = MagicMock(id="user-publish-disputed-author", email="disputed@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author

    cid = "c-disputed-publish-test"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-publish-1",
        "contributor": author.id,
        "title": "Disputed Delivery",
        "category": "code",
        "verification_status": "needs-review",
        "visibility": "private",
        "dispute_state": "disputed",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z",
    })

    res = client.post(f"/contributions/{cid}/publish")
    assert res.status_code == 400
    assert "Only confirmed contributions can be published" in res.json()["detail"]


def test_unpublish_contribution_success():
    """Unpublish endpoint toggles visibility to private."""
    author = MagicMock(id="user-unpublish-author", email="author@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: author

    cid = "c-unpublish-test-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-publish-1",
        "contributor": author.id,
        "title": "CI/CD Pipeline Setup",
        "category": "devops",
        "verification_status": "confirmed",
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z",
    })

    res = client.post(f"/contributions/{cid}/unpublish")
    assert res.status_code == 200
    data = res.json()
    assert data["visibility"] == "private"

    updated = next(c for c in DEV_CONTRIBUTIONS_DB if c["id"] == cid)
    assert updated["visibility"] == "private"


def test_publish_unpublish_unauthorized_fails_with_403():
    """Non-author and non-owner cannot publish or unpublish."""
    author = MagicMock(id="user-auth-owner", email="owner@buildcrew.io")
    intruder = MagicMock(id="user-intruder", email="intruder@buildcrew.io")

    cid = "c-auth-test-1"
    DEV_CONTRIBUTIONS_DB.append({
        "id": cid,
        "project": "proj-publish-1",
        "contributor": author.id,
        "title": "Private Module",
        "verification_status": "confirmed",
        "visibility": "private",
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-01T10:00:00Z",
    })

    app.dependency_overrides[get_current_user] = lambda: intruder
    pub_res = client.post(f"/contributions/{cid}/publish")
    assert pub_res.status_code == 403

    unpub_res = client.post(f"/contributions/{cid}/unpublish")
    assert unpub_res.status_code == 403


def test_publish_unpublish_not_found_fails_with_404():
    """Nonexistent contribution returns 404."""
    user = MagicMock(id="user-any", email="user@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: user

    pub_res = client.post("/contributions/nonexistent-id-999/publish")
    assert pub_res.status_code == 404

    unpub_res = client.post("/contributions/nonexistent-id-999/unpublish")
    assert unpub_res.status_code == 404


