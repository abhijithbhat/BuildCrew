import pytest
from unittest.mock import MagicMock, patch
import httpx
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from core.errors import handle_route_error, raise_route_error
from core.rate_limit import get_real_client_ip
from main import app
from routers.projects import DEV_PROJECTS_DB, DEV_PROJECT_MEMBERS_DB, DEV_PROJECT_INVITES_DB
from postgrest.exceptions import APIError


class TestRouteErrorMappingHelper:
    """Tests for requirement 1: handle_route_error centralized mapping."""

    def test_httpx_transport_and_timeout_errors(self):
        connect_err = httpx.ConnectTimeout("Connection timed out to upstream service")
        exc1 = handle_route_error(connect_err, generic_message="Failed to fetch data.")
        assert exc1.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc1.detail == "Service temporarily unavailable. Please try again."
        assert exc1.headers.get("Retry-After") == "5"

        read_err = httpx.ReadTimeout("Upstream read timed out")
        exc2 = handle_route_error(read_err, generic_message="Failed to fetch data.")
        assert exc2.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc2.detail == "Service temporarily unavailable. Please try again."
        assert exc2.headers.get("Retry-After") == "5"

        net_err = httpx.NetworkError("Network socket closed unexpectedly")
        exc3 = handle_route_error(net_err, generic_message="Failed to fetch data.")
        assert exc3.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc3.headers.get("Retry-After") == "5"

    def test_postgrest_5xx_api_error(self):
        err_503 = APIError({"message": "Service unavailable", "code": "503", "details": None})
        exc1 = handle_route_error(err_503, generic_message="Failed to query database.")
        assert exc1.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc1.detail == "Service temporarily unavailable. Please try again."
        assert exc1.headers.get("Retry-After") == "5"

        err_500 = APIError({"message": "Internal postgrest server error", "code": "500", "details": None})
        exc2 = handle_route_error(err_500, generic_message="Failed to query database.")
        assert exc2.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc2.headers.get("Retry-After") == "5"

    def test_timeout_and_gateway_heuristic_strings(self):
        test_cases = [
            RuntimeError("Request to backend timed out"),
            RuntimeError("Connection timeout after 10000ms"),
            RuntimeError("502 Bad Gateway from upstream CDN"),
            RuntimeError("Upstream returned 503 Service Unavailable"),
            Exception("Host gateway returned 502 error"),
        ]
        for exc in test_cases:
            mapped = handle_route_error(exc, generic_message="Failed to process request.")
            assert mapped.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert mapped.detail == "Service temporarily unavailable. Please try again."
            assert mapped.headers.get("Retry-After") == "5"

    def test_unexpected_errors_map_to_500_with_generic_message(self):
        exc = ValueError("Unexpected invalid state in business logic")
        mapped = handle_route_error(exc, generic_message="Failed to create resource. Please try again.")
        assert mapped.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert mapped.detail == "Failed to create resource. Please try again."

        exc2 = KeyError("missing_column")
        mapped2 = handle_route_error(exc2, generic_message="Failed to fetch records.")
        assert mapped2.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert mapped2.detail == "Failed to fetch records."

    def test_preserves_real_4xx_http_exceptions(self):
        codes = [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]
        for c in codes:
            original = HTTPException(status_code=c, detail=f"Custom client error {c}")
            mapped = handle_route_error(original, generic_message="Generic fallback")
            assert mapped is original
            assert mapped.status_code == c
            assert mapped.detail == f"Custom client error {c}"

    def test_raise_route_error_helper(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_route_error(
                httpx.ConnectTimeout("timed out"),
                generic_message="Failed to do work.",
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.headers.get("Retry-After") == "5"


class TestCreateProjectRollback:
    """Tests for requirement 3: delete just-created project if project_members insert fails."""

    def test_create_project_deletes_project_on_member_insert_failure(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "user-test-creator-123"

        # Mock Supabase
        mock_supabase = MagicMock()
        # project table insert succeeds
        mock_project_table = MagicMock()
        mock_project_res = MagicMock()
        mock_project_res.data = [{
            "id": "proj-uuid-12345",
            "name": "Rollback Test Project",
            "description": "Test rollback description",
            "created_by": "user-test-creator-123",
        }]
        mock_project_table.insert.return_value.execute.return_value = mock_project_res

        # delete builder for project table
        mock_delete_builder = MagicMock()
        mock_delete_eq = MagicMock()
        mock_delete_builder.eq.return_value = mock_delete_eq
        mock_delete_eq.execute.return_value = MagicMock()
        mock_project_table.delete.return_value = mock_delete_builder

        # member table insert fails with timeout
        mock_member_table = MagicMock()
        mock_member_table.insert.return_value.execute.side_effect = httpx.ConnectTimeout("Database connection timed out")

        def table_router(table_name):
            if table_name == "projects":
                return mock_project_table
            if table_name == "project_members":
                return mock_member_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.post(
                    "/projects",
                    json={"name": "Rollback Test Project", "description": "Test rollback description"},
                )
                # Verify that error was mapped to 503 due to timeout
                assert response.status_code == 503
                assert response.headers.get("retry-after") == "5"

                # Verify that projects table delete was called with the project ID
                mock_project_table.delete.assert_called_once()
                mock_delete_builder.eq.assert_called_once_with("id", "proj-uuid-12345")
                mock_delete_eq.execute.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_create_project_deletes_project_on_member_insert_empty_data(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "user-test-creator-456"

        mock_supabase = MagicMock()
        mock_project_table = MagicMock()
        mock_project_res = MagicMock()
        mock_project_res.data = [{
            "id": "proj-uuid-empty-member",
            "name": "Empty Member Project",
            "description": None,
            "created_by": "user-test-creator-456",
        }]
        mock_project_table.insert.return_value.execute.return_value = mock_project_res

        mock_delete_builder = MagicMock()
        mock_delete_eq = MagicMock()
        mock_delete_builder.eq.return_value = mock_delete_eq
        mock_delete_eq.execute.return_value = MagicMock()
        mock_project_table.delete.return_value = mock_delete_builder

        # member table returns empty data
        mock_member_table = MagicMock()
        mock_member_res = MagicMock()
        mock_member_res.data = []
        mock_member_table.insert.return_value.execute.return_value = mock_member_res

        def table_router(table_name):
            if table_name == "projects":
                return mock_project_table
            if table_name == "project_members":
                return mock_member_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.post(
                    "/projects",
                    json={"name": "Empty Member Project"},
                )
                assert response.status_code == 500
                assert response.json()["detail"] == "Failed to create project. Please try again."

                mock_project_table.delete.assert_called_once()
                mock_delete_builder.eq.assert_called_once_with("id", "proj-uuid-empty-member")
                mock_delete_eq.execute.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestJoinProjectNormalization:
    """Tests for requirement 4: normalize invite codes and prepend BC- if 6 alphanumerics."""

    def test_join_project_normalized_codes(self):
        client = TestClient(app)

        # Setup in-memory dev project
        proj_id = "test-proj-norm-1"
        clean_code = "BC-ALPHA1"
        DEV_PROJECTS_DB[proj_id] = {
            "id": proj_id,
            "name": "Normalize Code Project",
            "description": "Project for invite code testing",
            "created_by": "creator-user-999",
            "invite_code": clean_code,
        }
        DEV_PROJECT_INVITES_DB[clean_code] = {"project_id": proj_id}

        mock_user = MagicMock()
        mock_user.id = "new-member-joiner-1"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        try:
            # 1. 6 alphanumeric code without 'BC-' (e.g. 'alpha1')
            res1 = client.post("/projects/join", json={"invite_code": "alpha1"})
            assert res1.status_code == 200
            assert res1.json()["project"]["id"] == proj_id

            # Clean up membership to test other variants
            DEV_PROJECT_MEMBERS_DB[:] = [m for m in DEV_PROJECT_MEMBERS_DB if m.get("user_id") != "new-member-joiner-1"]

            # 2. Code with spaces: 'BC - ALPHA1'
            res2 = client.post("/projects/join", json={"invite_code": "BC - ALPHA1"})
            assert res2.status_code == 200

            DEV_PROJECT_MEMBERS_DB[:] = [m for m in DEV_PROJECT_MEMBERS_DB if m.get("user_id") != "new-member-joiner-1"]

            # 3. Code with en-dash: 'BC–ALPHA1'
            res3 = client.post("/projects/join", json={"invite_code": "BC\u2013ALPHA1"})
            assert res3.status_code == 200

            DEV_PROJECT_MEMBERS_DB[:] = [m for m in DEV_PROJECT_MEMBERS_DB if m.get("user_id") != "new-member-joiner-1"]

            # 4. Code with em-dash: 'BC—ALPHA1'
            res4 = client.post("/projects/join", json={"invite_code": "BC\u2014ALPHA1"})
            assert res4.status_code == 200

            # 5. Invalid/non-existent code keeps generic 404
            res5 = client.post("/projects/join", json={"invite_code": "NONEXISTENT"})
            assert res5.status_code == 404
            assert res5.json()["detail"] == "Invalid invite code"

            res6 = client.post("/projects/join", json={"invite_code": "123456"})
            assert res6.status_code == 404
            assert res6.json()["detail"] == "Invalid invite code"

        finally:
            app.dependency_overrides.pop(get_current_user, None)
            DEV_PROJECTS_DB.pop(proj_id, None)
            DEV_PROJECT_INVITES_DB.pop(clean_code, None)
            DEV_PROJECT_MEMBERS_DB[:] = [m for m in DEV_PROJECT_MEMBERS_DB if m.get("user_id") != "new-member-joiner-1"]


class TestAccessLogAndGithubState:
    """Tests for requirements 2 and 5."""

    def test_access_log_includes_client_ip(self, caplog):
        client = TestClient(app)
        import logging
        with caplog.at_level(logging.INFO):
            res = client.get("/health", headers={"X-Real-IP": "198.51.100.42"})
            assert res.status_code == 200

        # Verify that access log contains the resolved client IP
        found_log = any("198.51.100.42 - GET /health" in rec.message for rec in caplog.records)
        assert found_log, f"Expected resolved IP in access log, records: {[r.message for r in caplog.records]}"

    def test_github_callback_does_not_log_raw_state(self, caplog):
        client = TestClient(app)
        import logging
        secret_state_token = "secret_raw_jwt_value_12345"

        with caplog.at_level(logging.INFO):
            # Call github callback endpoint with state
            res = client.get(
                f"/github/app/callback?state={secret_state_token}&installation_id=999"
            )

        # Raw state value MUST NOT appear in log records
        for rec in caplog.records:
            if "GitHub App Callback received" in rec.message:
                assert secret_state_token not in rec.message
                assert "state_present=True" in rec.message
