import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from main import app
from routers.projects import (
    DEV_PROJECTS_DB,
    DEV_PROJECT_MEMBERS_DB,
    DEV_ROLE_AGREEMENTS_DB,
    DEV_CONTRIBUTIONS_DB,
)
from routers.contributions import DEV_CONFIRMATIONS_DB
from routers.auth import DEV_USER_NAMES_DB
from services.github_service import DEV_GITHUB_INSTALLATIONS_DB

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

    # 1. Query with ?format=json returns JSON without auth
    resp_json = client.get(f"/passport/{user_id}/{project_id}?format=json")
    assert resp_json.status_code == 200
    assert "application/json" in resp_json.headers.get("content-type", "")
    data = resp_json.json()
    assert data["user_id"] == user_id
    assert data["project_id"] == project_id
    assert data["project_name"] == "Open Source Kernel"
    assert data["role"] == "Team Lead"
    assert data["total_contributions"] == 0
    assert data["contributions"] == []

    # 2. Query without ?format=json (default Accept */*) returns HTML without auth
    resp_html = client.get(f"/passport/{user_id}/{project_id}")
    assert resp_html.status_code == 200
    assert "text/html" in resp_html.headers.get("content-type", "")
    assert "Open Source Kernel" in resp_html.text


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

    # Query public endpoint with format=json
    resp = client.get(f"/passport/{author_id}/{project_id}?format=json")
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
    slash_resp = client.get(f"/passport/{author_id}/{project_id}/?format=json")
    assert slash_resp.status_code == 200
    assert slash_resp.json()["total_contributions"] == 1


def test_public_passport_content_negotiation_rules():
    """
    Requirement 1: Content negotiation (main.py ~l.172):
    render HTML unless ?format=json or the Accept header lists application/json before text/html.
    */* and a missing Accept header must return HTML.
    """
    user_id = "user-cn-test"
    project_id = "proj-cn-test"

    DEV_USER_NAMES_DB[user_id] = "Diana Prince"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Themyscira Grid",
        "created_by": user_id,
    }

    # Case A: Accept */* returns HTML with og:title
    resp_star = client.get(f"/passport/{user_id}/{project_id}", headers={"Accept": "*/*"})
    assert resp_star.status_code == 200
    assert "text/html" in resp_star.headers.get("content-type", "")
    assert '<meta property="og:title"' in resp_star.text

    # Case B: Missing Accept header returns HTML
    resp_no_accept = client.get(f"/passport/{user_id}/{project_id}", headers={})
    assert resp_no_accept.status_code == 200
    assert "text/html" in resp_no_accept.headers.get("content-type", "")
    assert '<meta property="og:title"' in resp_no_accept.text

    # Case C: ?format=json returns JSON
    resp_format_json = client.get(f"/passport/{user_id}/{project_id}?format=json")
    assert resp_format_json.status_code == 200
    assert "application/json" in resp_format_json.headers.get("content-type", "")
    assert resp_format_json.json()["user_id"] == user_id

    # Case D: ?format=json overrides Accept: text/html
    resp_override = client.get(
        f"/passport/{user_id}/{project_id}?format=json",
        headers={"Accept": "text/html"},
    )
    assert resp_override.status_code == 200
    assert "application/json" in resp_override.headers.get("content-type", "")

    # Case E: Accept header lists application/json before text/html returns JSON
    resp_json_first = client.get(
        f"/passport/{user_id}/{project_id}",
        headers={"Accept": "application/json, text/html;q=0.9"},
    )
    assert resp_json_first.status_code == 200
    assert "application/json" in resp_json_first.headers.get("content-type", "")

    # Case F: Accept header lists text/html before application/json returns HTML
    resp_html_first = client.get(
        f"/passport/{user_id}/{project_id}",
        headers={"Accept": "text/html, application/json;q=0.9"},
    )
    assert resp_html_first.status_code == 200
    assert "text/html" in resp_html_first.headers.get("content-type", "")


def test_public_passport_errors_return_branded_html_page_on_html_requests():
    """
    Requirement 2: Errors on that route:
    catch HTTPException and return a small branded HTML page (emerald #064E3B / champagne #F8E7C9, no JSON)
    with the same status code (404 "Passport not found", 503 "Temporarily unavailable, try again shortly")
    when the request is rendering HTML.
    """
    # 1. 404 Not Found on HTML request
    resp_404 = client.get(
        "/passport/non-existent-user/non-existent-proj",
        headers={"Accept": "*/*"},
    )
    assert resp_404.status_code == 404
    assert "text/html" in resp_404.headers.get("content-type", "")
    assert "Passport not found" in resp_404.text
    assert "#064E3B" in resp_404.text
    assert "#F8E7C9" in resp_404.text
    # Ensure it's not a JSON error response
    assert not resp_404.text.strip().startswith("{")

    # 2. 503 from data layer on HTML request
    with patch("main.get_project_passport", side_effect=Exception("Database cluster connection failed")):
        resp_503 = client.get(
            "/passport/any-user/any-proj",
            headers={"Accept": "*/*"},
        )
        assert resp_503.status_code == 503
        assert "text/html" in resp_503.headers.get("content-type", "")
        assert "Temporarily unavailable, try again shortly" in resp_503.text
        assert "#064E3B" in resp_503.text
        assert "#F8E7C9" in resp_503.text

    # 3. Explicit HTTPException(503) on HTML request
    with patch("main.get_project_passport", side_effect=HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Temporarily unavailable, try again shortly")):
        resp_503_http = client.get(
            "/passport/any-user/any-proj",
            headers={"Accept": "*/*"},
        )
        assert resp_503_http.status_code == 503
        assert "text/html" in resp_503_http.headers.get("content-type", "")
        assert "Temporarily unavailable, try again shortly" in resp_503_http.text
        assert "#064E3B" in resp_503_http.text
        assert "#F8E7C9" in resp_503_http.text

    # 3. For ?format=json, HTTPException returns JSON
    resp_json_404 = client.get("/passport/non-existent-user/non-existent-proj?format=json")
    assert resp_json_404.status_code == 404
    assert "application/json" in resp_json_404.headers.get("content-type", "")
    assert "detail" in resp_json_404.json()


def test_public_passport_copy_prohibited_phrases_removed_and_new_copy():
    """
    Requirement 3 & 7 & 9:
    Delete 'Consensus Verified', 'cryptographically confirmed', the avatar 'Verified Contributor' tick,
    '100% Peer Approved' and the per-card 'Verified by BuildCrew Team Consensus' footer.
    Title: 'BuildCrew Contribution Passport'.
    Subtitle: 'Each item is linked to GitHub activity matched to this person's verified GitHub account, or confirmed by named teammates. Open the links to check the source.'
    Role shown as 'Declared role: X'.
    Replace the 'PID:' chip with 'Team of N' and the first 200 characters of the project description.
    3-bullet 'How verification works' block at the bottom.
    """
    user_id = "user-copy-test"
    project_id = "proj-copy-test"

    DEV_USER_NAMES_DB[user_id] = "Ada Lovelace"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Analytical Engine",
        "description": "First general-purpose mechanical computer architecture and algorithmic execution model.",
        "created_by": user_id,
    }
    DEV_ROLE_AGREEMENTS_DB.append({
        "project_id": project_id,
        "user_id": user_id,
        "role_name": "Chief Algorithmist",
        "category": "architecture",
    })

    DEV_CONTRIBUTIONS_DB.append({
        "id": "c-copy-1",
        "contributor": user_id,
        "project": project_id,
        "title": "Bernoulli Numbers Generator",
        "category": "code",
        "description": "Pioneering algorithmic formulation",
        "verification_status": "peer-confirmed",
        "confirmed_by": "peer-charles",
        "visibility": "public",
        "dispute_state": "none",
        "created_at": "2026-09-10T12:00:00Z",
    })

    resp = client.get(f"/passport/{user_id}/{project_id}", headers={"Accept": "*/*"})
    assert resp.status_code == 200
    html = resp.text

    # A. Prohibited phrases MUST NOT be in the HTML
    prohibited_phrases = [
        "Consensus Verified",
        "cryptographically confirmed",
        "Verified Contributor",
        "100% Peer Approved",
        "Verified by BuildCrew Team Consensus",
    ]
    for phrase in prohibited_phrases:
        assert phrase not in html, f"Prohibited phrase '{phrase}' found in passport HTML!"

    # B. Verified new title, subtitle, role, team chip, description
    assert "BuildCrew Contribution Passport" in html
    assert "Each item is linked to GitHub activity matched to this person's verified GitHub account, or confirmed by named teammates. Open the links to check the source." in html
    assert "Declared role: Chief Algorithmist" in html
    assert "Team of 1" in html
    assert "First general-purpose mechanical computer architecture" in html

    # C. 3-bullet 'How verification works' block at the bottom
    assert "How verification works" in html
    assert "GitHub items come from the connected repository and match the contributor's signed-in GitHub account." in html
    assert "Confirmations come from named teammates." in html
    assert "BuildCrew does not inspect uploaded files or typed links, and roles are self-declared." in html


def test_public_passport_raw_commits_collapse_to_one_row_and_confirmed_count():
    """
    Requirement 6 & 9:
    Show raw GitHub commits as ONE row ('N commits between <first> and <last>' + the GitHub link, no per-commit cards);
    list merged PRs and peer-confirmed manual items individually;
    confirmed_count counts only those two kinds.
    """
    user_id = "user-commits-test"
    project_id = "proj-commits-test"

    DEV_USER_NAMES_DB[user_id] = "Grace Hopper"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Compiler Foundation",
        "github_repo": "buildcrew/compiler-engine",
        "created_by": user_id,
    }
    from routers.projects import DEV_GITHUB_IDENTITIES_DB
    DEV_GITHUB_IDENTITIES_DB[user_id] = "gracehopper"

    # Add 3 raw GitHub commits
    DEV_CONTRIBUTIONS_DB.extend([
        {
            "id": "c-commit-1",
            "contributor": user_id,
            "project": project_id,
            "title": "Lexer grammar definitions",
            "category": "code",
            "source_type": "github_commit",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/compiler-engine/commit/111",
            "created_at": "2026-08-01T10:00:00Z",
        },
        {
            "id": "c-commit-2",
            "contributor": user_id,
            "project": project_id,
            "title": "AST parser implementation",
            "category": "code",
            "source_type": "github_commit",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/compiler-engine/commit/222",
            "created_at": "2026-08-15T10:00:00Z",
        },
        {
            "id": "c-commit-3",
            "contributor": user_id,
            "project": project_id,
            "title": "Code generator backend",
            "category": "code",
            "source_type": "github_commit",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/compiler-engine/commit/333",
            "created_at": "2026-08-30T10:00:00Z",
        },
        # Add 1 merged PR
        {
            "id": "c-pr-1",
            "contributor": user_id,
            "project": project_id,
            "title": "PR #42: Optimize symbol lookup tables",
            "category": "code",
            "source_type": "github_pr",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/compiler-engine/pull/42",
            "created_at": "2026-09-05T10:00:00Z",
        },
        # Add 1 manual peer-confirmed deliverable
        {
            "id": "c-manual-1",
            "contributor": user_id,
            "project": project_id,
            "title": "Subroutine Architecture RFC",
            "category": "architecture",
            "source_type": "manual",
            "verification_status": "peer-confirmed",
            "confirmed_by": "peer-linus",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://docs.buildcrew.io/rfc/subroutines",
            "created_at": "2026-09-08T10:00:00Z",
        },
    ])

    # 1. Verify JSON counting and collapsing
    resp_json = client.get(f"/passport/{user_id}/{project_id}?format=json")
    assert resp_json.status_code == 200
    data = resp_json.json()

    # Raw commits collapsed into ONE row -> Total display items = 1 (collapsed commit) + 1 (PR) + 1 (manual) = 3
    assert data["total_contributions"] == 3
    # confirmed_count strictly counts ONLY merged PRs and peer-confirmed manual items! (1 PR + 1 manual = 2)
    assert data["confirmed_count"] == 2

    titles = [c["title"] for c in data["contributions"]]
    assert "3 commits between 2026-08-01 and 2026-08-30" in titles
    assert "PR #42: Optimize symbol lookup tables" in titles
    assert "Subroutine Architecture RFC" in titles
    # Individual commit cards are NOT listed!
    assert "Lexer grammar definitions" not in titles
    assert "AST parser implementation" not in titles

    # 2. Verify HTML rendering
    resp_html = client.get(f"/passport/{user_id}/{project_id}", headers={"Accept": "*/*"})
    assert resp_html.status_code == 200
    html = resp_html.text
    assert "3 commits between 2026-08-01 and 2026-08-30" in html
    assert "Lexer grammar definitions" not in html
    assert "PR #42: Optimize symbol lookup tables" in html
    assert "Subroutine Architecture RFC" in html


def test_public_passport_confirmer_names_and_header_summary_line():
    """
    Requirement 4 & 5 & 9:
    Confirmer names appear:
    - In the per-item badge: 'Confirmed by A, B · <date>'
    - In header summary line: 'Evidence: N items · G matched to GitHub @login · C confirmed by <names> (k of team_size teammates)'
    - Repository header line with GitHub commits link
    - Evidence labels: 'View on GitHub' vs 'Evidence link (provided by contributor)'
    """
    user_id = "user-summary-test"
    project_id = "proj-summary-test"
    voter1_id = "user-voter-alice"
    voter2_id = "user-voter-bob"

    DEV_USER_NAMES_DB[user_id] = "Margaret Hamilton"
    DEV_USER_NAMES_DB[voter1_id] = "Alice Armstrong"
    DEV_USER_NAMES_DB[voter2_id] = "Bob Aldrin"

    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Apollo AGC Flight Software",
        "description": "Guidance computer asynchronous executive",
        "github_repo": "buildcrew/apollo-agc",
        "created_by": user_id,
    }
    DEV_PROJECT_MEMBERS_DB.extend([
        {"project_id": project_id, "user_id": voter1_id, "role": "member"},
        {"project_id": project_id, "user_id": voter2_id, "role": "member"},
        {"project_id": project_id, "user_id": "user-member-3", "role": "member"},
    ])
    # Total team size = creator + 3 members = 4
    from routers.projects import DEV_GITHUB_IDENTITIES_DB
    DEV_GITHUB_IDENTITIES_DB[user_id] = "mhamilton"

    manual_item_id = "c-apollo-manual-1"
    DEV_CONTRIBUTIONS_DB.extend([
        # 1. GitHub commit
        {
            "id": "c-apollo-commit-1",
            "contributor": user_id,
            "project": project_id,
            "title": "Async executive job scheduler",
            "category": "code",
            "source_type": "github_commit",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/apollo-agc/commit/aaa",
            "created_at": "2026-07-01T12:00:00Z",
        },
        # 2. GitHub PR
        {
            "id": "c-apollo-pr-1",
            "contributor": user_id,
            "project": project_id,
            "title": "PR #11: Priority display restart protection",
            "category": "code",
            "source_type": "github_pr",
            "verification_status": "source-verified",
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://github.com/buildcrew/apollo-agc/pull/11",
            "created_at": "2026-07-10T12:00:00Z",
        },
        # 3. Manual deliverable confirmed by Alice and Bob
        {
            "id": manual_item_id,
            "contributor": user_id,
            "project": project_id,
            "title": "Flight Software Specification & Verification Matrix",
            "category": "documentation",
            "source_type": "manual",
            "verification_status": "peer-confirmed",
            "confirmed_by": voter1_id,
            "visibility": "public",
            "dispute_state": "none",
            "evidence_link": "https://specs.nasa.gov/agc-flight-specs.pdf",
            "created_at": "2026-07-15T12:00:00Z",
        },
    ])

    # Record confirmations in DEV_CONFIRMATIONS_DB
    DEV_CONFIRMATIONS_DB.extend([
        {
            "contribution_id": manual_item_id,
            "confirmed_by_user_id": voter1_id,
            "action": "confirm",
            "confirmed_at": "2026-07-16T10:00:00Z",
        },
        {
            "contribution_id": manual_item_id,
            "confirmed_by_user_id": voter2_id,
            "action": "confirm",
            "confirmed_at": "2026-07-17T11:00:00Z",
        },
    ])

    resp = client.get(f"/passport/{user_id}/{project_id}", headers={"Accept": "*/*"})
    assert resp.status_code == 200
    html = resp.text

    # Confirmer names must appear in the summary line
    # Evidence: 3 items · 2 matched to GitHub @mhamilton · 1 confirmed by Alice Armstrong, Bob Aldrin (2 of 4 teammates)
    assert "Evidence: 3 items · 2 matched to GitHub @mhamilton · 1 confirmed by Alice Armstrong, Bob Aldrin (2 of 4 teammates)" in html

    # Repository link and commits link
    assert "Repository: <a href=\"https://github.com/buildcrew/apollo-agc\" target=\"_blank\" rel=\"noopener noreferrer\">github.com/buildcrew/apollo-agc</a>" in html
    assert "All commits by @mhamilton" in html
    assert "https://github.com/buildcrew/apollo-agc/commits?author=mhamilton" in html

    # Confirmer names must appear on the card badge
    assert "Confirmed by Alice Armstrong, Bob Aldrin · 2026-07-17" in html

    # Per-item badges and evidence labels
    assert "GitHub · matched to @mhamilton" in html
    assert "View on GitHub" in html
    assert "Evidence link (provided by contributor)" in html


def test_public_passport_og_image_and_meta_tags():
    """
    Requirement 8:
    generate backend/static/og-default.png (1200x630, Pillow, emerald background, champagne text 'BuildCrew — verified contribution passports');
    mount /static read-only (keep the existing /static/evidence mount working);
    use it as og:image/twitter:image when there is no avatar, with an absolute URL;
    set twitter:card to summary_large_image. Keep noindex.
    """
    user_id = "user-og-test"
    project_id = "proj-og-test"

    DEV_USER_NAMES_DB[user_id] = "Alan Turing"
    DEV_PROJECTS_DB[project_id] = {
        "id": project_id,
        "name": "Enigma Cryptanalysis",
        "created_by": user_id,
    }

    # Case A: User without avatar gets default og image with absolute URL
    resp = client.get(f"/passport/{user_id}/{project_id}", headers={"Accept": "*/*"})
    assert resp.status_code == 200
    html = resp.text

    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<meta property="og:image" content="http://testserver/static/og-default.png">' in html
    assert '<meta name="twitter:image" content="http://testserver/static/og-default.png">' in html

    # Case B: Static mounts work properly
    resp_img = client.get("/static/og-default.png")
    assert resp_img.status_code == 200
    assert "image/png" in resp_img.headers.get("content-type", "")
    assert len(resp_img.content) > 0


def test_format_clean_display_name_resolves_profile_names_and_email_fallbacks():
    from routers.contributions import _format_clean_display_name

    # 1. Profile display_name takes highest precedence
    assert _format_clean_display_name(
        "raw_prefix",
        {"display_name": "Abhijith Hubli", "full_name": "Abhijith M Bhat"},
    ) == "Abhijith Hubli"

    # 2. Profile full_name used when display_name is absent
    assert _format_clean_display_name(
        "raw_prefix",
        {"full_name": "Abhijith M Bhat"},
    ) == "Abhijith M Bhat"

    # 3. If display_name and full_name are emails, falls back to cleaned email prefix
    assert _format_clean_display_name(
        "abhijithhubli@gmail.com",
        {"display_name": "abhijithhubli@gmail.com"},
    ) == "Abhijithhubli"

    # 4. Standard email parsing when no profile is present
    assert _format_clean_display_name("john.doe_dev@domain.com") == "John Doe Dev"

    # 5. Raw name with no email
    assert _format_clean_display_name("Sarah Connor") == "Sarah Connor"

    # 6. None or empty falls back to Anonymous Builder
    assert _format_clean_display_name(None) == "Anonymous Builder"
