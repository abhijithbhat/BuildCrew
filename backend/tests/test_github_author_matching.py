import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from core.dependencies import get_current_user
from routers.projects import (
    DEV_CONFIRMATION_REQUESTS_DB,
    DEV_CONTRIBUTIONS_DB,
    DEV_GITHUB_IDENTITIES_DB,
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    _match_author_to_member,
    _verified_github_logins,
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
    DEV_GITHUB_IDENTITIES_DB.clear()
    github_service.DEV_GITHUB_INSTALLATIONS_DB.clear()
    yield
    app.dependency_overrides.clear()
    DEV_PROJECTS_DB.clear()
    DEV_PROJECT_MEMBERS_DB.clear()
    DEV_CONTRIBUTIONS_DB.clear()
    DEV_CONFIRMATION_REQUESTS_DB.clear()
    DEV_GITHUB_IDENTITIES_DB.clear()
    github_service.DEV_GITHUB_INSTALLATIONS_DB.clear()


# ==============================================================================
# 1. Verified GitHub Logins & Identity Inspection Tests
# ==============================================================================

def test_verified_github_logins_oauth_provider_match():
    """Member counts ONLY if user.identities has provider == 'github' with lowercased identity_data['user_name']."""
    mock_supabase = MagicMock()

    # User 1 has verified GitHub OAuth identity
    user1_identity = MagicMock()
    user1_identity.provider = "github"
    user1_identity.identity_data = {"user_name": "Alice-Dev"}
    mock_user1 = MagicMock(identities=[user1_identity])

    # User 2 has email identity only
    user2_identity = MagicMock()
    user2_identity.provider = "email"
    user2_identity.identity_data = {"email": "bob@example.com"}
    mock_user2 = MagicMock(identities=[user2_identity])

    def get_user_side_effect(uid):
        if uid == "u-alice":
            return MagicMock(user=mock_user1)
        elif uid == "u-bob":
            return MagicMock(user=mock_user2)
        return MagicMock(user=None)

    mock_supabase.auth.admin.get_user_by_id.side_effect = get_user_side_effect

    members = [
        {"user_id": "u-alice", "github_username": "forged_alice"},
        {"user_id": "u-bob", "github_username": "forged_bob"},
    ]

    verified = _verified_github_logins(members, supabase=mock_supabase)
    # Only Alice should be present, mapped from her OAuth identity lowercased
    assert "alice-dev" in verified
    assert verified["alice-dev"] == "u-alice"
    # Bob should not be in verified map despite having profiles.github_username
    assert "forged_bob" not in verified
    assert "bob" not in verified
    assert len(verified) == 1


def test_forged_profile_github_username_is_not_trusted():
    """profiles.github_username alone is NEVER trusted; email-signup members cannot spoof GitHub identity."""
    mock_supabase = MagicMock()

    # User signed up via email/password, no GitHub OAuth identity attached
    email_identity = MagicMock()
    email_identity.provider = "email"
    email_identity.identity_data = {"email": "impostor@buildcrew.io"}
    mock_impostor = MagicMock(identities=[email_identity])
    mock_supabase.auth.admin.get_user_by_id.return_value = MagicMock(user=mock_impostor)

    members = [
        {
            "user_id": "u-impostor",
            "email": "impostor@buildcrew.io",
            "github_username": "torvalds",  # Forged handle in profile
        }
    ]

    verified = _verified_github_logins(members, supabase=mock_supabase)
    assert "torvalds" not in verified
    assert len(verified) == 0


# ==============================================================================
# 2. Strict Author Matching Engine Unit Tests
# ==============================================================================

def test_match_author_exact_case_insensitive_and_noreply():
    verified_map = {
        "alice-code": "u-1",
        "bob-builder": "u-2",
    }

    # (a) Exact case-insensitive match on author_login
    assert _match_author_to_member("alice-code", None, verified_map) == "u-1"
    assert _match_author_to_member("ALICE-CODE", "irrelevant@corp.com", verified_map) == "u-1"
    assert _match_author_to_member("Bob-Builder", None, verified_map) == "u-2"

    # (b) Parse <id>+<login>@users.noreply.github.com
    assert _match_author_to_member(
        None, "123456+alice-code@users.noreply.github.com", verified_map
    ) == "u-1"

    # (b) Parse <login>@users.noreply.github.com
    assert _match_author_to_member(
        None, "bob-builder@users.noreply.github.com", verified_map
    ) == "u-2"


def test_match_author_bot_detection():
    verified_map = {
        "dependabot[bot]": "u-dependabot",
        "github-actions[bot]": "u-actions",
        "alice-code": "u-1",
    }

    # Logins ending in [bot] return None
    assert _match_author_to_member("dependabot[bot]", None, verified_map) is None
    assert _match_author_to_member("github-actions[bot]", None, verified_map) is None
    assert _match_author_to_member("custom-bot[bot]", "bot@service.com", verified_map) is None

    # Noreply emails ending in [bot] return None
    assert _match_author_to_member(
        None, "49699333+dependabot[bot]@users.noreply.github.com", verified_map
    ) is None
    assert _match_author_to_member(
        None, "github-actions[bot]@users.noreply.github.com", verified_map
    ) is None


def test_match_author_unmatched_never_credits_anyone():
    verified_map = {"alice-code": "u-1"}

    # Author not in verified map returns None
    assert _match_author_to_member("stranger", "stranger@corp.com", verified_map) is None
    assert _match_author_to_member("someone_else", None, verified_map) is None
    assert _match_author_to_member(None, "stranger@gmail.com", verified_map) is None


# ==============================================================================
# 3. Draft Generation Pipeline & End-to-End Endpoint Tests
# ==============================================================================

@pytest.mark.anyio
async def test_generate_drafts_skips_unmatched_and_bots_and_records_stats():
    """Verify that generate_draft_contributions skips unmatched authors and bots, never credits caller, and counts them."""
    caller_id = "user-caller"
    mock_caller = MagicMock(id=caller_id, email="caller@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_caller

    project_id = "proj-test-stats"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Audit Test Project",
        "created_by": caller_id,
    }

    # Setup installation
    github_service.DEV_GITHUB_INSTALLATIONS_DB[project_id] = {
        "id": "inst-1",
        "project_id": project_id,
        "installation_id": "inst-101",
        "repo_full_name": "buildcrew/stats-repo",
        "connected_at": "2026-09-01T00:00:00Z",
    }

    # Only member1 is verified
    DEV_PROJECT_MEMBERS_DB.append({"project_id": project_id, "user_id": "u-member1"})
    DEV_GITHUB_IDENTITIES_DB["u-member1"] = "verified-member"

    # Mock commits
    mock_commits = [
        {
            "sha": "c111",
            "message": "feat: legitimate verified commit",
            "author_login": "verified-member",
            "url": "https://github.com/buildcrew/stats-repo/commit/c111",
            "date": "2026-09-02T10:00:00Z",
        },
        {
            "sha": "c222",
            "message": "chore: dependabot bump",
            "author_login": "dependabot[bot]",
            "url": "https://github.com/buildcrew/stats-repo/commit/c222",
            "date": "2026-09-02T11:00:00Z",
        },
        {
            "sha": "c333",
            "message": "fix: outside contributor fix",
            "author_login": "outside-hacker",
            "url": "https://github.com/buildcrew/stats-repo/commit/c333",
            "date": "2026-09-02T12:00:00Z",
        },
        {
            "sha": "c444",
            "message": "fix: second commit by outside contributor",
            "author_login": "outside-hacker",
            "url": "https://github.com/buildcrew/stats-repo/commit/c444",
            "date": "2026-09-02T13:00:00Z",
        },
    ]

    # Mock PRs (1 merged bot PR, 1 unmerged PR, 1 merged unmatched PR)
    mock_pulls = [
        {
            "id": 1,
            "number": 1,
            "title": "bot automated pr",
            "user": "github-actions[bot]",
            "url": "https://github.com/buildcrew/stats-repo/pull/1",
            "merged_at": "2026-09-02T14:00:00Z",
        },
        {
            "id": 2,
            "number": 2,
            "title": "unmerged open pr by verified",
            "user": "verified-member",
            "url": "https://github.com/buildcrew/stats-repo/pull/2",
            "merged_at": None,  # Not merged!
        },
        {
            "id": 3,
            "number": 3,
            "title": "merged pr by external author",
            "user": "external-pr-author",
            "url": "https://github.com/buildcrew/stats-repo/pull/3",
            "merged_at": "2026-09-02T15:00:00Z",
        },
    ]

    with patch.object(github_service, "fetch_repository_commits", new_callable=AsyncMock, return_value=mock_commits), \
         patch.object(github_service, "fetch_repository_pulls", new_callable=AsyncMock, return_value=mock_pulls):
        response = client.post(f"/projects/{project_id}/generate-draft")
        assert response.status_code == 200
        data = response.json()

        # Only 1 contribution should be generated (the verified commit)
        assert data["generated_count"] == 1
        assert len(data["contributions"]) == 1

        generated = data["contributions"][0]
        assert generated["contributor"] == "u-member1"
        assert generated["evidence_link"] == "https://github.com/buildcrew/stats-repo/commit/c111"
        # Must be private and source-verified
        assert generated["visibility"] == "private"
        assert generated["verification_status"] == "source-verified"

        # Check skipped_bots count: 1 bot commit + 1 bot PR = 2 bots skipped
        assert data["skipped_bots"] == 2

        # Check unmatched summary: outside-hacker (count=2), external-pr-author (count=1)
        unmatched_map = {item["login"]: item["count"] for item in data["unmatched"]}
        assert unmatched_map.get("outside-hacker") == 2
        assert unmatched_map.get("external-pr-author") == 1
        assert "verified-member" not in unmatched_map


@pytest.mark.anyio
async def test_generate_drafts_deduplication_and_no_issues_imported():
    """Verify that issues are never imported and second run adds nothing (dedupe by evidence_link)."""
    caller_id = "user-lead"
    mock_caller = MagicMock(id=caller_id, email="lead@buildcrew.io")
    app.dependency_overrides[get_current_user] = lambda: mock_caller

    project_id = "proj-dedupe"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Dedupe Project",
        "created_by": caller_id,
    }
    DEV_GITHUB_IDENTITIES_DB[caller_id] = "lead-dev"

    github_service.DEV_GITHUB_INSTALLATIONS_DB[project_id] = {
        "id": "inst-dedupe",
        "project_id": project_id,
        "installation_id": "inst-202",
        "repo_full_name": "buildcrew/dedupe-repo",
        "connected_at": "2026-09-01T00:00:00Z",
    }

    mock_commits = [
        {
            "sha": "dedupe123",
            "message": "feat: primary commit",
            "author_login": "lead-dev",
            "url": "https://github.com/buildcrew/dedupe-repo/commit/dedupe123",
            "date": "2026-09-02T10:00:00Z",
        }
    ]
    mock_pulls = [
        {
            "id": 99,
            "number": 99,
            "title": "feat: primary merged PR",
            "user": "lead-dev",
            "url": "https://github.com/buildcrew/dedupe-repo/pull/99",
            "merged_at": "2026-09-02T11:00:00Z",
        }
    ]

    with patch.object(github_service, "fetch_repository_commits", new_callable=AsyncMock, return_value=mock_commits), \
         patch.object(github_service, "fetch_repository_pulls", new_callable=AsyncMock, return_value=mock_pulls):
        # 1st run
        resp1 = client.post(f"/projects/{project_id}/generate-draft")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["generated_count"] == 2  # 1 commit + 1 PR

        for c in data1["contributions"]:
            assert c["source_type"] in ("github_commit", "github_pr")
            assert c["source_type"] != "github_issue"  # Issues are NOT imported
            assert c["visibility"] == "private"
            assert c["verification_status"] == "source-verified"

        # 2nd run with the exact same items
        resp2 = client.post(f"/projects/{project_id}/generate-draft")
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Deduplication by evidence_link ensures 0 new items are created
        assert data2["generated_count"] == 0
        assert len(data2["contributions"]) == 2  # Existing contributions remain, no duplicates
