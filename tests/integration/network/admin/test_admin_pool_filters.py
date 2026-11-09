"""C13 Admin trainer pool — q / topic (ANY) / verified / tag filters over the 60-profile
fixture, each walked across exactly 3 pages and compared with the precomputed id set;
CSV export row count = filtered total (PostgreSQL)."""

from __future__ import annotations

import csv
import io
import re

import pytest

from tests.integration.network.admin.pool_seed import CV_TEXT_SENTINEL, NEEDLE, POOL_TAG

ROW_KEYS = {
    "id", "user_id", "display_name", "email", "avatar_url", "headline", "city", "remote_ok",
    "topics", "rate", "verified", "completeness_pct", "tags", "created_at", "updated_at",
}


def _walk(client, admin_headers, params: list[tuple[str, str]], page_size: int) -> tuple[list[int], dict]:
    """Fetch every page; returns (ids in order, first page body)."""
    first = None
    ids: list[int] = []
    page = 1
    while True:
        response = client.get(
            "/api/admin/network/trainers",
            params=params + [("page", str(page)), ("page_size", str(page_size))],
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        first = first or data
        assert data["page"] == page and data["page_size"] == page_size
        assert len(data["trainers"]) <= page_size
        ids.extend(row["id"] for row in data["trainers"])
        if page >= data["total_pages"]:
            break
        page += 1
    return ids, first


CASES = [
    # (label, params, page_size, expected-set getter)
    ("q", [("q", NEEDLE.upper())], 10, lambda p: p.by_q),
    ("topic-any", [("topic", "python"), ("topic", "kubernetes")], 10,
     lambda p: p.by_topic["python"] | p.by_topic["kubernetes"]),
    ("verified", [("verified", "true")], 12, lambda p: p.verified),
    ("unverified", [("verified", "false")], 12, lambda p: p.unverified),
    ("tag", [("tag", POOL_TAG.upper())], 7, lambda p: p.by_tag[POOL_TAG]),
]


@pytest.mark.parametrize(("label", "params", "page_size", "expected"), CASES, ids=[c[0] for c in CASES])
def test_filter_returns_precomputed_set_across_three_pages(
    client, admin_headers, pool60, label, params, page_size, expected
):
    want = expected(pool60)
    ids, first = _walk(client, admin_headers, params, page_size)
    assert first["total"] == len(want)
    assert first["total_pages"] == 3, f"{label}: fixture must span exactly 3 pages"
    assert len(ids) == len(set(ids)), "no row may appear on two pages"
    assert set(ids) == want
    # newest first == fixture index ascending
    order = [pool60.ids.index(i) for i in ids]
    assert order == sorted(order)


def test_combined_filters_intersect(client, admin_headers, pool60):
    want = pool60.verified & pool60.by_topic["python"] & pool60.by_tag["mentor"]
    ids, first = _walk(
        client, admin_headers,
        [("verified", "true"), ("topic", "python"), ("tag", "mentor")], 25,
    )
    assert want, "fixture must make this intersection non-empty"
    assert set(ids) == want and first["total"] == len(want)


def test_row_shape_is_the_contract_and_rate_unit_is_shown_as_stored(client, admin_headers, pool60):
    response = client.get(
        "/api/admin/network/trainers", params={"page_size": 100}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total"] == 60 and len(data["trainers"]) == 60 and data["total_pages"] == 1
    rows = {row["id"]: row for row in data["trainers"]}
    for row in rows.values():
        assert set(row) == ROW_KEYS
        assert isinstance(row["completeness_pct"], int) and 0 <= row["completeness_pct"] <= 100
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["created_at"])
        for topic in row["topics"]:
            assert set(topic) == {"slug", "name", "level"}
    units = set()
    for i, pid in enumerate(pool60.ids):
        row = rows[pid]
        if i % 2:
            assert row["rate"]["min"] == 1000 + i and row["rate"]["max"] == 2000 + i
            assert row["rate"]["currency"] == "INR"
            units.add(row["rate"]["unit"])
        else:
            assert row["rate"] is None
    assert units == {"hour", "day", "course", "month"}
    zero = rows[pool60.ids[0]]
    # display order = topic position (Languages < AI & Data < Cloud & DevOps)
    assert [(t["slug"], t["level"]) for t in zero["topics"]] == [
        ("python", "advanced"), ("generative-ai", "intermediate"), ("kubernetes", "expert"),
    ]
    assert zero["topics"][0]["name"] == "Python"


def test_empty_pool_and_no_match(client, admin_headers):
    response = client.get("/api/admin/network/trainers", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data == {"trainers": [], "page": 1, "page_size": 25, "total": 0, "total_pages": 0}


def test_unknown_topic_and_wildcard_q_match_nothing(client, admin_headers, pool60):
    for params in ({"topic": "no-such-topic"}, {"q": "%"}, {"q": "_"}, {"tag": "nope"}):
        response = client.get("/api/admin/network/trainers", params=params, headers=admin_headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["total"] == 0, params


@pytest.mark.parametrize(
    "params", [{"page_size": "101"}, {"page_size": "0"}, {"page": "0"}, {"verified": "maybe"}]
)
def test_bad_query_params_are_validation_errors(client, admin_headers, params):
    response = client.get("/api/admin/network/trainers", params=params, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


# --------------------------------------------------------------------------- CSV


def _csv_rows(response) -> list[dict]:
    raw = response.content.decode("utf-8")
    assert raw.startswith("\ufeff"), "CSV must start with a UTF-8 BOM"
    return list(csv.DictReader(io.StringIO(raw.lstrip("\ufeff"))))


@pytest.mark.parametrize(
    "params",
    [
        [],
        [("q", NEEDLE)],
        [("topic", "python"), ("topic", "kubernetes")],
        [("verified", "true")],
        [("tag", POOL_TAG)],
        [("verified", "false"), ("topic", "generative-ai")],
    ],
    ids=["all", "q", "topic-any", "verified", "tag", "combined"],
)
def test_csv_row_count_equals_filtered_total(client, admin_headers, pool60, params):
    listing = client.get(
        "/api/admin/network/trainers", params=params + [("page_size", "5")], headers=admin_headers
    ).json()["data"]
    response = client.get("/api/admin/network/trainers.csv", params=params, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert re.fullmatch(
        r'attachment; filename="workshop0-trainers-\d{8}\.csv"',
        response.headers["content-disposition"],
    )
    rows = _csv_rows(response)
    assert len(rows) == listing["total"]
    ids = {int(r["id"]) for r in rows}
    page_ids, _ = _walk(client, admin_headers, params, 100)
    assert ids == set(page_ids)
    assert CV_TEXT_SENTINEL not in response.text, "CSV must never include CV text"


def test_csv_columns_and_values(client, admin_headers, pool60):
    rows = _csv_rows(client.get("/api/admin/network/trainers.csv", headers=admin_headers))
    by_id = {int(r["id"]): r for r in rows}
    one = by_id[pool60.ids[1]]
    assert one["email"] == pool60.emails[1]
    assert one["rate_min"] == "1001" and one["rate_unit"] == "hour" and one["rate_currency"] == "INR"
    assert one["verified"] == "false" and one["tags"] == POOL_TAG
    three = by_id[pool60.ids[3]]
    assert three["rate_unit"] == "day"
    zero = by_id[pool60.ids[0]]
    assert set(zero["topics"].split("; ")) == {"python:advanced", "kubernetes:expert", "generative-ai:intermediate"}
    assert zero["verified"] == "true" and zero["rate_min"] == ""


def test_csv_neutralises_formula_cells(client, admin_headers):
    from src.workshop0.db.session import create_db_session
    from tests.integration.network.admin.pool_seed import seed_profile

    with create_db_session() as session:
        seed_profile(session, email="evil@example.test", display_name="=HYPERLINK(1)", headline="+cmd")
    rows = _csv_rows(client.get("/api/admin/network/trainers.csv", headers=admin_headers))
    assert rows[0]["display_name"] == "'=HYPERLINK(1)" and rows[0]["headline"] == "'+cmd"


def test_csv_with_no_match_is_header_only(client, admin_headers, pool60):
    response = client.get(
        "/api/admin/network/trainers.csv", params={"q": "zzz-nothing"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert _csv_rows(response) == []
    assert response.content.decode("utf-8").lstrip("\ufeff").startswith("id,display_name,email,")
