"""GET /api/admin/network/trainers rule filters (spec/api.md §Phase 12)."""

from __future__ import annotations

from tests.fixtures.network_pool import seed_pool
from src.workshop0.db.session import create_db_session

URL = "/api/admin/network/trainers"


def _ids(client, headers, **params) -> set[int]:
    r = client.get(URL, params={"page_size": 100, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return {t["id"] for t in r.json()["data"]["trainers"]}


def _pool():
    with create_db_session() as session:
        return seed_pool(session)


def test_no_extended_filter_returns_everyone(client, admin_headers):
    pool = _pool()
    assert _ids(client, admin_headers) == set(pool.profile_ids)


def test_topic_with_min_level(client, admin_headers):
    pool = _pool()
    got = _ids(client, admin_headers, topic="generative-ai", min_level="advanced")
    assert pool.best_id in got and got.isdisjoint(pool.by_reason["level"]) and got.isdisjoint(pool.by_reason["topic"])
    assert _ids(client, admin_headers, min_level="expert") >= {pool.best_id}


def test_budget_needs_currency_and_unit_and_filters_rate(client, admin_headers):
    pool = _pool()
    got = _ids(client, admin_headers, budget_max=10000, currency="inr", unit="day")
    assert got.isdisjoint(pool.by_reason["rate"]) and pool.best_id in got
    r = client.get(URL, params={"budget_max": 10000}, headers=admin_headers)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "validation_error"


def test_availability_window_and_location(client, admin_headers):
    pool = _pool()
    got = _ids(client, admin_headers, available_start="2027-03-01", available_end="2027-03-02")
    assert got.isdisjoint(pool.by_reason["blackout"] | pool.by_reason["available_from"]) and pool.best_id in got
    onsite = _ids(client, admin_headers, location_mode="onsite", city="PUNE")
    assert pool.best_id in onsite and onsite.isdisjoint(pool.by_reason["city"])
    hybrid = _ids(client, admin_headers, location_mode="hybrid", city="Pune")
    assert hybrid >= pool.by_reason["city"]  # remote_ok trainers qualify for hybrid


def test_combined_filters_and_csv_row_count_agree(client, admin_headers):
    pool = _pool()
    params = {"topic": "python", "min_level": "advanced", "verified": "true", "location_mode": "onsite", "city": "Pune"}
    got = _ids(client, admin_headers, **params)
    assert pool.best_id in got and got <= pool.eligible_ids and len(got) >= 2  # verified + python>=advanced + onsite Pune
    assert got.isdisjoint(pool.by_reason['city'] | pool.by_reason['level'])
    csv = client.get("/api/admin/network/trainers.csv", params=params, headers=admin_headers)
    assert csv.status_code == 200 and len(csv.text.strip().splitlines()) == 1 + len(got)


def test_invalid_values_are_validation_errors(client, admin_headers):
    _pool()
    for params in ({"min_level": "guru"}, {"location_mode": "moon"}, {"available_start": "tomorrow"},
                   {"available_start": "2027-03-05", "available_end": "2027-03-01"}):
        r = client.get(URL, params=params, headers=admin_headers)
        assert r.status_code == 422 and r.json()["detail"]["code"] == "validation_error", params
