"""Phase 12 admin-only budget + min_level: validation, admin serialisation, public leak proof,
applicant_count."""

from __future__ import annotations

import pytest

from tests.integration.applications.conftest import apply_to

BUDGET = {"budget_min": 20000, "budget_max": 40000, "budget_currency": "INR", "budget_unit": "day",
          "min_level": "advanced"}
LEAK = ("budget_min", "budget_max", "budget_currency", "budget_unit", "min_level", "applicant_count")


def test_budget_roundtrip_on_admin_create_get_patch_and_list(client, admin_headers, create_opportunity):
    created = create_opportunity(**BUDGET)
    for key, value in BUDGET.items():
        assert created[key] == value
    got = client.get(f"/api/admin/opportunities/{created['id']}", headers=admin_headers).json()["data"]
    assert got["opportunity"]["budget_max"] == 40000 and got["opportunity"]["applicant_count"] == 0
    patched = client.patch(
        f"/api/admin/opportunities/{created['id']}", json={"budget_max": 50000, "min_level": None},
        headers=admin_headers,
    ).json()["data"]["opportunity"]
    assert patched["budget_max"] == 50000 and patched["min_level"] is None
    audit = [a for a in got["activity"]]
    assert audit  # create is audited
    listed = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]["opportunities"]
    assert listed[0]["budget_unit"] == "day"
    updated = client.get(f"/api/admin/opportunities/{created['id']}", headers=admin_headers).json()["data"]
    assert "budget_max" in updated["activity"][0]["detail"]["changed_fields"]


def test_budget_defaults_to_null(create_opportunity):
    created = create_opportunity()
    assert all(created[k] is None for k in ("budget_min", "budget_max", "budget_currency", "budget_unit", "min_level"))


@pytest.mark.parametrize(
    "patch",
    [
        {"budget_min": 500, "budget_max": 100, "budget_currency": "INR", "budget_unit": "day"},
        {"budget_max": 100},  # amount without currency/unit
        {"budget_max": 100, "budget_currency": "INR"},  # no unit
        {"budget_currency": "INR"},  # currency without amount
        {"budget_max": 100, "budget_currency": "EUR", "budget_unit": "day"},
        {"budget_max": 100, "budget_currency": "INR", "budget_unit": "year"},
        {"budget_max": -1, "budget_currency": "INR", "budget_unit": "day"},
        {"budget_max": 10**9, "budget_currency": "INR", "budget_unit": "day"},
        {"budget_max": 1.5, "budget_currency": "INR", "budget_unit": "day"},
        {"min_level": "beginner"},
    ],
)
def test_budget_validation_rejected(client, admin_headers, create_opportunity, patch):
    opp = create_opportunity()
    r = client.patch(f"/api/admin/opportunities/{opp['id']}", json=patch, headers=admin_headers)
    assert r.status_code == 422, (patch, r.text)
    assert r.json()["detail"]["code"] == "validation_error"


def test_budget_boundaries_accepted(client, admin_headers, create_opportunity):
    opp = create_opportunity(budget_min=0, budget_max=0, budget_currency="USD", budget_unit="course",
                             min_level="intermediate")
    assert opp["budget_max"] == 0 and opp["budget_unit"] == "course"
    r = client.patch(f"/api/admin/opportunities/{opp['id']}",
                     json={"budget_min": None, "budget_max": None, "budget_currency": None, "budget_unit": None},
                     headers=admin_headers)
    assert r.status_code == 200 and r.json()["data"]["opportunity"]["budget_currency"] is None


def test_budget_never_in_public_payloads(client, admin_headers, create_opportunity, trainer_factory):
    opp = create_opportunity(status="open", **BUDGET)
    paths = ["/api/public/opportunities", f"/api/public/opportunities/{opp['id']}",
             f"/api/public/opportunities/{opp['slug']}"]
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)
        for needle in LEAK:
            assert needle not in r.text, (path, needle)
    page = client.get(f"/opportunities/{opp['slug']}")
    for needle in LEAK:
        assert needle not in page.text
    # trainer-facing payloads too
    _, tclient, _ = trainer_factory("ada@example.test")
    apply_to(tclient, opp["id"])
    for needle in LEAK:
        assert needle not in tclient.get("/api/me/applications").text


def test_applicant_count_excludes_withdrawn(client, admin_headers, trainer_factory, open_listing):
    listing = open_listing()
    other = open_listing(title="Second listing no applicants")
    _, a, _ = trainer_factory("ada@example.test")
    _, b, _ = trainer_factory("bob@example.test")
    apply_to(a, listing["id"])
    app_b = apply_to(b, listing["id"]).json()["data"]["application"]["id"]
    rows = {o["id"]: o for o in client.get("/api/admin/opportunities", headers=admin_headers)
            .json()["data"]["opportunities"]}
    assert rows[listing["id"]]["applicant_count"] == 2 and rows[other["id"]]["applicant_count"] == 0
    b.post(f"/api/me/applications/{app_b}/withdraw")
    rows = {o["id"]: o for o in client.get("/api/admin/opportunities", headers=admin_headers)
            .json()["data"]["opportunities"]}
    assert rows[listing["id"]]["applicant_count"] == 1
    single = client.get(f"/api/admin/opportunities/{listing['id']}", headers=admin_headers).json()["data"]
    assert single["opportunity"]["applicant_count"] == 1
