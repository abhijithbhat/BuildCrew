import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_PROJECTS_DB,
    DEV_PROJECT_INVITES_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_ROLE_AGREEMENTS_DB,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_state():
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()




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
        assert "invite code" in data["message"].lower()



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


def test_declare_role_unauthenticated():
    response = client.post(
        "/projects/proj-123/role",
        json={"declared_role": "Backend Lead"},
    )
    assert response.status_code in (401, 403)


def test_declare_role_empty_role():
    mock_user = MagicMock(id="user-dev-1", email="dev1@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = client.post(
        "/projects/proj-123/role",
        json={"declared_role": "   ", "responsibilities": "Building APIs"},
        headers={"Authorization": "Bearer valid-token"},
    )
    assert response.status_code == 422
    assert "Declared role cannot be empty" in response.json()["detail"]


def test_declare_role_project_not_found():
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
            "/projects/nonexistent-proj/role",
            json={"declared_role": "DevOps Engineer"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


def test_declare_role_forbidden_for_non_member():
    mock_supabase = MagicMock()

    # Project exists with created_by = other-user
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-123", "name": "BuildCrew Core", "created_by": "other-user"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # User is not in project_members
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

    mock_user = MagicMock(id="outsider-user", email="outsider@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-123/role",
            json={"declared_role": "Security Architect"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403
        assert "must be a member" in response.json()["detail"]


def test_declare_role_create_success_supabase():
    mock_supabase = MagicMock()

    # Project exists
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-abc-1", "name": "AI Workspace", "created_by": "user-dev-1"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # Member check
    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(
        data=[{"project_id": "proj-abc-1", "user_id": "user-dev-1", "role": "owner"}]
    )
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    # Existing role check -> empty (new declaration)
    mock_role_table = MagicMock()
    mock_role_select = MagicMock()
    mock_role_eq1 = MagicMock()
    mock_role_eq2 = MagicMock()
    mock_role_eq2.execute.return_value = MagicMock(data=[])
    mock_role_eq1.eq.return_value = mock_role_eq2
    mock_role_select.eq.return_value = mock_role_eq1
    mock_role_table.select.return_value = mock_role_select

    # Role insert
    mock_role_insert = MagicMock()
    mock_role_insert.execute.return_value = MagicMock(
        data=[
            {
                "id": "role-uuid-001",
                "project_id": "proj-abc-1",
                "user_id": "user-dev-1",
                "declared_role": "Lead Architect",
                "responsibilities": "System design and core APIs",
                "deadline": "2026-10-01T00:00:00Z",
                "created_at": "2026-08-16T12:00:00Z",
                "updated_at": "2026-08-16T12:00:00Z",
            }
        ]
    )
    mock_role_table.insert.return_value = mock_role_insert

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        elif table_name == "role_agreements":
            return mock_role_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-dev-1", email="dev1@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-abc-1/role",
            json={
                "declared_role": "Lead Architect",
                "responsibilities": "System design and core APIs",
                "deadline": "2026-10-01T00:00:00Z",
            },
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Role declared successfully"
        assert data["role_agreement"]["declared_role"] == "Lead Architect"
        assert data["role_agreement"]["responsibilities"] == "System design and core APIs"
        assert data["role_agreement"]["project_id"] == "proj-abc-1"
        assert data["role_agreement"]["user_id"] == "user-dev-1"


def test_declare_role_update_success_supabase():
    mock_supabase = MagicMock()

    # Project exists
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-abc-1", "name": "AI Workspace", "created_by": "user-dev-1"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # Member check
    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    mock_member_eq2.execute.return_value = MagicMock(
        data=[{"project_id": "proj-abc-1", "user_id": "user-dev-1", "role": "owner"}]
    )
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select

    # Existing role check -> has existing record
    mock_role_table = MagicMock()
    mock_role_select = MagicMock()
    mock_role_eq1 = MagicMock()
    mock_role_eq2 = MagicMock()
    mock_role_eq2.execute.return_value = MagicMock(
        data=[
            {
                "id": "role-uuid-001",
                "project_id": "proj-abc-1",
                "user_id": "user-dev-1",
                "declared_role": "Architect",
                "responsibilities": "Old responsibilities",
                "deadline": None,
                "created_at": "2026-08-14T00:00:00Z",
                "updated_at": "2026-08-14T00:00:00Z",
            }
        ]
    )
    mock_role_eq1.eq.return_value = mock_role_eq2
    mock_role_select.eq.return_value = mock_role_eq1
    mock_role_table.select.return_value = mock_role_select

    # Role update
    mock_role_update = MagicMock()
    mock_update_eq = MagicMock()
    mock_update_eq.execute.return_value = MagicMock(
        data=[
            {
                "id": "role-uuid-001",
                "project_id": "proj-abc-1",
                "user_id": "user-dev-1",
                "declared_role": "Principal Engineer",
                "responsibilities": "Updated responsibilities",
                "deadline": "2026-12-31T00:00:00Z",
                "created_at": "2026-08-14T00:00:00Z",
                "updated_at": "2026-08-16T12:00:00Z",
            }
        ]
    )
    mock_role_update.eq.return_value = mock_update_eq
    mock_role_table.update.return_value = mock_role_update

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        elif table_name == "role_agreements":
            return mock_role_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-dev-1", email="dev1@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.post(
            "/projects/proj-abc-1/role",
            json={
                "declared_role": "Principal Engineer",
                "responsibilities": "Updated responsibilities",
                "deadline": "2026-12-31T00:00:00Z",
            },
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Role agreement updated successfully"
        assert data["role_agreement"]["declared_role"] == "Principal Engineer"
        assert data["role_agreement"]["responsibilities"] == "Updated responsibilities"


def test_declare_role_create_and_update_local_dev():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-offline-1"] = {
        "id": "proj-offline-1",
        "name": "Offline Project",
        "created_by": "user-offline-1",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-offline-1",
        "user_id": "user-offline-1",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-offline-1", email="offline@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # 1. Initial declaration using 'role' alias key
        response1 = client.post(
            "/projects/proj-offline-1/role",
            json={
                "role": "Fullstack Developer",
                "responsibilities": "Building Flutter UI and FastAPI backend",
            },
            headers={"Authorization": "Bearer mock-dev-access-token-offline@example.com"},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert "Role declared successfully" in data1["message"]
        assert data1["role_agreement"]["declared_role"] == "Fullstack Developer"
        assert data1["role_agreement"]["responsibilities"] == "Building Flutter UI and FastAPI backend"
        assert data1["role_agreement"]["project_id"] == "proj-offline-1"
        assert data1["role_agreement"]["user_id"] == "user-offline-1"
        assert len(DEV_ROLE_AGREEMENTS_DB) == 1

        # 2. Update existing role declaration
        response2 = client.post(
            "/projects/proj-offline-1/role",
            json={
                "declared_role": "Engineering Lead",
                "responsibilities": "Architecture, Code Reviews, and Deployment",
            },
            headers={"Authorization": "Bearer mock-dev-access-token-offline@example.com"},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert "Role agreement updated successfully" in data2["message"]
        assert data2["role_agreement"]["declared_role"] == "Engineering Lead"
        assert data2["role_agreement"]["responsibilities"] == "Architecture, Code Reviews, and Deployment"
        assert len(DEV_ROLE_AGREEMENTS_DB) == 1  # Still 1 record (updated in place)


def test_list_project_roles_unauthenticated():
    response = client.get("/projects/proj-123/roles")
    assert response.status_code in (401, 403)


def test_list_project_roles_project_not_found():
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
        response = client.get(
            "/projects/non-existent/roles",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 404
        assert "Project not found" in response.json()["detail"]


def test_list_project_roles_forbidden_for_non_member():
    mock_supabase = MagicMock()

    # Project exists with created_by = other-user
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-xyz", "name": "Secret Project", "created_by": "other-user"}
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

    mock_user = MagicMock(id="outsider-user", email="outsider@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/projects/proj-xyz/roles",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 403
        assert "must be a member" in response.json()["detail"]


def test_list_project_roles_success_supabase():
    mock_supabase = MagicMock()

    # Project exists
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_eq = MagicMock()
    mock_proj_single = MagicMock()
    mock_proj_single.execute.return_value = MagicMock(
        data={"id": "proj-supabase-1", "name": "Supabase Project", "created_by": "user-owner"}
    )
    mock_proj_eq.single.return_value = mock_proj_single
    mock_proj_select.eq.return_value = mock_proj_eq
    mock_proj_table.select.return_value = mock_proj_select

    # User is member and members query
    mock_member_table = MagicMock()
    mock_member_select = MagicMock()
    mock_member_eq1 = MagicMock()
    mock_member_eq2 = MagicMock()
    members_data = [
        {"project_id": "proj-supabase-1", "user_id": "user-owner", "role": "owner"},
        {"project_id": "proj-supabase-1", "user_id": "user-member-2", "role": "member"},
    ]
    mock_member_eq1.execute.return_value = MagicMock(data=members_data)
    mock_member_eq2.execute.return_value = MagicMock(data=members_data)
    mock_member_eq1.eq.return_value = mock_member_eq2
    mock_member_select.eq.return_value = mock_member_eq1
    mock_member_table.select.return_value = mock_member_select


    # Role agreements query
    mock_role_table = MagicMock()
    mock_role_select = MagicMock()
    mock_role_eq = MagicMock()
    mock_role_eq.execute.return_value = MagicMock(
        data=[
            {
                "id": "role-1",
                "project_id": "proj-supabase-1",
                "user_id": "user-owner",
                "declared_role": "Project Lead",
                "responsibilities": "Roadmap and oversight",
                "deadline": None,
                "created_at": "2026-08-16T10:00:00Z",
                "updated_at": "2026-08-16T10:00:00Z",
            },
            {
                "id": "role-2",
                "project_id": "proj-supabase-1",
                "user_id": "user-member-2",
                "declared_role": "Backend Engineer",
                "responsibilities": "APIs and database schemas",
                "deadline": "2026-11-01T00:00:00Z",
                "created_at": "2026-08-16T11:00:00Z",
                "updated_at": "2026-08-16T11:00:00Z",
            },
        ]
    )
    mock_role_select.eq.return_value = mock_role_eq
    mock_role_table.select.return_value = mock_role_select

    def table_side_effect(table_name):
        if table_name == "projects":
            return mock_proj_table
        elif table_name == "project_members":
            return mock_member_table
        elif table_name == "role_agreements":
            return mock_role_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id="user-owner", email="owner@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/projects/proj-supabase-1/roles",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["roles"]) == 2
        assert data["roles"][0]["declared_role"] == "Project Lead"
        assert data["roles"][1]["declared_role"] == "Backend Engineer"
        assert data["project_id"] == "proj-supabase-1"


def test_list_project_roles_success_local_dev():
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-offline-roles"] = {
        "id": "proj-offline-roles",
        "name": "Offline Roles Test",
        "created_by": "user-offline-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-offline-roles",
        "user_id": "user-offline-lead",
        "role": "owner",
    })
    DEV_ROLE_AGREEMENTS_DB.append({
        "id": "dev-role-1",
        "project_id": "proj-offline-roles",
        "user_id": "user-offline-lead",
        "declared_role": "Flutter Dev",
        "responsibilities": "Mobile app implementation",
        "deadline": None,
        "created_at": "2026-08-16T10:00:00Z",
        "updated_at": "2026-08-16T10:00:00Z",
    })

    mock_user = MagicMock(id="user-offline-lead", email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        response = client.get(
            "/projects/proj-offline-roles/roles",
            headers={"Authorization": "Bearer mock-dev-access-token-lead@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["roles"]) == 1
        assert data["roles"][0]["declared_role"] == "Flutter Dev"
        assert data["roles"][0]["responsibilities"] == "Mobile app implementation"
        assert data["project_id"] == "proj-offline-roles"


def test_permanent_invite_code_reuse():
    """Verify that multiple calls to generate_project_invite return the exact same permanent code."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-perm-test"] = {
        "id": "proj-perm-test",
        "name": "Permanent Code Project",
        "created_by": "user-lead-1",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-perm-test",
        "user_id": "user-lead-1",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-lead-1", email="lead1@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # 1st call
        res1 = client.post(
            "/projects/proj-perm-test/invite",
            headers={"Authorization": "Bearer token"},
        )
        assert res1.status_code == 200
        code1 = res1.json()["invite_code"]

        # 2nd call (same project)
        res2 = client.post(
            "/projects/proj-perm-test/invite",
            headers={"Authorization": "Bearer token"},
        )
        assert res2.status_code == 200
        code2 = res2.json()["invite_code"]

        # Must be identical permanent code
        assert code1 == code2


def test_regenerate_invite_code_team_lead():
    """Verify that Team Lead can regenerate invite code, revoking the old one."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-regen-test"] = {
        "id": "proj-regen-test",
        "name": "Regen Code Project",
        "created_by": "user-lead-regen",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-regen-test",
        "user_id": "user-lead-regen",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-lead-regen", email="leadregen@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        # 1st call: initial code
        res1 = client.post(
            "/projects/proj-regen-test/invite",
            headers={"Authorization": "Bearer token"},
        )
        assert res1.status_code == 200
        code1 = res1.json()["invite_code"]

        # 2nd call: regenerate endpoint
        res2 = client.post(
            "/projects/proj-regen-test/invite/regenerate",
            headers={"Authorization": "Bearer token"},
        )
        assert res2.status_code == 200
        code2 = res2.json()["invite_code"]

        # Must have generated a new distinct code
        assert code1 != code2

        # Old code must be revoked
        join_old = client.post(
            "/projects/join",
            json={"invite_code": code1},
            headers={"Authorization": "Bearer token"},
        )
        assert join_old.status_code in [404, 400]


def test_regenerate_invite_code_forbidden_for_non_lead():
    """Verify that non-lead members cannot regenerate the invite code."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-nonlead-test"] = {
        "id": "proj-nonlead-test",
        "name": "Non-Lead Project",
        "created_by": "user-actual-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-nonlead-test",
        "user_id": "user-regular-member",
        "role": "member",
    })

    mock_user = MagicMock(id="user-regular-member", email="member@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.post(
            "/projects/proj-nonlead-test/invite/regenerate",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 403
        assert "Only the Team Lead" in res.json()["detail"]


def test_delete_project_success_team_lead():
    """Verify that Team Lead can permanently dismantle / delete the project."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-del-1"] = {
        "id": "proj-del-1",
        "name": "Delete Me Project",
        "created_by": "user-del-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-del-1",
        "user_id": "user-del-lead",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-del-lead", email="dellead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.delete(
            "/projects/proj-del-1",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 200
        assert "dismantled" in res.json()["message"].lower()
        assert "proj-del-1" not in DEV_PROJECTS_DB


def test_delete_project_forbidden_non_lead():
    """Verify that non-lead members cannot dismantle the project."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-del-2"] = {
        "id": "proj-del-2",
        "name": "Protected Project",
        "created_by": "user-real-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-del-2",
        "user_id": "user-member-intruder",
        "role": "member",
    })

    mock_user = MagicMock(id="user-member-intruder", email="intruder@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.delete(
            "/projects/proj-del-2",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 403
        assert "Only the Team Lead" in res.json()["detail"]


def test_leave_project_success_teammate():
    """Verify that a joined teammate can leave the project."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-leave-1"] = {
        "id": "proj-leave-1",
        "name": "Team Project",
        "created_by": "user-proj-creator",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-leave-1",
        "user_id": "user-quitter",
        "role": "member",
    })

    mock_user = MagicMock(id="user-quitter", email="quitter@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.post(
            "/projects/proj-leave-1/leave",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 200
        assert "left the project" in res.json()["message"].lower()


def test_leave_project_forbidden_for_team_lead():
    """Verify that the Team Lead cannot leave the project without dismantling."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-leave-lead"] = {
        "id": "proj-leave-lead",
        "name": "Leader Project",
        "created_by": "user-captain",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-leave-lead",
        "user_id": "user-captain",
        "role": "owner",
    })

    mock_user = MagicMock(id="user-captain", email="captain@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.post(
            "/projects/proj-leave-lead/leave",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 400
        assert "Team Lead cannot leave" in res.json()["detail"]


def test_remove_member_success_team_lead():
    """Verify that Team Lead can remove a teammate."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-kick-1"] = {
        "id": "proj-kick-1",
        "name": "Kick Project",
        "created_by": "user-kick-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-kick-1",
        "user_id": "user-kick-lead",
        "role": "owner",
    })
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-kick-1",
        "user_id": "user-to-kick",
        "role": "member",
    })

    mock_user = MagicMock(id="user-kick-lead", email="kicklead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.delete(
            "/projects/proj-kick-1/members/user-to-kick",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 200
        assert "removed" in res.json()["message"].lower()


def test_remove_member_forbidden_non_lead():
    """Verify that a regular member cannot remove another member."""
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = Exception("nodename nor servname provided")

    DEV_PROJECTS_DB["proj-kick-2"] = {
        "id": "proj-kick-2",
        "name": "Kick Project 2",
        "created_by": "user-kick-real-lead",
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-kick-2",
        "user_id": "user-not-lead",
        "role": "member",
    })
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": "proj-kick-2",
        "user_id": "user-target",
        "role": "member",
    })

    mock_user = MagicMock(id="user-not-lead", email="notlead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        res = client.delete(
            "/projects/proj-kick-2/members/user-target",
            headers={"Authorization": "Bearer token"},
        )
        assert res.status_code == 403
        assert "Only the Team Lead" in res.json()["detail"]






