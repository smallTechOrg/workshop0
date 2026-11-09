"""Leak proof: no public response ever carries the internal partner name, the internal
notes, or the admin-only keys — checked on the RAW response text (PostgreSQL)."""

from tests.conftest import BOARD_TOPICS, BOARD_TYPES, INTERNAL_NOTE_SENTINEL, INTERNAL_PARTNER_SENTINEL

PARTNER_NOTE_SENTINEL = "ZZ-PARTNER-NOTE-4b2e"
FORBIDDEN = (
    INTERNAL_PARTNER_SENTINEL,
    INTERNAL_NOTE_SENTINEL,
    "partner_internal_name",
    "internal_notes",
    "stored_status",
    PARTNER_NOTE_SENTINEL,
    "partner_id",
    '"partner"',
    "name_key",
    '"notes"',
    "locations_json",
)


def _assert_clean(response) -> None:
    assert response.status_code == 200, response.text
    for needle in FORBIDDEN:
        assert needle not in response.text, (response.url, needle)
    data = response.json()["data"]
    cards = data.get("opportunities") or ([data["opportunity"]] if "opportunity" in data else [])
    for card in cards:  # Phase 11c: every Location has exactly {city, country}
        assert isinstance(card["locations"], list)
        for item in card["locations"]:
            assert set(item) == {"city", "country"}, (response.url, item)


def _give_partner_notes(client, admin_headers) -> int:
    partners = client.get("/api/admin/partners", headers=admin_headers).json()["data"]["partners"]
    sentinel = [p for p in partners if p["internal_name"] == INTERNAL_PARTNER_SENTINEL]
    assert len(sentinel) == 1
    response = client.patch(
        f"/api/admin/partners/{sentinel[0]['id']}",
        json={"notes": PARTNER_NOTE_SENTINEL},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    return sentinel[0]["id"]


def test_no_public_endpoint_leaks_internal_fields(client, admin_headers, board, create_opportunity):
    partner_id = _give_partner_notes(client, admin_headers)
    # Phase 11c: one open multi-location listing so `locations` items are really checked
    multi = create_opportunity(
        status="open", location_mode="hybrid",
        partner_internal_name=INTERNAL_PARTNER_SENTINEL, internal_notes=INTERNAL_NOTE_SENTINEL,
        locations=[{"city": "Bengaluru", "country": "India"}, {"city": "Pune"}],
    )
    _assert_clean(client.get(f"/api/public/opportunities/{multi['id']}"))
    # sanity: the sentinels really are stored and visible to admins
    admin = client.get(f"/api/admin/opportunities/{board['open_ids'][0]}", headers=admin_headers)
    assert INTERNAL_PARTNER_SENTINEL in admin.text and INTERNAL_NOTE_SENTINEL in admin.text
    assert admin.json()["data"]["opportunity"]["partner_id"] == partner_id
    assert PARTNER_NOTE_SENTINEL not in admin.text  # PartnerRef never carries notes
    # the public display name IS public
    card = client.get(f"/api/public/opportunities/{board['open_ids'][0]}")
    assert "A Bengaluru fintech" in card.text

    _assert_clean(client.get("/api/public/topics"))
    for sort in ("newest", "deadline"):
        for page in (1, 2, 3):
            _assert_clean(client.get("/api/public/opportunities", params={"page": page, "sort": sort}))
    _assert_clean(client.get("/api/public/opportunities", params={"page_size": 50}))
    for kind in BOARD_TYPES:
        response = client.get("/api/public/opportunities", params={"type": kind, "page_size": 50})
        _assert_clean(response)
        assert response.json()["data"]["total"] > 0
    _assert_clean(client.get("/api/public/opportunities", params={"topic": list(BOARD_TOPICS)}))
    for opportunity_id in board["open_ids"][:3] + board["expired_ids"] + board["closed_ids"]:
        _assert_clean(client.get(f"/api/public/opportunities/{opportunity_id}"))


def test_not_found_responses_do_not_leak_either(client, board):
    response = client.get(f"/api/public/opportunities/{board['draft_ids'][0]}")
    assert response.status_code == 404
    for needle in FORBIDDEN:
        assert needle not in response.text


# --------------------------------------------------------------------------- Phase 11e
SEO_FORBIDDEN = (
    *FORBIDDEN,
    "Acme Payments Pvt Ltd",  # the factory's default internal partner name
    "Contact: R. Rao",  # the factory's default internal note
    "ZZ-DRAFT-TITLE",
)


def _assert_html_clean(response, status: int) -> None:
    assert response.status_code == status, response.text
    for needle in SEO_FORBIDDEN:
        assert needle not in response.text, (response.url, needle)


def test_seo_html_and_sitemap_do_not_leak(
    client, admin_headers, board, create_opportunity, monkeypatch, tmp_path
):
    import src.workshop0.api.seo as seo_api

    view = tmp_path / "view.html"
    view.write_text("<html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(seo_api, "VIEW_HTML", view)
    _give_partner_notes(client, admin_headers)
    multi = create_opportunity(
        status="open", location_mode="hybrid",
        partner_internal_name=INTERNAL_PARTNER_SENTINEL, internal_notes=INTERNAL_NOTE_SENTINEL,
        locations=[{"city": "Bengaluru", "country": "India"}, {"city": "Pune"}],
    )
    draft = create_opportunity(
        title="ZZ-DRAFT-TITLE", partner_internal_name=INTERNAL_PARTNER_SENTINEL,
        internal_notes=INTERNAL_NOTE_SENTINEL,
    )

    def slug_of(oid: int) -> str:
        response = client.get(f"/api/admin/opportunities/{oid}", headers=admin_headers)
        return response.json()["data"]["opportunity"]["slug"]

    ids = [multi["id"], *board["open_ids"][:3], *board["expired_ids"], *board["closed_ids"]]
    for oid in ids:
        response = client.get(f"/opportunities/{slug_of(oid)}", follow_redirects=False)
        _assert_html_clean(response, 200)
        assert 'rel="canonical"' in response.text
    for key in (draft["slug"], str(draft["id"]), slug_of(board["draft_ids"][0])):
        response = client.get(f"/opportunities/{key}", follow_redirects=False)
        _assert_html_clean(response, 404)
        assert "Draft 0" not in response.text
    sitemap = client.get("/sitemap.xml")
    _assert_html_clean(sitemap, 200)
    assert draft["slug"] not in sitemap.text
    _assert_html_clean(client.get("/robots.txt"), 200)
