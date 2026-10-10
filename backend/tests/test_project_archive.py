import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.auth import get_current_user
from routers.contributions import (
    DEV_CONFIRMATION_REQUESTS_DB,
    DEV_CONTRIBUTIONS_DB,
)
from routers.projects import (
    DEV_PROJECT_INVITES_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_PROJECTS_DB,
    DEV_ROLE_AGREEMENTS_DB,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_dev_dbs():
    """Clean all in-memory mock databases before and after tests."""
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()
    yield
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_ROLE_AGREEMENTS_DB.clear()
    DEV_PROJECT_INVITES_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()


def test_solo_delete_removes_rows_local_dev():
    """Solo project delete permanently removes all rows (hard delete)."""
    lead_id = "user-lead-solo"
    proj_id = "proj-solo-1"
    now_iso = datetime.now(timezone.utc).isoformat()

    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Solo Project",
        "description": "Only lead exists",
        "created_by": lead_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": proj_id,
        "user_id": lead_id,
        "role": "owner",
        "joined_at": now_iso,
    })

    mock_user = MagicMock(id=lead_id, email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client") as mock_supa:
        mock_supa.side_effect = Exception("PGRST301 connection refused")
        resp = client.delete(f"/projects/{proj_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("archived") is False
        assert "dismantled" in data.get("message", "").lower()

    # Verify rows removed
    assert proj_id not in DEV_PROJECTS_DB
    assert not any(m.get("project_id") == proj_id for m in DEV_PROJECT_MEMBERS_DB)


def test_solo_delete_removes_rows_supabase():
    """Solo project delete in Supabase calls delete() cascade and returns archived: false."""
    lead_id = "user-lead-solo-supa"
    proj_id = "proj-solo-supa-1"
    now_iso = datetime.now(timezone.utc).isoformat()

    mock_supabase = MagicMock()
    mock_proj_table = MagicMock()
    mock_proj_select = MagicMock()
    mock_proj_select.single.return_value.execute.return_value = MagicMock(
        data={
            "id": proj_id,
            "name": "Supabase Solo Proj",
            "created_by": lead_id,
            "created_at": now_iso,
        }
    )
    mock_proj_table.select.return_value.eq.return_value = mock_proj_select
    mock_proj_table.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_members_table = MagicMock()
    # Only lead member exists
    mock_members_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"user_id": lead_id, "project_id": proj_id}]
    )

    def table_side_effect(name):
        if name == "projects":
            return mock_proj_table
        if name == "project_members":
            return mock_members_table
        return MagicMock()

    mock_supabase.table.side_effect = table_side_effect

    mock_user = MagicMock(id=lead_id, email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client", return_value=mock_supabase):
        resp = client.delete(f"/projects/{proj_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("archived") is False
        # Verify hard delete was executed on projects table
        mock_proj_table.delete.assert_called_once()


def test_shared_delete_archives_and_preserves_rows():
    """Shared project delete sets archived_at=now(), returns archived: true, and preserves rows."""
    lead_id = "user-lead-shared"
    teammate_id = "user-mate-shared"
    proj_id = "proj-shared-1"
    now_iso = datetime.now(timezone.utc).isoformat()

    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Team Collab Project",
        "description": "Collaborative project with multiple members",
        "created_by": lead_id,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"project_id": proj_id, "user_id": lead_id, "role": "owner", "joined_at": now_iso},
        {"project_id": proj_id, "user_id": teammate_id, "role": "member", "joined_at": now_iso},
    ])

    mock_user = MagicMock(id=lead_id, email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client") as mock_supa:
        mock_supa.side_effect = Exception("PGRST301 connection refused")
        resp = client.delete(f"/projects/{proj_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("archived") is True
        assert "archived" in data.get("message", "").lower()

    # Project MUST still exist in database and have archived_at set
    assert proj_id in DEV_PROJECTS_DB
    assert DEV_PROJECTS_DB[proj_id].get("archived_at") is not None
    # Teammate members preserved
    assert any(m.get("user_id") == teammate_id for m in DEV_PROJECT_MEMBERS_DB)


def test_archived_project_hidden_from_default_list_included_with_query_param():
    """Default GET /projects excludes archived; include_archived=true includes them."""
    lead_id = "user-lead-list"
    proj_active = "proj-active-10"
    proj_archived = "proj-archived-10"
    now_iso = datetime.now(timezone.utc).isoformat()

    DEV_PROJECTS_DB[proj_active] = {
        "id": proj_active,
        "name": "Active Project",
        "created_by": lead_id,
        "created_at": now_iso,
    }
    DEV_PROJECTS_DB[proj_archived] = {
        "id": proj_archived,
        "name": "Archived Project",
        "created_by": lead_id,
        "created_at": now_iso,
        "archived_at": now_iso,
    }

    mock_user = MagicMock(id=lead_id, email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client") as mock_supa:
        mock_supa.side_effect = Exception("PGRST301 connection refused")

        # 1. Default GET /projects
        resp = client.get("/projects")
        assert resp.status_code == 200
        p_ids = [p["id"] for p in resp.json().get("projects", [])]
        assert proj_active in p_ids
        assert proj_archived not in p_ids

        # 2. GET /projects?include_archived=true
        resp_inc = client.get("/projects?include_archived=true")
        assert resp_inc.status_code == 200
        p_ids_inc = [p["id"] for p in resp_inc.json().get("projects", [])]
        assert proj_active in p_ids_inc
        assert proj_archived in p_ids_inc


def test_archived_project_read_only_protection_409():
    """All mutating actions on archived project return HTTP 409 Conflict."""
    lead_id = "user-lead-protect"
    proj_id = "proj-archived-protect"
    now_iso = datetime.now(timezone.utc).isoformat()

    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Protected Archived Project",
        "created_by": lead_id,
        "created_at": now_iso,
        "archived_at": now_iso,
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": proj_id,
        "user_id": lead_id,
        "role": "owner",
        "joined_at": now_iso,
    })

    mock_user = MagicMock(id=lead_id, email="lead@example.com")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("routers.projects.get_supabase_client") as mock_supa, \
         patch("routers.contributions.get_supabase_client") as mock_cont_supa, \
         patch("routers.github.get_supabase_client") as mock_gh_supa:
        mock_supa.side_effect = Exception("PGRST301")
        mock_cont_supa.side_effect = Exception("PGRST301")
        mock_gh_supa.side_effect = Exception("PGRST301")

        # 1. Manual contribution -> 409
        r1 = client.post(
            "/contributions",
            json={
                "project_id": proj_id,
                "title": "New feature post archive",
                "category": "design",
                "evidence_description": "Mock work",
            },
        )
        assert r1.status_code == 409
        assert "archived" in r1.json()["detail"].lower()

        # 2. Upload evidence -> 409
        r2 = client.post(
            f"/contributions/upload-evidence?project_id={proj_id}",
            files={"file": ("test.png", b"filecontent", "image/png")},
        )
        assert r2.status_code == 409
        assert "archived" in r2.json()["detail"].lower()

        # 3. Generate invite -> 409
        r3 = client.post(f"/projects/{proj_id}/invite")
        assert r3.status_code == 409
        assert "archived" in r3.json()["detail"].lower()

        # 4. Declare role -> 409
        r4 = client.post(
            f"/projects/{proj_id}/role",
            json={"declared_role": "Backend Engineer"},
        )
        assert r4.status_code == 409
        assert "archived" in r4.json()["detail"].lower()

        # 5. GitHub changes -> 409
        r5_url = client.get(f"/projects/{proj_id}/github/install-url")
        assert r5_url.status_code == 409
        assert "archived" in r5_url.json()["detail"].lower()

        r5 = client.post(f"/projects/{proj_id}/github/install", json={})
        assert r5.status_code == 409
        assert "archived" in r5.json()["detail"].lower()


def test_passport_keeps_rendering_with_project_archived_header():
    """Passports of archived projects keep rendering with 'Project archived' in header."""
    lead_id = "user-lead-pass"
    proj_id = "proj-passport-archived"
    contrib_id = "contrib-pass-1"
    now_iso = datetime.now(timezone.utc).isoformat()

    DEV_PROJECTS_DB[proj_id] = {
        "id": proj_id,
        "name": "Archived Moonshot",
        "description": "Historic project that was archived",
        "created_by": lead_id,
        "created_at": now_iso,
        "archived_at": now_iso,
    }
    DEV_PROJECT_MEMBERS_DB.append({
        "project_id": proj_id,
        "user_id": lead_id,
        "role": "owner",
        "joined_at": now_iso,
    })
    DEV_CONTRIBUTIONS_DB.append({
        "id": contrib_id,
        "project_id": proj_id,
        "project": proj_id,
        "author_id": lead_id,
        "contributor": lead_id,
        "contributor_id": lead_id,
        "title": "Architecture Blueprint",
        "category": "design",
        "status": "confirmed",
        "verification_status": "confirmed",
        "visibility": "public",
        "selected_for_passport": True,
        "created_at": now_iso,
    })

    with patch("routers.contributions.get_supabase_client") as mock_supa, \
         patch("routers.projects.get_supabase_client") as mock_proj_supa:
        mock_supa.side_effect = Exception("PGRST301")
        mock_proj_supa.side_effect = Exception("PGRST301")

        # 1. Test JSON passport data via public passport endpoint
        r_json = client.get(f"/passport/{lead_id}/{proj_id}?format=json")
        assert r_json.status_code == 200
        pdata = r_json.json()
        assert pdata.get("is_archived") is True
        assert pdata.get("archived_at") is not None
        assert pdata.get("project_name") == "Archived Moonshot"
        assert len(pdata.get("contributions", [])) >= 1

        # 2. Test HTML passport page rendering
        r_html = client.get(f"/passport/{lead_id}/{proj_id}")
        assert r_html.status_code == 200
        assert "text/html" in r_html.headers.get("content-type", "")
        html = r_html.text
        assert "Project archived" in html
        assert "Archived Moonshot" in html
        assert "Architecture Blueprint" in html
