"""C10 Public opportunity board — list (filters, sorts, pagination), detail, expiry
boundary (PostgreSQL). The `board` fixture (tests/conftest.py) holds 30 open listings
plus 3 drafts, 3 closed and 3 expired, so a truncated or unfiltered result differs."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import BOARD_TYPES, db_execute, iso

CARD_KEYS = {
    "id", "title", "type", "summary", "partner_display_name", "topics", "location_mode",
    "city", "locations", "starts_on", "ends_on", "duration_text", "compensation_text", "deadline",
    "compensation_min", "compensation_max", "compensation_currency", "compensation_unit",
    "published_at", "status", "public_url",
}


def _list(client, **params) -> dict:
    response = client.get("/api/public/opportunities", params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _all_pages(client, **params) -> list[list[int]]:
    pages = []
    for page in (1, 2, 3):
        data = _list(client, page=page, page_size=12, **params)
        assert data["total"] == 30 and data["total_pages"] == 3 and data["page"] == page
        pages.append([o["id"] for o in data["opportunities"]])
    return pages


# --------------------------------------------------------------------------- list


@pytest.mark.parametrize("sort", ["newest", "deadline"])
def test_three_pages_of_12_12_6_cover_exactly_the_30_open_ids(client, board, sort):
    pages = _all_pages(client, sort=sort)
    assert [len(p) for p in pages] == [12, 12, 6]
    flat = [i for p in pages for i in p]
    assert len(flat) == len(set(flat)) == 30
    assert set(flat) == set(board["open_ids"])
    beyond = _list(client, page=4, page_size=12, sort=sort)
    assert beyond["opportunities"] == [] and beyond["total"] == 30 and beyond["total_pages"] == 3


def test_newest_sort_is_published_at_desc_and_deadline_sort_is_deadline_asc(client, board):
    newest = [o for p in (1, 2, 3) for o in _list(client, page=p, page_size=12)["opportunities"]]
    published = [o["published_at"] for o in newest]
    assert published == sorted(published, reverse=True)
    assert [o["id"] for o in newest] != sorted(o["id"] for o in newest)  # not just id order

    by_deadline = [
        o for p in (1, 2, 3)
        for o in _list(client, page=p, page_size=12, sort="deadline")["opportunities"]
    ]
    deadlines = [o["deadline"] for o in by_deadline]
    assert deadlines == sorted(deadlines)
    assert [o["id"] for o in by_deadline] == board["open_ids"]  # created with deadline +1..+30 days


def test_default_page_size_is_12_and_total_ignores_non_open(client, board):
    data = _list(client)
    assert data["page"] == 1 and data["page_size"] == 12 and data["total"] == 30
    assert len(data["opportunities"]) == 12
    card = data["opportunities"][0]
    assert set(card) == CARD_KEYS
    assert card["status"] == "open"
    assert card["public_url"] == f"http://testserver/opportunities/{card['id']}"
    hidden = set(board["draft_ids"] + board["closed_ids"] + board["expired_ids"])
    every = {o["id"] for o in _list(client, page_size=50)["opportunities"]}
    assert len(every) == 30 and not every & hidden


@pytest.mark.parametrize("kind", BOARD_TYPES)
def test_each_type_filter_returns_exactly_its_precomputed_set(client, board, kind):
    data = _list(client, type=kind, page_size=50)
    assert {o["id"] for o in data["opportunities"]} == board["by_type"][kind]
    assert data["total"] == len(board["by_type"][kind]) and data["total"] < 30
    assert all(o["type"] == kind for o in data["opportunities"])


def test_two_slug_topic_filter_matches_any(client, board):
    expected = board["by_topic"]["kubernetes"] | board["by_topic"]["ux-design"]
    data = _list(client, topic=["kubernetes", "ux-design"], page_size=50)
    assert {o["id"] for o in data["opportunities"]} == expected
    assert data["total"] == len(expected)
    assert expected != board["by_topic"]["kubernetes"] and expected != board["by_topic"]["ux-design"]


def test_topic_filter_combined_with_type_and_open_only(client, board):
    # python is also on every draft, closed and expired listing: none may appear.
    expected = board["by_topic"]["python"] & board["by_type"]["workshop"]
    data = _list(client, topic="python", type="workshop", page_size=50)
    assert {o["id"] for o in data["opportunities"]} == expected and expected


def test_unknown_slug_matches_nothing(client, board):
    data = _list(client, topic="no-such-topic")
    assert data == {"opportunities": [], "page": 1, "page_size": 12, "total": 0, "total_pages": 0}
    mixed = _list(client, topic=["no-such-topic", "aws"], page_size=50)
    assert {o["id"] for o in mixed["opportunities"]} == board["by_topic"]["aws"]


def test_empty_board_returns_zero_pages(client):
    assert _list(client) == {"opportunities": [], "page": 1, "page_size": 12, "total": 0, "total_pages": 0}


@pytest.mark.parametrize(
    ("params", "message_start"),
    [
        ({"type": "gig"}, "type: must be one of workshop, engagement, role, cofacilitation"),
        ({"sort": "oldest"}, "sort: must be one of newest, deadline"),
        ({"page": 0}, "page:"),
        ({"page_size": 51}, "page_size:"),
        ({"page_size": 0}, "page_size:"),
    ],
)
def test_invalid_query_params_are_validation_errors(client, params, message_start):
    response = client.get("/api/public/opportunities", params=params)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error" and detail["message"].startswith(message_start)


# --------------------------------------------------------------------------- detail


def test_detail_of_open_closed_and_expired_draft_is_404(client, board):
    open_id = board["open_ids"][0]
    detail = client.get(f"/api/public/opportunities/{open_id}").json()["data"]["opportunity"]
    assert set(detail) == CARD_KEYS | {"description_md"}
    assert detail["status"] == "open" and "```python" in detail["description_md"]

    closed = client.get(f"/api/public/opportunities/{board['closed_ids'][0]}")
    assert closed.status_code == 200 and closed.json()["data"]["opportunity"]["status"] == "closed"
    expired = client.get(f"/api/public/opportunities/{board['expired_ids'][0]}")
    assert expired.status_code == 200 and expired.json()["data"]["opportunity"]["status"] == "expired"

    for path in (board["draft_ids"][0], 999999, "abc", "-1"):
        response = client.get(f"/api/public/opportunities/{path}")
        assert response.status_code == 404, path
        assert response.json()["detail"] == {
            "code": "not_found", "message": "This opportunity isn't available."
        }


@pytest.mark.parametrize(
    "raw_id",
    ["0", "-1", "abc", str(2**31), "9999999999", str(2**63), "9" * 40, "١٢"],
)
def test_malformed_or_out_of_range_detail_id_is_404_never_500(client, raw_id):
    # Ids above PostgreSQL INTEGER max must not reach the DB (they would overflow → 500).
    response = client.get(f"/api/public/opportunities/{raw_id}")
    assert response.status_code == 404, raw_id
    assert response.json()["detail"] == {
        "code": "not_found", "message": "This opportunity isn't available."
    }


def test_card_shape_for_a_hybrid_listing_with_dates(client, create_opportunity):
    opp = create_opportunity(
        ["generative-ai", "prompt-engineering"],
        status="open", location_mode="hybrid", city="  Bengaluru ",
        starts_on="2026-12-05", ends_on="2026-12-06", duration_text="2 days",
        compensation_text="Paid — day rate", partner_display_name="   ",
    )
    card = _list(client)["opportunities"][0]
    assert card["id"] == opp["id"]
    assert card["city"] == "Bengaluru" and card["location_mode"] == "hybrid"
    assert card["starts_on"] == "2026-12-05" and card["ends_on"] == "2026-12-06"
    assert card["partner_display_name"] is None  # blank → null (UI shows the network name)
    assert card["topics"] == [
        {"slug": "generative-ai", "name": "Generative AI & LLMs"},
        {"slug": "prompt-engineering", "name": "Prompt Engineering"},
    ]
    assert card["deadline"].endswith("Z") and card["published_at"].endswith("Z")


# --------------------------------------------------------------------------- expiry


def test_expiry_boundary_minus_one_second_vs_plus_sixty(client, admin_headers, create_opportunity):
    soon = create_opportunity(["aws"], status="open", deadline=iso(datetime.now(timezone.utc) + timedelta(seconds=60)))
    gone = create_opportunity(["aws"], status="open")
    db_execute(
        "UPDATE opportunity SET deadline = :d WHERE id = :id",
        d=datetime.now(timezone.utc) - timedelta(seconds=1), id=gone["id"],
    )

    listed = {o["id"] for o in _list(client)["opportunities"]}
    assert listed == {soon["id"]}
    assert client.get(f"/api/public/opportunities/{soon['id']}").json()["data"]["opportunity"]["status"] == "open"
    gone_public = client.get(f"/api/public/opportunities/{gone['id']}")
    assert gone_public.status_code == 200
    assert gone_public.json()["data"]["opportunity"]["status"] == "expired"

    admin = client.get(f"/api/admin/opportunities/{gone['id']}", headers=admin_headers).json()["data"]
    assert admin["opportunity"]["status"] == "expired" and admin["opportunity"]["stored_status"] == "open"
    expired_tab = client.get("/api/admin/opportunities", params={"status": "expired"}, headers=admin_headers)
    assert [o["id"] for o in expired_tab.json()["data"]["opportunities"]] == [gone["id"]]
    topics = {t["slug"]: t["open_count"] for t in client.get("/api/public/topics").json()["data"]["topics"]}
    assert topics["aws"] == 1


def test_extending_an_expired_deadline_reopens_with_no_other_change(client, admin_headers, create_opportunity):
    opp = create_opportunity(["aws"], status="open")
    db_execute(
        "UPDATE opportunity SET deadline = :d WHERE id = :id",
        d=datetime.now(timezone.utc) - timedelta(minutes=5), id=opp["id"],
    )
    before = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()["data"]["opportunity"]
    assert before["status"] == "expired"

    # editing another field of an expired listing is allowed and leaves it expired
    edited = client.patch(f"/api/admin/opportunities/{opp['id']}", json={"summary": "New summary"}, headers=admin_headers)
    assert edited.status_code == 200 and edited.json()["data"]["opportunity"]["status"] == "expired"

    new_deadline = iso(datetime.now(timezone.utc) + timedelta(days=3))
    response = client.patch(
        f"/api/admin/opportunities/{opp['id']}", json={"deadline": new_deadline}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    after = response.json()["data"]["opportunity"]
    assert after["status"] == "open" and after["stored_status"] == "open"
    assert after["deadline"] == new_deadline
    assert after["published_at"] == before["published_at"]
    assert after["closed_at"] is None
    assert {o["id"] for o in _list(client)["opportunities"]} == {opp["id"]}
    activity = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()["data"]["activity"]
    assert activity[0]["action"] == "opportunity.update"
    assert activity[0]["detail"]["changed_fields"] == ["deadline"]
