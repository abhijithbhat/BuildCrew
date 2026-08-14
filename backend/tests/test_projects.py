import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_PROJECTS_DB,
    DEV_PROJECT_INVITES_DB,
    DEV_PROJECT_MEMBERS_DB,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_state():
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()



def test_create_project_unauthenticated():
    response = client.post(
        "/projects",
        json={"name": "Test Project", "description": "Test description"},
    )
    assert response.status_code in (401, 403)


def test_create_project_empty_name():
    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.post(
        "/projects",
        json={"name": "   ", "description": "Test description"},
        headers={"Authorization": "Bearer mock-dev-access-token-user@example.com"},
    )
    assert response.status_code == 422
    assert "Project name cannot be empty" in response.json()["detail"]


def test_create_project_success_supabase():
    mock_supabase = MagicMock()

    # Mock project insert
    mock_project_table = MagicMock()
    mock_project_insert = MagicMock()
    mock_project_insert.execute.return_value = MagicMock(
        data=[
            {
                "id": "proj-uuid-1234",
                "name": "BuildCrew Mobile",
                "description": "Collaborative builder platform",
                "created_by": "user-123",
                "created_at": "2026-08-14T10:00:00Z",
                "updated_at": "2026-08-14T10:00:00Z",
            }
        ]
    )
    mock_project_table.insert.return_value = mock_project_insert

    # Mock member insert
    mock_member_table = MagicMock()
    mock_member_insert = MagicMock()
    mock_member_insert.execute.return_value = MagicMock(
        data=[
            {
                "project_id": "proj-uuid-1234",
                "user_id": "user-123",
                "role": "owner",
                "joined_at": "2026-08-14T10:00:00Z",
            }
        ]
    )
    mock_member_table.insert.return_value = mock_member_insert

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_project_table
        elif table_name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects",
            json={
                "name": "BuildCrew Mobile",
                "description": "Collaborative builder platform",
            },
            headers={"Authorization": "Bearer valid-token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Project created successfully"
        assert data["project"]["id"] == "proj-uuid-1234"
        assert data["project"]["name"] == "BuildCrew Mobile"
        assert data["project"]["created_by"] == "user-123"
        assert data["member"]["project_id"] == "proj-uuid-1234"
        assert data["member"]["user_id"] == "user-123"
        assert data["member"]["role"] == "owner"

        # Verify insert payloads
        mock_project_table.insert.assert_called_once_with(
            {
                "name": "BuildCrew Mobile",
                "description": "Collaborative builder platform",
                "created_by": "user-123",
            }
        )
        mock_member_table.insert.assert_called_once_with(
            {
                "project_id": "proj-uuid-1234",
                "user_id": "user-123",
                "role": "owner",
            }
        )


def test_create_project_local_dev_fallback():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    mock_user = MagicMock(id="dev-user-777", email="dev@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects",
            json={
                "name": "Dev Mode Project",
                "description": "Running locally without internet",
            },
            headers={"Authorization": "Bearer mock-dev-access-token-dev@example.com"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "Local Dev Mode" in data["message"]
        assert data["project"]["name"] == "Dev Mode Project"
        assert data["project"]["created_by"] == "dev-user-777"
        assert data["member"]["role"] == "owner"
        assert data["member"]["user_id"] == "dev-user-777"


def test_list_projects_unauthenticated():
    response = client.get("/projects")
    assert response.status_code in (401, 403)


def test_list_projects_user_membership_supabase():
    mock_supabase = MagicMock()
    
    mock_members_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[
            {
                "role": "owner",
                "joined_at": "2026-08-14T10:00:00Z",
                "projects": {
                    "id": "proj-1",
                    "name": "My Team Project",
                    "description": "Collaborative project",
                    "created_by": "user-123",
                    "created_at": "2026-08-14T10:00:00Z",
                    "updated_at": "2026-08-14T10:00:00Z",
                },
            }
        ]
    )
    mock_select.eq.return_value = mock_eq
    mock_members_table.select.return_value = mock_select

    mock_projects_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_eq.execute.return_value = MagicMock(data=[])
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_projects_table.select.return_value = mock_proj_select

    def table_side_effect(table_name):
        if table_name == "project_members":
            return mock_members_table
        elif table_name == "projects":
            return mock_projects_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/projects",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["id"] == "proj-1"
        assert data["projects"][0]["name"] == "My Team Project"
        assert data["projects"][0]["role"] == "owner"


def test_list_projects_local_dev_membership_filter():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    # Populate in-memory state with projects belonging to user-1 and user-2
    DEV_PROJECTS_DB["proj-user1"] = {
        "id": "proj-user1",
        "name": "User 1 Project",
        "description": "Belongs to user 1",
        "created_by": "user-1",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-user1",
        "user_id": "user-1",
        "role": "owner",
    })

    DEV_PROJECTS_DB["proj-user2"] = {
        "id": "proj-user2",
        "name": "User 2 Project",
        "description": "Belongs to user 2",
        "created_by": "user-2",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-user2",
        "user_id": "user-2",
        "role": "owner",
    })

    mock_user1 = MagicMock(id="user-1", email="user1@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user1

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/projects",
            headers={"Authorization": "Bearer mock-dev-access-token-user1@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["id"] == "proj-user1"
        assert data["projects"][0]["name"] == "User 1 Project"
        assert data["projects"][0]["role"] == "owner"


def test_generate_invite_unauthenticated():
    response = client.post("/projects/proj-123/invite")
    assert response.status_code in (401, 403)


def test_generate_invite_project_not_found():
    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(data=None)
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select
    mock_supabase.table.return_value = mock_proj_table

    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/non-existent-proj/invite",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


def test_generate_invite_forbidden_for_non_member():
    mock_supabase = MagicMock()

    # Project exists with created_by = another-user
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-123", "name": "Private Project", "created_by": "other-user"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # project_members query returns empty (user is not a member)
    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(data=[])
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="intruder-user", email="intruder@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-123/invite",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403
        assert "must be a member" in response.json()["detail"]


def test_generate_invite_success_supabase():
    mock_supabase = MagicMock()

    # Project exists
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-123", "name": "BuildCrew Core", "created_by": "user-123"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # User is member
    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(
        data=[{"project_id": "proj-123", "user_id": "user-123", "role": "owner"}]
    )
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-123", email="user@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-123/invite",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj-123"
        assert data["project_name"] == "BuildCrew Core"
        assert data["created_by"] == "user-123"
        assert data["invite_code"].startswith("BC-")
        assert "https://buildcrew.app/join/BC-" in data["invite_url"]
        assert "Invite code generated successfully" in data["message"]


def test_generate_invite_success_local_dev():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-dev-99"] = {
        "id": "proj-dev-99",
        "name": "Dev Offline Project",
        "created_by": "user-dev-99",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-dev-99",
        "user_id": "user-dev-99",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-dev-99", email="dev@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-dev-99/invite",
            headers={"Authorization": "Bearer mock-dev-access-token-dev@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == "proj-dev-99"
        assert data["project_name"] == "Dev Offline Project"
        assert data["invite_code"].startswith("BC-")
        assert "Local Dev Mode" in data["message"]


def test_join_project_unauthenticated():
    response = client.post("/projects/join", json={"invite_code": "BC-123456"})
    assert response.status_code in (401, 403)


def test_join_project_empty_code():
    mock_user = MagicMock(id="user-joiner", email="joiner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.post(
        "/projects/join",
        json={"invite_code": "   "},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 422
    assert "Invite code cannot be empty" in response.json()["detail"]


def test_join_project_invalid_code():
    mock_user = MagicMock(id="user-joiner", email="joiner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.post(
        "/projects/join",
        json={"invite_code": "BC-NONEXIST"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 404
    assert "Invalid or expired invite code" in response.json()["detail"]


def test_join_project_already_member_supabase():
    mock_supabase = MagicMock()

    DEV_PROJECT_INVITES_DB["BC-EXISTS"] = {
        "invite_code": "BC-EXISTS",
        "project_id": "proj-existing-1",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-existing-1", "name": "Existing Project"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(
        data=[{"project_id": "proj-existing-1", "user_id": "user-already-in"}]
    )
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-already-in", email="in@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/join",
            json={"invite_code": "BC-EXISTS"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 409
        assert "already a member" in response.json()["detail"]


def test_join_project_success_supabase():
    mock_supabase = MagicMock()

    DEV_PROJECT_INVITES_DB["BC-VALID1"] = {
        "invite_code": "BC-VALID1",
        "project_id": "proj-valid-1",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-valid-1", "name": "Valid Supabase Project"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(data=[])  # Not a member yet
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    mock_member_insert = MagicMock()
    mock_member_insert.execute.return_value = MagicMock(
        data=[{"project_id": "proj-valid-1", "user_id": "new-user-123", "role": "member"}]
    )
    mock_member_table.insert.return_value = mock_member_insert


    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="new-user-123", email="newuser@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/join",
            json={"invite_code": "BC-VALID1"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Successfully joined project"
        assert data["project"]["name"] == "Valid Supabase Project"
        assert data["member"]["user_id"] == "new-user-123"
        assert data["member"]["role"] == "member"


def test_join_project_success_local_dev():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-offline-join"] = {
        "id": "proj-offline-join",
        "name": "Offline Project",
        "created_by": "user-owner",
    }
    DEV_PROJECT_INVITES_DB["BC-OFFLINE"] = {
        "invite_code": "BC-OFFLINE",
        "project_id": "proj-offline-join",
        "expires_at": "2099-01-01T00:00:00Z",
    }

    mock_user = MagicMock(id="user-dev-joiner", email="joiner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/join",
            json={"invite_code": "bc-offline"},  # Lowercase to test normalization
            headers={"Authorization": "Bearer mock-dev-access-token-joiner@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Successfully joined project" in data["message"]
        assert data["project"]["name"] == "Offline Project"
        assert data["member"]["user_id"] == "user-dev-joiner"
        assert data["member"]["role"] == "member"


