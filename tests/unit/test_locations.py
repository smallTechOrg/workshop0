"""Phase 11c location helpers (spec/data-model.md §Phase 11c) — pure, no DB."""

import json

from src.workshop0.services.locations import (
    CITY_MAX,
    COUNTRY_MAX,
    LOCATIONS_MAX,
    collapse,
    dedupe,
    dump,
    location_key,
    parse_stored,
)


def test_constants():
    assert (CITY_MAX, COUNTRY_MAX, LOCATIONS_MAX) == (80, 80, 10)


def test_collapse_trims_and_collapses_internal_whitespace():
    assert collapse("  New   Delhi \t") == "New Delhi"
    assert collapse("   ") == ""
    assert collapse("Zürich") == "Zürich"


def test_location_key_ignores_case_and_whitespace_but_keeps_country():
    assert location_key(" PUNE ", None) == location_key("pune", "") == ("pune", "")
    assert location_key("Pune", None) != location_key("Pune", "India")
    assert location_key("pune", " india ") == location_key("PUNE", "INDIA")


def test_dedupe_first_wins_order_kept_exact_keys():
    items = [
        {"city": "Pune", "country": None},
        {"city": "Bengaluru", "country": "India"},
        {"city": "PUNE", "country": None},
        {"city": "Pune", "country": "India"},
    ]
    out = dedupe(items)
    assert out == [
        {"city": "Pune", "country": None},
        {"city": "Bengaluru", "country": "India"},
        {"city": "Pune", "country": "India"},
    ]
    assert all(set(i) == {"city", "country"} for i in out)
    assert dedupe([]) == []


def test_parse_stored_returns_a_non_empty_list():
    stored = [{"city": "Bengaluru", "country": "India"}, {"city": "Pune", "country": None}]
    assert parse_stored(dump(stored), "Stale", "hybrid") == stored


def test_parse_stored_fallback_for_empty_list_with_city_onsite():
    assert parse_stored("[]", "  Navi   Mumbai ", "onsite") == [{"city": "Navi Mumbai", "country": None}]


def test_parse_stored_remote_never_falls_back():
    assert parse_stored("[]", "Pune", "remote") == []


def test_parse_stored_invalid_json_falls_back_for_hybrid():
    assert parse_stored("{not json", "Pune", "hybrid") == [{"city": "Pune", "country": None}]


def test_parse_stored_none_and_no_city_is_empty():
    assert parse_stored(None, None, "onsite") == []
    assert parse_stored("[]", "   ", "onsite") == []


def test_dump_keeps_unicode():
    assert dump([{"city": "Zürich", "country": None}]) == '[{"city": "Zürich", "country": null}]'
    assert json.loads(dump([])) == []
