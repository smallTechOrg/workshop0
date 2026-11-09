"""C9 Opportunity management — admin auth, create/patch validation (exact messages),
state transitions, list counts/filters/search/pagination (PostgreSQL)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.conftest import iso, opportunity_body

ADMIN_FULL_KEYS = {
    "id", "title", "type", "summary", "description_md", "topics", "location_mode", "city",
    "starts_on", "ends_on", "duration_text", "compensation_text", "deadline",
    "partner_display_name", "partner_internal_name", "internal_notes", "status",
    "partner_id", "partner", "compensation_min", "compensation_max", "compensation_currency",
    "compensation_unit",
    "stored_status", "public_url", "published_at", "closed_at", "created_at", "updated_at",
}


def _count(sql: str) -> int:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return int(session.execute(text(sql)).scalar_one())


# --------------------------------------------------------------------------- auth


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/admin/opportunities", None),
        ("post", "/api/admin/opportunities", {"title": "x"}),
        ("get", "/api/admin/opportunities/1", None),
        ("patch", "/api/admin/opportunities/1", {"title": "Hello there"}),
        ("get", "/api/admin/topics", None),
        ("post", "/api/admin/topics", {"name": "Elixir", "category": "Languages"}),
        ("patch", "/api/admin/topics/1", {"active": False}),
    ],
)
@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_every_admin_board_endpoint_requires_the_key(client, method, path, body, key):
    headers = {"X-Admin-Key": key} if key else {}
    kwargs = {"json": body} if body is not None else {}
    response = getattr(client, method)(path, headers=headers, **kwargs)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_admin_key"
    assert _count("SELECT count(*) FROM topic WHERE active") == 40  # nothing changed


# --------------------------------------------------------------------------- create


def test_create_draft_persists_listing_topics_and_returns_full_admin_shape(client, admin_headers, topic_ids):
    body = opportunity_body(
        [topic_ids["generative-ai"], topic_ids["prompt-engineering"]],
        location_mode="hybrid", city="Bengaluru", starts_on="2026-12-05", ends_on="2026-12-06",
        duration_text="2 days", compensation_text="Paid — day rate",
        deadline="2026-11-30T23:59:59+05:30",
    )
    response = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
    assert response.status_code == 200, response.text
    opp = response.json()["data"]["opportunity"]
    assert set(opp) == ADMIN_FULL_KEYS
    assert opp["status"] == opp["stored_status"] == "draft"
    assert opp["published_at"] is None and opp["closed_at"] is None
    assert opp["deadline"] == "2026-11-30T18:29:59Z"  # normalised to UTC
    assert opp["partner_internal_name"] == "Acme Payments Pvt Ltd"
    assert opp["internal_notes"] == "Contact: R. Rao"
    assert [t["slug"] for t in opp["topics"]] == ["generative-ai", "prompt-engineering"]
    assert opp["public_url"] == f"http://testserver/opportunities/{opp['id']}"
    assert _count("SELECT count(*) FROM opportunity") == 1
    assert _count("SELECT count(*) FROM opportunity_topic") == 2
    # draft is invisible publicly
    assert client.get(f"/api/public/opportunities/{opp['id']}").status_code == 404


def test_create_open_sets_published_at_and_remote_forces_city_null(client, admin_headers, topic_ids):
    body = opportunity_body([topic_ids["python"]], status="open", location_mode="remote", city="Pune")
    opp = client.post("/api/admin/opportunities", json=body, headers=admin_headers).json()["data"]["opportunity"]
    assert opp["status"] == "open" and opp["published_at"] is not None
    assert opp["city"] is None


def _with(slug_map, **overrides):
    return opportunity_body([slug_map["python"]], **overrides)


PAST = iso(datetime.now(timezone.utc) - timedelta(hours=1))

CREATE_CASES = [
    (dict(title="ab"), "title: must be 3–160 characters"),
    (dict(title="t" * 161), "title: must be 3–160 characters"),
    (dict(title="   "), "title: must be 3–160 characters"),
    (dict(type="gig"), "type: must be one of workshop, engagement, role, cofacilitation"),
    (dict(summary="  "), "summary: must be 1–280 characters"),
    (dict(summary="s" * 281), "summary: must be 1–280 characters"),
    (dict(description_md="d" * 20001), "description_md: must be at most 20000 characters"),
    (dict(topic_ids=[]), "topic_ids: choose 1 to 8 topics"),
    (dict(topic_ids=list(range(1, 10))), "topic_ids: choose 1 to 8 topics"),
    (dict(topic_ids=[1, 1]), "topic_ids: choose each topic only once"),
    (dict(topic_ids=[99999]), "topic_ids: topic 99999 does not exist"),
    (dict(location_mode="moon"), "location_mode: must be one of remote, onsite, hybrid"),
    (dict(location_mode="onsite"), "city: required for onsite or hybrid"),
    (dict(location_mode="hybrid", city="  "), "city: required for onsite or hybrid"),
    (dict(location_mode="onsite", city="c" * 81), "city: must be at most 80 characters"),
    (dict(starts_on="2026-12-06", ends_on="2026-12-05"), "ends_on: must be on or after starts_on"),
    (dict(duration_text="d" * 81), "duration_text: must be at most 80 characters"),
    (dict(compensation_text="c" * 121), "compensation_text: must be at most 120 characters"),
    (dict(deadline="2026-11-30T18:29:59"), "deadline: include a time zone, e.g. 2026-11-30T18:29:59Z"),
    (dict(partner_display_name="p" * 161), "partner_display_name: must be at most 160 characters"),
    (dict(partner_internal_name="p" * 161), "partner_internal_name: must be at most 160 characters"),
    (dict(internal_notes="n" * 5001), "internal_notes: must be at most 5000 characters"),
    (dict(status="expired"), "status: must be one of draft, open, closed"),
    (dict(status="open", deadline=PAST), "deadline: set a future deadline to publish"),
]


@pytest.mark.parametrize(("overrides", "message"), CREATE_CASES)
def test_create_validation_messages(client, admin_headers, topic_ids, overrides, message):
    response = client.post("/api/admin/opportunities", json=_with(topic_ids, **overrides), headers=admin_headers)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == {"code": "validation_error", "message": message}
    assert _count("SELECT count(*) FROM opportunity") == 0
    assert _count("SELECT count(*) FROM facilitator_action") == 0


@pytest.mark.parametrize("field", ["title", "type", "summary", "topic_ids", "deadline"])
def test_create_missing_required_field(client, admin_headers, topic_ids, field):
    body = _with(topic_ids)
    del body[field]
    response = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"] == {"code": "validation_error", "message": f"{field}: Field required"}


def test_draft_and_closed_may_carry_a_past_deadline(client, admin_headers, topic_ids):
    for status in ("draft", "closed"):
        response = client.post(
            "/api/admin/opportunities", json=_with(topic_ids, status=status, deadline=PAST), headers=admin_headers
        )
        assert response.status_code == 200, (status, response.text)


# --------------------------------------------------------------------------- patch


def test_patch_validation_uses_the_same_rules(client, admin_headers, create_opportunity, topic_ids):
    opp = create_opportunity(["python"], status="open")
    path = f"/api/admin/opportunities/{opp['id']}"
    cases = [
        ({"topic_ids": []}, "topic_ids: choose 1 to 8 topics"),
        ({"topic_ids": list(range(1, 10))}, "topic_ids: choose 1 to 8 topics"),
        ({"location_mode": "onsite"}, "city: required for onsite or hybrid"),
        ({"starts_on": "2026-12-06", "ends_on": "2026-12-01"}, "ends_on: must be on or after starts_on"),
        ({"deadline": "2026-11-30T18:29:59"}, "deadline: include a time zone, e.g. 2026-11-30T18:29:59Z"),
        ({"deadline": PAST}, "deadline: set a future deadline to publish"),
        ({"title": None}, "title: is required"),
        ({"deadline": None}, "deadline: is required"),
        ({"status": None}, "status: is required"),
    ]
    for body, message in cases:
        response = client.patch(path, json=body, headers=admin_headers)
        assert response.status_code == 422, body
        assert response.json()["detail"] == {"code": "validation_error", "message": message}, body
    unchanged = client.get(path, headers=admin_headers).json()["data"]
    assert unchanged["opportunity"]["deadline"] == opp["deadline"]
    assert [a["action"] for a in unchanged["activity"]] == ["opportunity.create"]


def test_patch_ends_before_existing_start_is_rejected(client, admin_headers, create_opportunity):
    opp = create_opportunity(starts_on="2026-12-05")
    response = client.patch(
        f"/api/admin/opportunities/{opp['id']}", json={"ends_on": "2026-12-04"}, headers=admin_headers
    )
    assert response.json()["detail"]["message"] == "ends_on: must be on or after starts_on"


def test_publish_with_a_past_deadline_is_refused_and_nothing_goes_public(client, admin_headers, create_opportunity):
    opp = create_opportunity(deadline=PAST)  # draft with a past deadline is fine
    response = client.patch(f"/api/admin/opportunities/{opp['id']}", json={"status": "open"}, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "deadline: set a future deadline to publish"
    assert client.get(f"/api/public/opportunities/{opp['id']}").status_code == 404
    assert client.get("/api/public/opportunities").json()["data"]["total"] == 0


def test_patch_omitted_unchanged_null_clears_and_topics_replace(client, admin_headers, create_opportunity, topic_ids):
    opp = create_opportunity(["python", "go"], duration_text="2 days", compensation_text="Paid")
    response = client.patch(
        f"/api/admin/opportunities/{opp['id']}",
        json={"duration_text": None, "compensation_text": "  ", "topic_ids": [topic_ids["rust"]]},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    after = response.json()["data"]["opportunity"]
    assert after["duration_text"] is None and after["compensation_text"] is None
    assert [t["slug"] for t in after["topics"]] == ["rust"]
    assert after["title"] == opp["title"] and after["partner_internal_name"] == opp["partner_internal_name"]
    assert _count("SELECT count(*) FROM opportunity_topic") == 1


def test_state_transitions_set_published_and_closed_timestamps(client, admin_headers, create_opportunity):
    opp = create_opportunity()
    path = f"/api/admin/opportunities/{opp['id']}"
    published = client.patch(path, json={"status": "open"}, headers=admin_headers).json()["data"]["opportunity"]
    assert published["status"] == "open" and published["published_at"]
    closed = client.patch(path, json={"status": "closed"}, headers=admin_headers).json()["data"]["opportunity"]
    assert closed["status"] == "closed" and closed["closed_at"]
    assert closed["published_at"] == published["published_at"]
    reopened = client.patch(path, json={"status": "open"}, headers=admin_headers).json()["data"]["opportunity"]
    assert reopened["status"] == "open" and reopened["closed_at"] is None
    assert reopened["published_at"] == published["published_at"]  # never reset
    draft = client.patch(path, json={"status": "draft"}, headers=admin_headers).json()["data"]["opportunity"]
    assert draft["status"] == "draft" and draft["published_at"] == published["published_at"]


def test_unknown_ids_are_404(client, admin_headers):
    assert client.get("/api/admin/opportunities/4242", headers=admin_headers).status_code == 404
    response = client.patch("/api/admin/opportunities/4242", json={"title": "Hello"}, headers=admin_headers)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "not_found"


def test_create_null_description_is_stored_as_empty_string(client, admin_headers, topic_ids):
    response = client.post(
        "/api/admin/opportunities", json=_with(topic_ids, description_md=None), headers=admin_headers
    )
    assert response.status_code == 200, response.text
    opp = response.json()["data"]["opportunity"]
    assert opp["description_md"] == ""
    assert _count("SELECT count(*) FROM opportunity WHERE description_md = ''") == 1
    detail = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()["data"]
    assert detail["opportunity"]["description_md"] == ""


def test_create_null_location_mode_and_status_take_the_spec_defaults(client, admin_headers, topic_ids):
    body = _with(topic_ids, location_mode=None, status=None, city="Pune")
    response = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
    assert response.status_code == 200, response.text
    opp = response.json()["data"]["opportunity"]
    assert opp["location_mode"] == "remote" and opp["city"] is None  # remote forces city null
    assert opp["status"] == opp["stored_status"] == "draft" and opp["published_at"] is None
    assert _count("SELECT count(*) FROM opportunity WHERE status = 'draft' AND location_mode = 'remote'") == 1


def test_create_null_required_field_is_still_rejected(client, admin_headers, topic_ids):
    response = client.post("/api/admin/opportunities", json=_with(topic_ids, title=None), headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"
    assert response.json()["detail"]["message"].startswith("title: ")
    assert _count("SELECT count(*) FROM opportunity") == 0


@pytest.mark.parametrize("bad_id", ["0", "-1", "abc", str(2**31), str(2**63), "9" * 40])
def test_out_of_range_or_non_numeric_path_ids_are_404_not_500(client, admin_headers, bad_id):
    get = client.get(f"/api/admin/opportunities/{bad_id}", headers=admin_headers)
    assert get.status_code == 404, get.text
    assert get.json()["detail"] == {"code": "not_found", "message": "No opportunity matches this id."}
    patch = client.patch(f"/api/admin/opportunities/{bad_id}", json={"title": "Hello"}, headers=admin_headers)
    assert patch.status_code == 404, patch.text
    assert patch.json()["detail"]["code"] == "not_found"
    topic = client.patch(f"/api/admin/topics/{bad_id}", json={"active": False}, headers=admin_headers)
    assert topic.status_code == 404, topic.text
    assert topic.json()["detail"] == {"code": "not_found", "message": "No topic matches this id."}
    assert _count("SELECT count(*) FROM facilitator_action") == 0


@pytest.mark.parametrize("bad_topic", [2**31, 2**63, -5, 0])
def test_out_of_range_topic_ids_are_a_validation_error_not_500(
    client, admin_headers, topic_ids, create_opportunity, bad_topic
):
    created = client.post(
        "/api/admin/opportunities",
        json=_with(topic_ids, topic_ids=[topic_ids["python"], bad_topic]),
        headers=admin_headers,
    )
    assert created.status_code == 422, created.text
    assert created.json()["detail"] == {
        "code": "validation_error", "message": f"topic_ids: topic {bad_topic} does not exist",
    }
    assert _count("SELECT count(*) FROM opportunity") == 0
    opp = create_opportunity(["python"])
    patched = client.patch(
        f"/api/admin/opportunities/{opp['id']}", json={"topic_ids": [bad_topic]}, headers=admin_headers
    )
    assert patched.status_code == 422, patched.text
    assert patched.json()["detail"]["message"] == f"topic_ids: topic {bad_topic} does not exist"
    assert _count("SELECT count(*) FROM opportunity_topic") == 1


# --------------------------------------------------------------------------- list


def test_counts_filters_and_pagination_over_the_board_fixture(client, admin_headers, board):
    data = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]
    assert data["counts"] == {"draft": 3, "open": 30, "expired": 3, "closed": 3}
    assert data["total"] == 39 and data["page_size"] == 25 and data["total_pages"] == 2
    assert len(data["opportunities"]) == 25
    second = client.get("/api/admin/opportunities", params={"page": 2}, headers=admin_headers).json()["data"]
    assert len(second["opportunities"]) == 14
    ids = [o["id"] for o in data["opportunities"] + second["opportunities"]]
    assert len(set(ids)) == 39
    row = data["opportunities"][0]
    assert set(row) == ADMIN_FULL_KEYS - {"description_md", "internal_notes"}
    stamps = [(o["updated_at"], o["id"]) for o in data["opportunities"]]
    assert stamps == sorted(stamps, reverse=True)

    for status, expected in (("draft", board["draft_ids"]), ("closed", board["closed_ids"]),
                             ("expired", board["expired_ids"])):
        filtered = client.get(
            "/api/admin/opportunities", params={"status": status}, headers=admin_headers
        ).json()["data"]
        assert {o["id"] for o in filtered["opportunities"]} == set(expected)
        assert all(o["status"] == status for o in filtered["opportunities"])
        assert filtered["counts"] == data["counts"]  # counts ignore filters
    open_rows = client.get(
        "/api/admin/opportunities", params={"status": "open", "page_size": 100}, headers=admin_headers
    ).json()["data"]
    assert {o["id"] for o in open_rows["opportunities"]} == set(board["open_ids"])
    typed = client.get(
        "/api/admin/opportunities", params={"type": "role", "page_size": 100}, headers=admin_headers
    ).json()["data"]
    assert {o["id"] for o in typed["opportunities"]} == board["by_type"]["role"] | set(board["draft_ids"])


def test_q_matches_internal_partner_name_case_insensitively(client, admin_headers, board, create_opportunity):
    target = create_opportunity(partner_internal_name="Acme Payments Pvt Ltd", partner_display_name="A fintech",
                                title="Something else")
    for q in ("acme payments", "ACME", "pvt ltd"):
        rows = client.get("/api/admin/opportunities", params={"q": q}, headers=admin_headers).json()["data"]
        assert [o["id"] for o in rows["opportunities"]] == [target["id"]], q
    by_title = client.get("/api/admin/opportunities", params={"q": "open listing 0"}, headers=admin_headers)
    assert by_title.json()["data"]["total"] == 10
    by_display = client.get("/api/admin/opportunities", params={"q": "a FINTECH"}, headers=admin_headers)
    assert [o["id"] for o in by_display.json()["data"]["opportunities"]] == [target["id"]]
    literal = client.get("/api/admin/opportunities", params={"q": "%"}, headers=admin_headers)
    assert literal.json()["data"]["total"] == 0  # LIKE wildcards are escaped


def test_admin_list_validation(client, admin_headers):
    for params, start in (({"status": "gone"}, "status:"), ({"type": "gig"}, "type:"),
                          ({"page_size": 101}, "page_size:"), ({"page": 0}, "page:")):
        response = client.get("/api/admin/opportunities", params=params, headers=admin_headers)
        assert response.status_code == 422, params
        assert response.json()["detail"]["message"].startswith(start)


def test_empty_admin_list(client, admin_headers):
    data = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]
    assert data == {
        "opportunities": [], "page": 1, "page_size": 25, "total": 0, "total_pages": 0,
        "counts": {"draft": 0, "open": 0, "expired": 0, "closed": 0},
    }
