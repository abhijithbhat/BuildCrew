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
def clean_database():
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


def test_complete_end_to_end_mobile_collaboration_lifecycle():
    """
    Exhaustive integration test covering the entire BuildCrew user journey:
    - Health checking
    - Owner (User A) Auth (Signup, OTP, Login, Password validation)
    - Project Management (Create, List, Detail, Validation)
    - Invite generation and security checks
    - Teammate (User B) Auth and Onboarding
    - Project Joining (Valid code, Invalid code, Duplicate check)
    - Role-based permissions (Member vs Outsider access control)
    - Password Reset flow (Forgot password, Verify OTP, Reset Password)
    """

    # -------------------------------------------------------------
    # STEP 1: Backend Health Check
    # -------------------------------------------------------------
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    # -------------------------------------------------------------
    # STEP 2: User A (Project Owner) Auth (Signup, OTP, Login)
    # -------------------------------------------------------------
    owner_email = "owner@buildcrew.io"
    user_a = MagicMock(id="user-owner-001", email=owner_email)

    # 2a: Mock Signup
    mock_sub = MagicMock()
    mock_resp = MagicMock()
    mock_resp.user = user_a
    mock_resp.user.identities = [MagicMock()]
    mock_sub.auth.sign_up.return_value = mock_resp

    with patch("routers.auth.get_supabase_pub_client", return_value=mock_sub):
        signup_a = client.post("/auth/signup", json={"email": owner_email, "password": "OwnerPassword123!"})
        assert signup_a.status_code == 201
        assert "Verification code sent to your email" in signup_a.json()["message"]

    # 2b: Mock OTP verification
    mock_otp_sub = MagicMock()
    mock_otp_sub.auth.verify_otp.return_value = MagicMock(
        session=MagicMock(access_token="token-a-jwt", refresh_token="refresh-a-jwt"),
        user=user_a,
    )
    with patch("routers.auth.get_supabase_pub_client", return_value=mock_otp_sub):
        otp_a = client.post("/auth/verify-otp", json={"email": owner_email, "token": "123456"})
        assert otp_a.status_code == 200
        assert otp_a.json()["access_token"] == "token-a-jwt"

    # 2c: Mock Login
    mock_login_sub = MagicMock()
    mock_session = MagicMock()
    mock_session.access_token = "token-a-jwt"
    mock_session.refresh_token = "refresh-a-jwt"
    mock_login_sub.auth.sign_in_with_password.return_value = MagicMock(
        session=mock_session,
        user=user_a,
    )
    with patch("routers.auth.get_supabase_client", return_value=mock_login_sub):
        login_a = client.post("/auth/login", json={"email": owner_email, "password": "OwnerPassword123!"})
        assert login_a.status_code == 200
        assert login_a.json()["access_token"] == "token-a-jwt"

    # -------------------------------------------------------------
    # STEP 3: User A Project Management & Validation
    # -------------------------------------------------------------
    app.dependency_overrides[get_current_user] = lambda: user_a

    # 3a: Empty project list initially
    list_initial = client.get("/projects", headers={"Authorization": "Bearer token-a-jwt"})
    assert list_initial.status_code == 200
    assert list_initial.json()["projects"] == []

    # 3b: Validation error on empty name
    create_invalid = client.post(
        "/projects",
        json={"name": "   ", "description": "Test description"},
        headers={"Authorization": "Bearer token-a-jwt"},
    )
    assert create_invalid.status_code == 422
    assert "Project name cannot be empty" in create_invalid.json()["detail"]

    # 3c: Valid project creation
    project_payload = {
        "name": "BuildCrew Mobile Platform",
        "description": "Cross-platform mobile workspace for developers"
    }
    create_a = client.post(
        "/projects",
        json=project_payload,
        headers={"Authorization": "Bearer token-a-jwt"},
    )
    assert create_a.status_code == 201 or create_a.status_code == 200
    create_data = create_a.json()
    project_data = create_data.get("project", create_data)
    project_id = project_data["id"]
    assert project_data["name"] == project_payload["name"]

    # 3d: List projects -> has 1 project as owner
    list_a = client.get("/projects", headers={"Authorization": "Bearer token-a-jwt"})
    assert list_a.status_code == 200
    projects_a = list_a.json()["projects"]
    assert len(projects_a) == 1
    assert projects_a[0]["id"] == project_id
    assert projects_a[0]["role"] == "owner"

    # 3e: Get single project detail
    detail_a = client.get(f"/projects/{project_id}", headers={"Authorization": "Bearer token-a-jwt"})
    assert detail_a.status_code == 200
    assert detail_a.json()["project"]["name"] == project_payload["name"]

    # -------------------------------------------------------------
    # STEP 4: Invite Code Generation
    # -------------------------------------------------------------
    invite_resp = client.post(f"/projects/{project_id}/invite", headers={"Authorization": "Bearer token-a-jwt"})
    assert invite_resp.status_code == 200
    invite_data = invite_resp.json()
    invite_code = invite_data["invite_code"]
    assert invite_code.startswith("BC-")
    assert "invite_url" in invite_data
    assert "expires_at" in invite_data

    # Retrieve existing invite
    get_invite = client.get(f"/projects/{project_id}/invite", headers={"Authorization": "Bearer token-a-jwt"})
    assert get_invite.status_code == 200
    assert get_invite.json()["invite_code"] == invite_code

    # -------------------------------------------------------------
    # STEP 5: User B (Teammate) Joining Project
    # -------------------------------------------------------------
    user_b = MagicMock(id="user-member-002", email="member@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: user_b

    # B has no projects initially
    list_b_initial = client.get("/projects", headers={"Authorization": "Bearer token-b-jwt"})
    assert list_b_initial.status_code == 200
    assert list_b_initial.json()["projects"] == []

    # B tries to join with non-existent invite code -> 404
    join_bad = client.post(
        "/projects/join",
        json={"invite_code": "BC-INVALID"},
        headers={"Authorization": "Bearer token-b-jwt"},
    )
    assert join_bad.status_code == 404

    # B joins with valid invite code
    join_b = client.post(
        "/projects/join",
        json={"invite_code": invite_code},
        headers={"Authorization": "Bearer token-b-jwt"},
    )
    assert join_b.status_code == 200
    join_data = join_b.json()
    joined_project = join_data.get("project", join_data)
    assert joined_project["id"] == project_id

    # B lists projects -> sees 1 project with role 'member'
    list_b = client.get("/projects", headers={"Authorization": "Bearer token-b-jwt"})
    assert list_b.status_code == 200
    projects_b = list_b.json()["projects"]
    assert len(projects_b) == 1
    assert projects_b[0]["id"] == project_id
    assert projects_b[0]["role"] == "member"

    # Duplicate Join check: B tries to join again -> 409 Conflict
    join_duplicate = client.post(
        "/projects/join",
        json={"invite_code": invite_code},
        headers={"Authorization": "Bearer token-b-jwt"},
    )
    assert join_duplicate.status_code == 409
    assert "already a member" in join_duplicate.json()["detail"]

    # -------------------------------------------------------------
    # STEP 6: Security & Role Permissions Check
    # -------------------------------------------------------------
    # Outsider C (not member of project) attempts to generate invite -> 403 Forbidden
    user_c = MagicMock(id="user-outsider-003", email="outsider@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: user_c

    invite_forbidden = client.post(f"/projects/{project_id}/invite", headers={"Authorization": "Bearer token-c-jwt"})
    assert invite_forbidden.status_code == 403
    assert "must be a member" in invite_forbidden.json()["detail"]

    # -------------------------------------------------------------
    # STEP 7: Password Reset Flow (Forgot Password Wizard)
    # -------------------------------------------------------------
    mock_reset_sub = MagicMock()
    mock_reset_sub.auth.reset_password_email.return_value = None
    mock_reset_sub.auth.verify_otp.return_value = MagicMock(
        session=MagicMock(access_token="temp-token"),
        user=user_a,
    )
    mock_reset_sub.auth.update_user.return_value = MagicMock(user=user_a)

    with patch("routers.auth.get_supabase_client", return_value=mock_reset_sub), \
         patch("routers.auth.get_supabase_pub_client", return_value=mock_reset_sub):
        
        # Step 7a: Request password reset OTP
        forgot_req = client.post("/auth/forgot-password", json={"email": owner_email})
        assert forgot_req.status_code == 200
        assert "Password reset" in forgot_req.json()["message"]


        # Step 7b: Reset password with valid OTP
        reset_ok = client.post("/auth/reset-password", json={
            "email": owner_email,
            "token": "123456",
            "new_password": "NewOwnerPassword123!"
        })
        assert reset_ok.status_code == 200
        assert "Password reset successfully" in reset_ok.json()["message"]

    # -------------------------------------------------------------
    # STEP 8: Phase 7 Role Agreement Collaboration Lifecycle
    # -------------------------------------------------------------
    # 8a: User A (Owner) declares role
    app.dependency_overrides[get_current_user] = lambda: user_a
    role_a_resp = client.post(
        f"/projects/{project_id}/role",
        json={
            "declared_role": "Lead Systems Architect",
            "responsibilities": "Oversee system architecture, database schema, and backend APIs.",
            "deadline": "2026-12-01T00:00:00Z"
        },
        headers={"Authorization": "Bearer token-a-jwt"}
    )
    assert role_a_resp.status_code == 200
    assert role_a_resp.json()["role_agreement"]["declared_role"] == "Lead Systems Architect"
    assert role_a_resp.json()["role_agreement"]["user_id"] == "user-owner-001"

    # 8b: User B (Teammate) declares role
    app.dependency_overrides[get_current_user] = lambda: user_b
    role_b_resp = client.post(
        f"/projects/{project_id}/role",
        json={
            "declared_role": "Lead Flutter Engineer",
            "responsibilities": "Build and test cross-platform mobile client components and screens.",
            "deadline": "2026-11-25T00:00:00Z"
        },
        headers={"Authorization": "Bearer token-b-jwt"}
    )
    assert role_b_resp.status_code == 200
    assert role_b_resp.json()["role_agreement"]["declared_role"] == "Lead Flutter Engineer"
    assert role_b_resp.json()["role_agreement"]["user_id"] == "user-member-002"

    # 8c: User B lists all roles for project -> sees both User A and User B roles
    roles_list_b = client.get(
        f"/projects/{project_id}/roles",
        headers={"Authorization": "Bearer token-b-jwt"}
    )
    assert roles_list_b.status_code == 200
    roles = roles_list_b.json()["roles"]
    assert len(roles) == 2
    role_titles = {r["declared_role"] for r in roles}
    assert "Lead Systems Architect" in role_titles
    assert "Lead Flutter Engineer" in role_titles

    # 8d: User A updates existing role
    app.dependency_overrides[get_current_user] = lambda: user_a
    role_a_update = client.post(
        f"/projects/{project_id}/role",
        json={
            "declared_role": "Principal Systems Architect",
            "responsibilities": "Lead cloud deployments and backend microservices."
        },
        headers={"Authorization": "Bearer token-a-jwt"}
    )
    assert role_a_update.status_code == 200
    assert role_a_update.json()["role_agreement"]["declared_role"] == "Principal Systems Architect"

    # Verify total count is still 2 (upserted, not duplicated)
    roles_list_a = client.get(
        f"/projects/{project_id}/roles",
        headers={"Authorization": "Bearer token-a-jwt"}
    )
    assert roles_list_a.status_code == 200
    assert len(roles_list_a.json()["roles"]) == 2

    # 8e: Outsider C tries to declare/list roles -> 403 Forbidden
    app.dependency_overrides[get_current_user] = lambda: user_c
    role_c_forbidden = client.post(
        f"/projects/{project_id}/role",
        json={"declared_role": "Hacker"},
        headers={"Authorization": "Bearer token-c-jwt"}
    )
    assert role_c_forbidden.status_code == 403

    roles_c_forbidden = client.get(
        f"/projects/{project_id}/roles",
        headers={"Authorization": "Bearer token-c-jwt"}
    )
    assert roles_c_forbidden.status_code == 403


