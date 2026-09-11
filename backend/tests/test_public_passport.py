import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app
from routers.projects import (
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_ROLE_AGREEMENTS_DB,
    DEV_CONTRIBUTIONS_DB,
)
from routers.auth import DEV_USER_NAMES_DB

client = TestClient(app)


def test_public_passport_endpoint_requires_no_authentication():
    """Verify /passport/{user_id}/{project_id} requires NO auth headers and returns 200."""
    user_id = "user-public-auth-test"
    project_id = "proj-public-auth-test"

    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Open Source Kernel",
        "created_by": user_id,
    }

    # Query without ANY Authorization header
    resp = client.get(f"/passport/{user_id}/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["project_id"] == project_id
    assert data["project_name"] == "Open Source Kernel"
    assert data["role"] == "Team Lead"
    assert data["total_contributions"] == 0
    assert data["contributions"] == []


def test_public_passport_returns_only_published_contributions_and_excludes_private_or_disputed():
    """
    Guarantees that /passport/{user_id}/{project_id}:
    1. Returns published (visibility='public') & confirmed items.
    2. Excludes private (visibility='private') items.
    3. Excludes unconfirmed (verification_status='self-declared') items.
    4. Excludes disputed (verification_status='needs-review' or dispute_state='disputed') items.
    5. Excludes items from other projects or other users.
    """
    author_id = "user-passport-author-1"
    peer_id = "user-passport-peer-1"
    other_user_id = "user-passport-other"
    project_id = "proj-passport-showcase"
    other_project_id = "proj-passport-other"

    DEV_USER_NAMES_DB[author_id] = "Alex Morgan"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Cloud Native Orchestrator",
        "created_by": author_id,
    }
    DEV_ROLE_AGREEMENTS_DB.append({
        "project_id": project_id,
        "user_id": author_id,
        "role_name": "Lead Cloud Architect",
        "category": "architecture",
    })

    # 1. Item 1: Published & Confirmed (MUST BE INCLUDED)
    item_published_confirmed = {
        "id": "c-pub-conf-1",
        "contributor": author_id,
        "project": project_id,
        "title": "Kubernetes Custom Controller Engine",
        "category": "code",
        "description": "Implemented zero-downtime reconcile loop with leader election",
        "verification_status": "peer-confirmed",
        "confirmed_by": peer_id,
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:00:00Z",
    }

    # 2. Item 2: Private & Confirmed (MUST BE EXCLUDED)
    item_private_confirmed = {
        "id": "c-priv-conf-2",
        "contributor": author_id,
        "project": project_id,
        "title": "Internal Infrastructure Cost Audit",
        "category": "documentation",
        "description": "Confidential budget analysis for AWS clusters",
        "verification_status": "peer-confirmed",
        "confirmed_by": peer_id,
        "visibility": "private",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:05:00Z",
    }

    # 3. Item 3: Public but Unconfirmed / Self-declared (MUST BE EXCLUDED)
    item_public_unconfirmed = {
        "id": "c-pub-unconf-3",
        "contributor": author_id,
        "project": project_id,
        "title": "Unreviewed Terraform Scripts",
        "category": "devops",
        "description": "Initial draft scripts awaiting review",
        "verification_status": "self-declared",
        "confirmed_by": None,
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:10:00Z",
    }

    # 4. Item 4: Disputed / Needs Review (MUST BE EXCLUDED)
    item_disputed = {
        "id": "c-disputed-4",
        "contributor": author_id,
        "project": project_id,
        "title": "Disputed Benchmark Results",
        "category": "testing",
        "description": "Questioned performance benchmark figures",
        "verification_status": "needs-review",
        "confirmed_by": None,
        "visibility": "public",
        "dispute_state": "disputed",
        "created_at": "2026-09-10T12:15:00Z",
    }

    # 5. Item 5: Other user's confirmed contribution in same project (MUST BE EXCLUDED)
    item_other_user = {
        "id": "c-other-user-5",
        "contributor": other_user_id,
        "project": project_id,
        "title": "Teammate Figma Design Mockups",
        "category": "design",
        "description": "Figma mockups done by peer",
        "verification_status": "peer-confirmed",
        "confirmed_by": author_id,
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:20:00Z",
    }

    # 6. Item 6: Same author's confirmed contribution in a DIFFERENT project (MUST BE EXCLUDED)
    item_other_project = {
        "id": "c-other-proj-6",
        "contributor": author_id,
        "project": other_project_id,
        "title": "Different Project Core API",
        "category": "code",
        "description": "Work from another project",
        "verification_status": "peer-confirmed",
        "confirmed_by": peer_id,
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:25:00Z",
    }

    DEV_CONTRIBUTIONS_DB.extend([
        item_published_confirmed,
        item_private_confirmed,
        item_public_unconfirmed,
        item_disputed,
        item_other_user,
        item_other_project,
    ])

    # Query public endpoint without login
    resp = client.get(f"/passport/{author_id}/{project_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["user_id"] == author_id
    assert data["project_id"] == project_id
    assert data["project_name"] == "Cloud Native Orchestrator"
    assert data["role"] == "Lead Cloud Architect"
    assert data["display_name"] == "Alex Morgan"

    # Only 1 item must be returned!
    assert data["total_contributions"] == 1
    assert data["confirmed_count"] == 1
    assert len(data["contributions"]) == 1

    returned_id = data["contributions"][0]["id"]
    assert returned_id == "c-pub-conf-1"
    assert data["contributions"][0]["title"] == "Kubernetes Custom Controller Engine"
    assert data["contributions"][0]["visibility"] == "public"

    # Test trailing slash variant
    slash_resp = client.get(f"/passport/{author_id}/{project_id}/")
    assert slash_resp.status_code == 200
    assert slash_resp.json()["total_contributions"] == 1


def test_public_passport_renders_jinja2_html_template_when_accept_html():
    """Verify /passport/{user_id}/{project_id} renders passport.html when Accept: text/html is requested."""
    user_id = "user-html-test"
    project_id = "proj-html-test"

    DEV_USER_NAMES_DB[user_id] = "Sarah Chen"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Distributed Transaction Engine",
        "created_by": user_id,
    }
    DEV_ROLE_AGREEMENTS_DB.append({
        "project_id": project_id,
        "user_id": user_id,
        "role_name": "Principal Systems Engineer",
        "category": "code",
    })

    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-html-1",
        "contributor": user_id,
        "project": project_id,
        "title": "Two-Phase Commit Consensus Algorithm",
        "category": "architecture",
        "description": "Implemented Raft-based distributed commit protocol",
        "verification_status": "peer-confirmed",
        "confirmed_by": "peer-1",
        "visibility": "public",
        "evidence_link": "https://github.com/buildcrew/consensus/pull/42",
        "dispute_state": "none",
        "created_at": "2026-09-10T14:00:00Z",
        "updated_at": "2026-09-10T14:00:00Z",
    })

    resp = client.get(
        f"/passport/{user_id}/{project_id}",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml"},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    html = resp.text

    # Assert name, role, project name, badges, evidence link
    assert "Sarah Chen" in html
    assert "Principal Systems Engineer" in html
    assert "Distributed Transaction Engine" in html
    assert "Two-Phase Commit Consensus Algorithm" in html
    assert "Implemented Raft-based distributed commit protocol" in html
    assert "Peer Confirmed" in html
    assert "https://github.com/buildcrew/consensus/pull/42" in html

    # Assert CSS styling is included
    assert "<style>" in html
    assert ".passport-container" in html
    assert ".badge-peer-confirmed" in html
    assert "@media (max-width: 640px)" in html

    # Assert Open Graph and Social Preview meta tags
    assert '<meta property="og:type" content="profile">' in html
    assert '<meta property="og:title" content="Sarah Chen — Principal Systems Engineer on Distributed Transaction Engine">' in html
    assert '<meta property="og:site_name" content="BuildCrew">' in html
    assert '<meta name="twitter:card" content="summary">' in html
    assert 'Verified Proof-of-Work Contribution Passport' in html



