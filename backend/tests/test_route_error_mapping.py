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

    def test_postgrest_status_codes(self):
        err_503 = APIError({"message": "Service unavailable", "code": "503", "details": None})
        exc1 = handle_route_error(err_503, generic_message="Failed to query database.")
        assert exc1.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc1.detail == "Service temporarily unavailable. Please try again."
        assert exc1.headers.get("Retry-After") == "5"

        err_502 = APIError({"message": "Bad gateway", "code": "502", "details": None})
        exc2 = handle_route_error(err_502, generic_message="Failed to query database.")
        assert exc2.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc2.headers.get("Retry-After") == "5"

        err_504 = APIError({"message": "Gateway timeout", "code": "504", "details": None})
        exc3 = handle_route_error(err_504, generic_message="Failed to query database.")
        assert exc3.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc3.headers.get("Retry-After") == "5"

        err_500 = APIError({"message": "Internal postgrest server error", "code": "500", "details": None})
        exc4 = handle_route_error(err_500, generic_message="Failed to query database.")
        assert exc4.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc4.detail == "Failed to query database."

    def test_postgrest_error_code_mapping(self):
        # PGRST116 (0 rows) -> 404 'Not found'
        err_pgrst116 = APIError({"code": "PGRST116", "message": "JSON object requested, multiple (or no) rows returned"})
        res116 = handle_route_error(err_pgrst116, generic_message="Failed to fetch item.")
        assert res116.status_code == status.HTTP_404_NOT_FOUND
        assert res116.detail == "Not found"

        # 22P02 (invalid uuid) -> 404 'Not found'
        err_22p02 = APIError({"code": "22P02", "message": "invalid input syntax for type uuid: 'bad-id'"})
        res22p02 = handle_route_error(err_22p02, generic_message="Failed to fetch item.")
        assert res22p02.status_code == status.HTTP_404_NOT_FOUND
        assert res22p02.detail == "Not found"

        # 23505 (unique constraint violation) -> 409 'Conflict'
        err_23505 = APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
        res23505 = handle_route_error(err_23505, generic_message="Failed to insert item.")
        assert res23505.status_code == status.HTTP_409_CONFLICT
        assert res23505.detail == "Conflict"

        # 23503 (foreign key constraint violation) -> 409 'Conflict'
        err_23503 = APIError({"code": "23503", "message": "violates foreign key constraint"})
        res23503 = handle_route_error(err_23503, generic_message="Failed to insert item.")
        assert res23503.status_code == status.HTTP_409_CONFLICT
        assert res23503.detail == "Conflict"

        # 42501 (permission denied / RLS) -> 500 generic (logged)
        err_42501 = APIError({"code": "42501", "message": "permission denied for table projects"})
        res42501 = handle_route_error(err_42501, generic_message="Database operation failed.")
        assert res42501.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert res42501.detail == "Database operation failed."

        # PGRST3xx -> 500 generic (logged)
        err_pgrst301 = APIError({"code": "PGRST301", "message": "JWT expired"})
        res301 = handle_route_error(err_pgrst301, generic_message="Database operation failed.")
        assert res301.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert res301.detail == "Database operation failed."

    def test_uuid_containing_502_or_503_does_not_become_503(self):
        # A UUID containing '502' or '503' must not trigger the 502/503 upstream gateway pattern
        exc_uuid_502 = RuntimeError("Failed to query project with id f502c81e-1234-4000-8000-000000000000")
        res1 = handle_route_error(exc_uuid_502, generic_message="Failed to fetch project.")
        assert res1.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert res1.detail == "Failed to fetch project."

        exc_uuid_503 = RuntimeError("Failed to query contribution 12345678-0503-4000-8000-000000000000")
        res2 = handle_route_error(exc_uuid_503, generic_message="Failed to fetch contribution.")
        assert res2.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert res2.detail == "Failed to fetch contribution."

        exc_uuid_both = Exception("Error in entity 11111502-0000-0000-0000-000000000503")
        res3 = handle_route_error(exc_uuid_both, generic_message="Failed to update record.")
        assert res3.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert res3.detail == "Failed to update record."

    def test_timeout_and_gateway_heuristic_strings(self):
        test_cases = [
            RuntimeError("Request to backend timed out"),
            RuntimeError("Connection timeout after 10000ms"),
            RuntimeError("502 Bad Gateway from upstream CDN"),
            RuntimeError("Upstream returned 503 Service Unavailable"),
            Exception("Host gateway returned 502 error"),
            Exception("failed to connect to postgres: connection refused"),
            Exception("cannot connect to server"),
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


class TestRoutePGRST116AndTransportErrorMapping:
    """Tests for Requirement 5: PGRST116 -> 404 on passport route, GET /projects/{id}/contributions, and confirm."""

    def test_passport_route_pgrst116_returns_404_branded_html(self):
        client = TestClient(app)
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "JSON object requested, multiple (or no) rows returned"}
        )

        with patch("core.database.is_dev_mode", return_value=False), \
             patch("routers.contributions.is_dev_mode", return_value=False), \
             patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
            response = client.get(
                "/passport/user-uuid-1/proj-uuid-1",
                headers={"Accept": "text/html"},
            )
            assert response.status_code == 404
            assert "text/html" in response.headers.get("content-type", "")
            assert "Passport not found" in response.text

    def test_passport_route_pgrst116_returns_404_json(self):
        client = TestClient(app)
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "0 rows"}
        )

        with patch("core.database.is_dev_mode", return_value=False), \
             patch("routers.contributions.is_dev_mode", return_value=False), \
             patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
            response = client.get(
                "/passport/user-uuid-1/proj-uuid-1?format=json",
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Not found"

    def test_passport_route_uuid_with_502_503_does_not_become_503(self):
        client = TestClient(app)
        uuid_with_502_503 = "f502c81e-0503-4000-8000-000000000000"
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": f"Project {uuid_with_502_503} not found"}
        )

        with patch("core.database.is_dev_mode", return_value=False), \
             patch("routers.contributions.is_dev_mode", return_value=False), \
             patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
            response = client.get(
                f"/passport/user-1/{uuid_with_502_503}?format=json",
            )
            assert response.status_code == 404
            assert response.status_code != 503

    def test_passport_route_transport_error_returns_503(self):
        client = TestClient(app)
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = httpx.ConnectTimeout(
            "Connection timed out"
        )

        with patch("core.database.is_dev_mode", return_value=False), \
             patch("routers.contributions.is_dev_mode", return_value=False), \
             patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
            response = client.get(
                "/passport/user-1/proj-1",
                headers={"Accept": "text/html"},
            )
            assert response.status_code == 503
            assert "Temporarily unavailable" in response.text

    def test_get_project_contributions_pgrst116_returns_404(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "user-test-caller-1"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "0 rows"}
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.projects.is_dev_mode", return_value=False), \
                 patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.get("/projects/nonexistent-proj-id/contributions")
                assert response.status_code == 404
                assert response.json()["detail"] == "Not found"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_get_project_contributions_uuid_with_502_503_does_not_become_503(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "user-test-caller-2"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        uuid_502_503 = "f502c81e-0503-4000-8000-000000000000"
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": f"Project {uuid_502_503} not found"}
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.projects.is_dev_mode", return_value=False), \
                 patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.get(f"/projects/{uuid_502_503}/contributions")
                assert response.status_code == 404
                assert response.status_code != 503
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_get_project_contributions_timeout_returns_503_with_retry_after(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "user-test-caller-3"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = httpx.ConnectTimeout(
            "Connection timed out while querying project"
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.projects.is_dev_mode", return_value=False), \
                 patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.get("/projects/some-proj-id/contributions")
                assert response.status_code == 503
                assert response.headers.get("retry-after") == "5"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_confirm_contribution_pgrst116_returns_404(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "reviewer-uuid-1"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "Results contain 0 rows"}
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.contributions.is_dev_mode", return_value=False), \
                 patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
                response = client.post("/contributions/nonexistent-contrib-uuid/confirm")
                assert response.status_code == 404
                assert response.json()["detail"] == "Not found"
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_confirm_contribution_uuid_with_502_503_does_not_become_503(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "reviewer-uuid-2"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        uuid_502_503 = "c502c81e-0503-4000-8000-000000000000"
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": f"Contribution {uuid_502_503} not found"}
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.contributions.is_dev_mode", return_value=False), \
                 patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
                response = client.post(f"/contributions/{uuid_502_503}/confirm")
                assert response.status_code == 404
                assert response.status_code != 503
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_confirm_contribution_timeout_returns_503_with_retry_after(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "reviewer-uuid-3"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.side_effect = httpx.ConnectTimeout(
            "Connection timeout to supabase"
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.contributions.is_dev_mode", return_value=False), \
                 patch("routers.contributions.get_supabase_client", return_value=mock_supabase):
                response = client.post("/contributions/some-contrib-uuid/confirm")
                assert response.status_code == 503
                assert response.headers.get("retry-after") == "5"
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestIsProjectArchivedAndDeletion:
    """Tests for Requirement 4: is_project_archived raises 503 on lookup error in prod, delete error renamed."""

    def test_is_project_archived_lookup_error_raises_503_in_production(self):
        from routers.projects import is_project_archived
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = RuntimeError(
            "Database connection failed"
        )

        with patch("routers.projects.is_dev_mode", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                is_project_archived("proj-arch-err-test", mock_supabase)
            assert exc_info.value.status_code == 503
            assert exc_info.value.headers.get("Retry-After") == "5"

    def test_is_project_archived_pgrst116_returns_false(self):
        from routers.projects import is_project_archived
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = APIError(
            {"code": "PGRST116", "message": "0 rows"}
        )

        with patch("routers.projects.is_dev_mode", return_value=False):
            res = is_project_archived("proj-not-found", mock_supabase)
            assert res is False

    def test_delete_project_renamed_error_text(self):
        client = TestClient(app)
        mock_user = MagicMock()
        mock_user.id = "lead-user-123"

        from core.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        mock_supabase = MagicMock()
        mock_proj_res = MagicMock()
        mock_proj_res.data = {"id": "proj-to-delete-fail", "created_by": "lead-user-123"}
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_proj_res

        mock_members_res = MagicMock()
        mock_members_res.data = []
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_members_res

        # Deletion step fails
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.side_effect = RuntimeError(
            "Unexpected internal failure during delete"
        )

        try:
            with patch("core.database.is_dev_mode", return_value=False), \
                 patch("routers.projects.is_dev_mode", return_value=False), \
                 patch("routers.projects.get_supabase_client", return_value=mock_supabase):
                response = client.delete("/projects/proj-to-delete-fail")
                assert response.status_code == 500
                assert response.json()["detail"] == "Failed to remove project. Please try again."
        finally:
            app.dependency_overrides.pop(get_current_user, None)

