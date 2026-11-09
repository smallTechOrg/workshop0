"""Phase 11e slug lifecycle + slug lookup over the real API (PostgreSQL).

Spec: data-model.md §Phase 11e (Lifecycle), api.md §Phase 11e."""

import re

import pytest
from sqlalchemy import text

SLUG_RE = r"[a-z0-9]+(-[a-z0-9]+)*-[0-9a-f]{4,6}"
BLR = [{"city": "Bengaluru", "country": "India"}]


def _patch(client, admin_headers, oid: int, body: dict) -> dict:
    response = client.patch(f"/api/admin/opportunities/{oid}", json=body, headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["opportunity"]


def _db_slug(oid: int) -> str:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return session.execute(text("SELECT slug FROM opportunity WHERE id = :i"), {"i": oid}).scalar_one()


def _suffix(slug: str) -> str:
    return slug.rpartition("-")[2]


@pytest.fixture
def draft(create_opportunity):
    return create_opportunity(title="GenAI Workshop", location_mode="hybrid", locations=BLR)


def test_post_assigns_a_slug_and_draft_edits_keep_the_suffix(client, admin_headers, draft):
    slug = draft["slug"]
    assert re.fullmatch(r"genai-workshop-bengaluru-[0-9a-f]{4}", slug)
    assert _db_slug(draft["id"]) == slug
    assert draft["public_url"] == f"http://testserver/opportunities/{slug}"

    renamed = _patch(client, admin_headers, draft["id"], {"title": "LLM Workshop"})
    assert renamed["slug"] == f"llm-workshop-bengaluru-{_suffix(slug)}"
    assert _db_slug(draft["id"]) == renamed["slug"]

    moved = _patch(client, admin_headers, draft["id"], {"locations": [{"city": "Pune", "country": None}]})
    assert moved["slug"] == f"llm-workshop-pune-{_suffix(slug)}"


def test_slug_is_frozen_from_the_first_publish(client, admin_headers, draft):
    published = _patch(client, admin_headers, draft["id"], {"status": "open"})
    frozen = published["slug"]
    assert frozen == draft["slug"]

    edited = _patch(
        client, admin_headers, draft["id"],
        {"title": "Completely Different", "locations": [{"city": "Delhi", "country": None}]},
    )
    assert edited["slug"] == frozen
    assert _patch(client, admin_headers, draft["id"], {"status": "draft"})["slug"] == frozen
    assert _patch(client, admin_headers, draft["id"], {"title": "Again Renamed"})["slug"] == frozen
    assert _patch(client, admin_headers, draft["id"], {"status": "open"})["slug"] == frozen
    assert _patch(client, admin_headers, draft["id"], {"status": "closed"})["slug"] == frozen
    assert _db_slug(draft["id"]) == frozen


def test_public_url_uses_the_slug_on_admin_and_public_payloads(client, admin_headers, create_opportunity):
    opp = create_opportunity(title="Open Listing", status="open")
    assert opp["public_url"].endswith(f"/opportunities/{opp['slug']}")
    admin_get = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()
    assert admin_get["data"]["opportunity"]["public_url"].endswith(f"/opportunities/{opp['slug']}")
    rows = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]["opportunities"]
    assert rows[0]["slug"] == opp["slug"] and rows[0]["public_url"].endswith(opp["slug"])
    cards = client.get("/api/public/opportunities").json()["data"]["opportunities"]
    assert [(c["slug"], c["public_url"]) for c in cards] == [
        (opp["slug"], f"http://testserver/opportunities/{opp['slug']}")
    ]


def test_public_detail_by_slug_upper_cased_slug_and_id_is_the_same_listing(client, create_opportunity):
    opp = create_opportunity(title="Lookup Listing", status="open")
    keys = [opp["slug"], opp["slug"].upper(), str(opp["id"])]
    found = []
    for key in keys:
        response = client.get(f"/api/public/opportunities/{key}")
        assert response.status_code == 200, key
        found.append(response.json()["data"]["opportunity"])
    assert {o["id"] for o in found} == {opp["id"]}
    assert all(o["slug"] == opp["slug"] for o in found)


@pytest.mark.parametrize("key", ["does-not-exist-0000", "a b&c", "x" * 81, "-", "9" * 12, "0"])
def test_unknown_or_malformed_keys_are_404(client, create_opportunity, key):
    create_opportunity(title="Some Listing", status="open")
    response = client.get(f"/api/public/opportunities/{key}")
    assert response.status_code == 404, key
    assert response.json()["detail"]["code"] == "not_found"


def test_draft_slug_and_id_are_404(client, draft):
    for key in (draft["slug"], str(draft["id"])):
        response = client.get(f"/api/public/opportunities/{key}")
        assert response.status_code == 404, key
        assert "GenAI Workshop" not in response.text


def test_slug_in_a_request_body_is_ignored(client, admin_headers, topic_ids):
    from tests.conftest import opportunity_body

    body = opportunity_body([topic_ids["generative-ai"]], title="Body Slug", slug="hacked-1234")
    created = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
    assert created.status_code == 200, created.text
    opp = created.json()["data"]["opportunity"]
    assert opp["slug"] != "hacked-1234" and opp["slug"].startswith("body-slug-")

    patched = _patch(client, admin_headers, opp["id"], {"slug": "hacked-5678", "summary": "New"})
    assert patched["slug"] == opp["slug"] == _db_slug(opp["id"])
    noop = _patch(client, admin_headers, opp["id"], {"slug": "hacked-9999"})
    assert noop["slug"] == opp["slug"]


def test_no_audit_row_reports_slug_in_changed_fields(client, admin_headers, draft):
    _patch(client, admin_headers, draft["id"], {"title": "LLM Workshop"})
    _patch(client, admin_headers, draft["id"], {"status": "open"})
    activity = client.get(
        f"/api/admin/opportunities/{draft['id']}", headers=admin_headers
    ).json()["data"]["activity"]
    assert len(activity) == 3
    for row in activity:
        assert "slug" not in row["detail"].get("changed_fields", [])
        assert "slug" not in row["detail"]


def test_two_listings_with_the_same_title_get_distinct_slugs(create_opportunity):
    a = create_opportunity(title="Same Title", location_mode="onsite", locations=[{"city": "Delhi"}])
    b = create_opportunity(title="Same Title", location_mode="onsite", locations=[{"city": "Delhi"}])
    assert a["slug"] != b["slug"]
    for o in (a, b):
        assert re.fullmatch(r"same-title-delhi-[0-9a-f]{4,6}", o["slug"])
        assert re.fullmatch(SLUG_RE, o["slug"])


def test_duplicate_slug_insert_is_rejected_by_the_constraint(create_opportunity):
    from sqlalchemy.exc import IntegrityError

    from src.workshop0.db.session import create_db_session

    a = create_opportunity(title="First")
    b = create_opportunity(title="Second")
    with pytest.raises(IntegrityError):
        with create_db_session() as session:
            session.execute(
                text("UPDATE opportunity SET slug = :s WHERE id = :i"), {"s": a["slug"], "i": b["id"]}
            )
            session.flush()


def test_post_retries_once_when_a_slug_collides_past_the_precheck(
    client, admin_headers, topic_ids, create_opportunity, monkeypatch
):
    """The unique constraint is the backstop: a race that slips past _slug_taken
    rolls back the savepoint, re-attaches the new row and retries with a fresh suffix."""
    from src.workshop0.db.session import create_db_session
    from src.workshop0.services import opportunities
    from tests.conftest import opportunity_body

    existing = create_opportunity(title="Race Title")
    real_new_slug = opportunities._new_slug
    calls = {"n": 0}

    def colliding_new_slug(session, base, *, exclude_id=None):
        calls["n"] += 1
        if calls["n"] == 1:  # concurrent insert: the precheck said free, the DB says taken
            return existing["slug"]
        return real_new_slug(session, base, exclude_id=exclude_id)

    monkeypatch.setattr(opportunities, "_new_slug", colliding_new_slug)
    topic = topic_ids["generative-ai"]
    response = client.post(
        "/api/admin/opportunities", json=opportunity_body([topic], title="Race Title"), headers=admin_headers
    )
    assert response.status_code == 200, response.text
    opp = response.json()["data"]["opportunity"]
    assert calls["n"] == 2
    assert opp["slug"] != existing["slug"]
    assert re.fullmatch(r"race-title-[0-9a-f]{4,6}", opp["slug"])
    with create_db_session() as session:
        assert session.execute(
            text("SELECT slug FROM opportunity WHERE id = :i"), {"i": opp["id"]}
        ).scalar_one() == opp["slug"]
        topics = session.execute(
            text("SELECT topic_id FROM opportunity_topic WHERE opportunity_id = :i"), {"i": opp["id"]}
        ).scalars().all()
    assert topics == [topic]
