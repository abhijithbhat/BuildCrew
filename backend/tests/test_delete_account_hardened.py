from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from core.dependencies import get_current_user
from main import app

client = TestClient(app)


def _setup_mock_supabase(user_id="user-del-test", email="del@buildcrew.io"):
    mock_supabase = MagicMock()
    mock_user = MagicMock(id=user_id, email=email)
    mock_supabase.auth.get_user.return_value = MagicMock(user=mock_user)
    return mock_supabase, mock_user


def test_admin_delete_raises_returns_500():
    """1. When supabase.auth.admin.delete_user raises: returns HTTP 500 with generic message."""
    mock_supabase, mock_user = _setup_mock_supabase()

    # DB: no owned projects
    mock_projects_table = MagicMock()
    mock_projects_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value = mock_projects_table

    # Storage: empty
    mock_supabase.storage.from_.return_value.list.return_value = []

    # Admin delete raises exception
    mock_supabase.auth.admin.delete_user.side_effect = Exception("Auth service failure: internal database down")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete account. Please try again."


def test_db_step_raises_returns_500_and_auth_delete_not_attempted():
    """2. When a DB step raises: returns 500 and supabase.auth.admin.delete_user is NOT attempted."""
    mock_supabase, mock_user = _setup_mock_supabase()

    # DB: projects select raises
    mock_projects_table = MagicMock()
    mock_projects_table.select.return_value.eq.return_value.execute.side_effect = Exception(
        "Database connection dropped"
    )
    mock_supabase.table.return_value = mock_projects_table

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete account. Please try again."

        # Verify auth delete was NOT attempted
        mock_supabase.auth.admin.delete_user.assert_not_called()


def test_delete_account_happy_path_200():
    """3. Happy path: user owns sole-member project; GitHub app uninstalled; storage cleared; auth user deleted -> 200."""
    user_id = "user-sole-owner"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    # Project query returns 1 owned project
    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "projects":
            # select owned projects
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "proj-solo-1"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-solo-1"}])
        elif table_name == "project_members":
            # Only current user is a member
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"user_id": user_id, "joined_at": "2026-01-01T00:00:00Z"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "github_installations":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"installation_id": "inst-999"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        else:
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router

    # Storage: empty
    mock_supabase.storage.from_.return_value.list.return_value = []

    # Auth admin: delete succeeds
    mock_supabase.auth.admin.delete_user.return_value = None

    # Auth admin: confirm user no longer exists via 404
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

    # Mock GitHub uninstall DELETE
    mock_gh_response = MagicMock(status_code=204)
    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase), patch(
        "routers.auth.generate_app_jwt", return_value="mock.jwt.token"
    ), patch("httpx.AsyncClient.delete", return_value=mock_gh_response) as mock_delete:
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["user_id"] == user_id
        mock_delete.assert_called_once()
        assert "inst-999" in mock_delete.call_args[0][0]
        mock_supabase.auth.admin.delete_user.assert_called_once_with(user_id)


def test_ownership_transferred_to_earliest_joined_member():
    """4. If other members exist, transfer ownership to EARLIEST-JOINED member and verify 1 row updated."""
    user_id = "user-team-lead"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    updated_rows = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "projects":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "proj-team-42"}]
            )
            # update ownership
            def mock_update(payload):
                updated_rows.append(payload)
                mock_upd_eq = MagicMock()
                mock_upd_eq.eq.return_value.execute.return_value = MagicMock(
                    data=[{"id": "proj-team-42", "created_by": payload["created_by"]}]
                )
                return mock_upd_eq
            mock_t.update.side_effect = mock_update
        elif table_name == "project_members":
            # 3 members: current user, member A (earlier), member B (later)
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[
                    {"user_id": user_id, "joined_at": "2026-01-01T00:00:00Z"},
                    {"user_id": "member-earliest", "joined_at": "2026-01-02T10:00:00Z"},
                    {"user_id": "member-later", "joined_at": "2026-01-10T12:00:00Z"},
                ]
            )
        return mock_t

    mock_supabase.table.side_effect = table_router
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert len(updated_rows) == 1
        assert updated_rows[0]["created_by"] == "member-earliest"
        mock_supabase.auth.admin.delete_user.assert_called_once_with(user_id)


def test_storage_objects_removed():
    """5. Delete every object under '{user_id}/' in the 'evidence' bucket until empty."""
    user_id = "user-storage-cleanup"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    # No projects
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    # Storage: first call returns 2 objects, second call returns empty
    storage_calls = []
    def mock_list(path):
        if not storage_calls:
            storage_calls.append(path)
            return [{"name": "spec.pdf"}, {"name": "wireframe.png"}]
        return []

    mock_bucket = MagicMock()
    mock_bucket.list.side_effect = mock_list
    removed_batches = []
    mock_bucket.remove.side_effect = lambda paths: removed_batches.append(paths)
    mock_supabase.storage.from_.return_value = mock_bucket

    mock_supabase.auth.admin.delete_user.return_value = None
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert len(removed_batches) == 1
        assert removed_batches[0] == [
            f"{user_id}/spec.pdf",
            f"{user_id}/wireframe.png",
        ]


def test_user_still_exists_after_delete_raises_500():
    """User confirmed still present via get_user_by_id -> raises 500 (never returns 200)."""
    user_id = "user-undel"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None

    # get_user_by_id returns a user object (user was not deleted)
    mock_supabase.auth.admin.get_user_by_id.return_value = MagicMock(user=MagicMock(id=user_id))

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete account. Please try again."
