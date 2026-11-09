"""F3 — structured compensation: validation (exact messages), merge semantics, public allow-list."""

import pytest

from tests.conftest import opportunity_body


def _post(client, headers, topic_ids, **over):
    return client.post(
        "/api/admin/opportunities", json=opportunity_body([topic_ids["python"]], **over), headers=headers
    )


def _msg(response):
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "validation_error"
    return response.json()["detail"]["message"]


@pytest.mark.parametrize("unit", ["hour", "day", "course", "month"])
def test_each_unit_round_trips_to_admin_and_public(client, admin_headers, topic_ids, unit):
    response = _post(
        client, admin_headers, topic_ids, compensation_min=8000, compensation_max=12000,
        compensation_currency="INR", compensation_unit=unit, compensation_text="plus travel",
        status="open",
    )
    assert response.status_code == 200, response.text
    opp = response.json()["data"]["opportunity"]
    assert (opp["compensation_min"], opp["compensation_max"]) == (8000, 12000)
    assert (opp["compensation_currency"], opp["compensation_unit"]) == ("INR", unit)
    card = client.get("/api/public/opportunities", params={"page_size": 50}).json()["data"]["opportunities"]
    mine = next(c for c in card if c["id"] == opp["id"])
    detail = client.get(f"/api/public/opportunities/{opp['id']}").json()["data"]["opportunity"]
    for view in (mine, detail):
        assert (view["compensation_min"], view["compensation_max"]) == (8000, 12000)
        assert (view["compensation_currency"], view["compensation_unit"]) == ("INR", unit)
        assert view["compensation_text"] == "plus travel"


def test_no_compensation_is_all_null_and_equal_min_max_ok(client, admin_headers, topic_ids):
    plain = _post(client, admin_headers, topic_ids).json()["data"]["opportunity"]
    assert all(plain[k] is None for k in (
        "compensation_min", "compensation_max", "compensation_currency", "compensation_unit"))
    single = _post(
        client, admin_headers, topic_ids, compensation_min=0, compensation_max=0,
        compensation_currency="USD", compensation_unit="hour",
    )
    assert single.status_code == 200
    only_max = _post(
        client, admin_headers, topic_ids, compensation_max=5000,
        compensation_currency="USD", compensation_unit="month",
    )
    assert only_max.status_code == 200


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (dict(compensation_min=100, compensation_unit="day"), "compensation_currency: required with an amount"),
        (dict(compensation_max=100, compensation_currency="INR"), "compensation_unit: required with an amount"),
        (dict(compensation_currency="INR"), "compensation_min: enter an amount, or clear the currency and unit"),
        (dict(compensation_unit="day"), "compensation_min: enter an amount, or clear the currency and unit"),
        (dict(compensation_min=10, compensation_max=5, compensation_currency="INR", compensation_unit="day"),
         "compensation_max: must be at least compensation_min"),
        (dict(compensation_min=-1, compensation_currency="INR", compensation_unit="day"),
         "compensation_min: must be between 0 and 100000000"),
        (dict(compensation_max=100_000_001, compensation_currency="INR", compensation_unit="day"),
         "compensation_max: must be between 0 and 100000000"),
        (dict(compensation_min=1, compensation_currency="EUR", compensation_unit="day"),
         "compensation_currency: must be one of INR, USD"),
        (dict(compensation_min=1, compensation_currency="INR", compensation_unit="week"),
         "compensation_unit: must be one of hour, day, course, month"),
    ],
)
def test_invalid_compensation_is_rejected_with_exact_message(client, admin_headers, topic_ids, fields, message):
    assert _msg(_post(client, admin_headers, topic_ids, **fields)) == message


def test_non_integer_amount_and_long_note_rejected(client, admin_headers, topic_ids):
    for bad in (12.5, "100", True):
        response = _post(
            client, admin_headers, topic_ids, compensation_min=bad,
            compensation_currency="INR", compensation_unit="day",
        )
        assert response.status_code == 422, bad
    assert "compensation_text" in _msg(_post(client, admin_headers, topic_ids, compensation_text="x" * 121))


def test_patch_partial_merges_against_stored_state(client, admin_headers, topic_ids):
    opp = _post(
        client, admin_headers, topic_ids, compensation_min=8000, compensation_max=12000,
        compensation_currency="INR", compensation_unit="day",
    ).json()["data"]["opportunity"]
    url = f"/api/admin/opportunities/{opp['id']}"
    # raising the max alone keeps the stored currency/unit
    ok = client.patch(url, json={"compensation_max": 15000}, headers=admin_headers)
    assert ok.status_code == 200 and ok.json()["data"]["opportunity"]["compensation_unit"] == "day"
    activity = client.get(url, headers=admin_headers).json()["data"]["activity"]
    assert activity[0]["detail"]["changed_fields"] == ["compensation_max"]
    # lowering the max below the stored min is judged on the merged state
    assert _msg(client.patch(url, json={"compensation_max": 100}, headers=admin_headers)) == (
        "compensation_max: must be at least compensation_min")
    # clearing only the amounts leaves a dangling currency/unit
    assert "enter an amount" in _msg(
        client.patch(url, json={"compensation_min": None, "compensation_max": None}, headers=admin_headers))
    # clearing everything together is fine
    cleared = client.patch(
        url,
        json={k: None for k in ("compensation_min", "compensation_max", "compensation_currency", "compensation_unit")},
        headers=admin_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["opportunity"]["compensation_unit"] is None
    # the legacy note-only listing still works
    assert client.patch(url, json={"compensation_text": "Pro bono"}, headers=admin_headers).status_code == 200
