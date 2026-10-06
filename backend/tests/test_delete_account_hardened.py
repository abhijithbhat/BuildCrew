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


def test_storage_cleanup_capped_at_50_iterations_and_raises():
    """1. Storage cleanup loop is capped at 50 iterations and raises 500 if objects still listed afterwards."""
    user_id = "user-storage-infinite"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    # Storage bucket continuously returns items (e.g. all 50 iterations see objects)
    mock_bucket = MagicMock()
    mock_bucket.list.return_value = [{"name": "stuck_file.png"}]
    mock_supabase.storage.from_.return_value = mock_bucket

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete account. Please try again."

        # The loop ran exactly 50 times, plus 1 check afterwards (51 total list calls)
        assert mock_bucket.list.call_count == 51
        assert mock_bucket.remove.call_count == 50

        # auth.admin.delete_user should NOT have been called because cleanup failed
        mock_supabase.auth.admin.delete_user.assert_not_called()


def test_post_delete_check_user_uuid_contains_404_raises_500():
    """2a. Post-delete check does not false-pass when a user UUID contains '404' and user still exists."""
    user_id = "40404040-4040-4040-4040-404040404040"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None

    # get_user_by_id returns a user (user still exists despite delete call)
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


def test_post_delete_check_auth_api_error_404_treated_as_deleted():
    """2b. Post-delete check treats not-found 404 AuthApiError as successfully deleted -> 200."""
    from supabase import AuthApiError

    user_id = "user-auth-api-error-test"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None

    # Supabase AuthApiError 404
    mock_supabase.auth.admin.get_user_by_id.side_effect = AuthApiError("User not found", 404, "not_found")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"


def test_post_delete_check_other_exception_returns_500():
    """2c. Post-delete check returns 500 if get_user_by_id raises any other exception (e.g. 500 DB down)."""
    from supabase import AuthApiError

    user_id = "user-get-error-500"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None

    # AuthApiError with status 500
    mock_supabase.auth.admin.get_user_by_id.side_effect = AuthApiError("Internal server error", 500, "internal_error")

    with patch(
        "core.dependencies.get_supabase_pub_client", return_value=mock_supabase
    ), patch("routers.auth.get_supabase_client", return_value=mock_supabase):
        response = client.delete(
            "/auth/me",
            headers={"Authorization": "Bearer token"},
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete account. Please try again."


def test_github_uninstall_not_called_when_shared_with_another_project():
    """3a. Only call GitHub DELETE /app/installations/{id} when NO other github_installations row references it."""
    user_id = "user-shared-gh"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "projects":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "proj-shared-1"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-shared-1"}])
        elif table_name == "project_members":
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"user_id": user_id, "joined_at": "2026-01-01T00:00:00Z"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "github_installations":
            def mock_select(fields):
                mock_sel = MagicMock()
                def mock_eq(field, val):
                    mock_eq_obj = MagicMock()
                    if field == "project_id":
                        # query for project's own installations
                        mock_eq_obj.execute.return_value = MagicMock(
                            data=[{"installation_id": "inst-shared"}]
                        )
                    elif field == "installation_id":
                        # query for other installations with same installation_id
                        mock_neq_obj = MagicMock()
                        mock_neq_obj.execute.return_value = MagicMock(
                            data=[{"project_id": "proj-other"}]  # Another project references inst-shared!
                        )
                        mock_eq_obj.neq.return_value = mock_neq_obj
                    return mock_eq_obj
                mock_sel.eq.side_effect = mock_eq
                return mock_sel

            mock_t.select.side_effect = mock_select
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        else:
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

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
        # GitHub uninstall must NOT have been called because another project references inst-shared!
        mock_delete.assert_not_called()


def test_github_uninstall_called_when_no_other_project_references_installation():
    """3b. Call GitHub DELETE /app/installations/{id} when NO other github_installations row references it."""
    user_id = "user-sole-gh"
    mock_supabase, mock_user = _setup_mock_supabase(user_id=user_id)

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "projects":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "proj-sole-1"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "proj-sole-1"}])
        elif table_name == "project_members":
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"user_id": user_id, "joined_at": "2026-01-01T00:00:00Z"}]
            )
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif table_name == "github_installations":
            def mock_select(fields):
                mock_sel = MagicMock()
                def mock_eq(field, val):
                    mock_eq_obj = MagicMock()
                    if field == "project_id":
                        mock_eq_obj.execute.return_value = MagicMock(
                            data=[{"installation_id": "inst-sole"}]
                        )
                    elif field == "installation_id":
                        mock_neq_obj = MagicMock()
                        mock_neq_obj.execute.return_value = MagicMock(
                            data=[]  # NO other project references inst-sole!
                        )
                        mock_eq_obj.neq.return_value = mock_neq_obj
                    return mock_eq_obj
                mock_sel.eq.side_effect = mock_eq
                return mock_sel

            mock_t.select.side_effect = mock_select
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        else:
            mock_t.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router
    mock_supabase.storage.from_.return_value.list.return_value = []
    mock_supabase.auth.admin.delete_user.return_value = None
    mock_supabase.auth.admin.get_user_by_id.side_effect = Exception("User not found: 404")

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
        # GitHub uninstall MUST have been called!
        mock_delete.assert_called_once()
        assert "inst-sole" in mock_delete.call_args[0][0]
