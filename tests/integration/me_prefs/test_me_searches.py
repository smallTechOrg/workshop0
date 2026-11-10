"""C17 saved searches, email prefs, my workshops, visibility patch (PostgreSQL)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from src.workshop0.db.models import EmailPref, FacilitatorAction, SavedSearch, TrainerProfile
from src.workshop0.db.session import create_db_session

PROFILE = {"headline": "GenAI trainer · ex-Flipkart", "topics": [{"slug": "python", "level": "expert"}],
           "consent": True}
FULL = {
    **PROFILE,
    "bio_md": "I teach practical LLM engineering to product teams. " * 3,
    "city": "Bengaluru",
    "linkedin_url": "https://www.linkedin.com/in/priya-example",
    "topics": [{"slug": "python", "level": "expert"}, {"slug": "generative-ai", "level": "advanced"},
               {"slug": "prompt-engineering", "level": "intermediate"}],
    "past_work": [{"title": "LLM bootcamp", "kind": "workshop", "org": "Acme", "year": 2025}],
    "rate_min": 40000, "rate_max": 60000, "rate_currency": "INR", "rate_unit": "day",
    "availability": {"mon": ["morning"]},
}
CRIT = {"types": ["workshop"], "topic_slugs": ["python"], "location_modes": [], "cities": []}


@pytest.fixture
def trainer(make_user, signed_in_client):
    user = make_user("searcher@example.test")
    return user, signed_in_client(user)


@pytest.fixture
def profiled(trainer):
    user, client = trainer
    assert client.post("/api/me/profile", json=PROFILE).status_code == 200
    return user, client


def _err(response, status, code):
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code, detail
    return detail


def _audit(action):
    with create_db_session() as s:
        return [json.loads(r.detail_json) for r in s.scalars(
            select(FacilitatorAction).where(FacilitatorAction.action == action).order_by(FacilitatorAction.id))]


def _make(client, name="Python workshops", **extra):
    r = client.post("/api/me/searches", json={"name": name, "criteria": CRIT, **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]["search"]


# --------------------------------------------------------------------------- searches


def test_list_empty_without_profile(trainer):
    _, client = trainer
    r = client.get("/api/me/searches")
    assert r.status_code == 200
    assert r.json()["data"] == {"searches": [], "limit": 10}


def test_create_requires_profile(trainer):
    _, client = trainer
    _err(client.post("/api/me/searches", json={"name": "x", "criteria": CRIT}), 409, "profile_required")


def test_create_list_newest_first_and_persisted(profiled):
    user, client = profiled
    a = _make(client, "First")
    b = _make(client, "Second", alerts_enabled=False)
    assert set(a) == {"id", "name", "criteria", "alerts_enabled", "created_at", "updated_at"}
    assert a["alerts_enabled"] is True and b["alerts_enabled"] is False
    listed = client.get("/api/me/searches").json()["data"]["searches"]
    assert [s["name"] for s in listed] == ["Second", "First"]
    with create_db_session() as s:
        row = s.get(SavedSearch, a["id"])
        assert row.user_id == user.id and json.loads(row.criteria_json) == CRIT
    audits = _audit("search.create")
    assert len(audits) == 2
    with create_db_session() as s:
        act = s.scalars(select(FacilitatorAction).where(FacilitatorAction.action == "search.create")).first()
        assert act.actor == "user" and act.subject_type == "trainer"


def test_criteria_normalised(profiled):
    _, client = profiled
    s = _make(client)
    r = client.post("/api/me/searches", json={"name": "c", "criteria": {
        "topic_slugs": ["python", "python"], "cities": ["  Pune   City ", "pune city"]}})
    assert r.status_code == 200, r.text
    crit = r.json()["data"]["search"]["criteria"]
    assert crit == {"types": [], "topic_slugs": ["python"], "location_modes": [], "cities": ["Pune City"]}
    assert s["id"]


@pytest.mark.parametrize("criteria,needle", [
    ({}, "at least one"),
    ({"types": [], "topic_slugs": [], "location_modes": [], "cities": []}, "at least one"),
    ({"types": ["bogus"]}, "types"),
    ({"location_modes": ["moon"]}, "location_modes"),
    ({"topic_slugs": ["no-such-topic"]}, "topic_slugs"),
    ({"cities": ["   "]}, "cities"),
    ({"cities": ["x" * 81]}, "cities"),
    ({"cities": [f"c{i}" for i in range(6)]}, "cities"),
    ({"types": ["workshop"], "extra": []}, "extra"),
    ("nope", "criteria"),
])
def test_bad_criteria_422(profiled, criteria, needle):
    _, client = profiled
    d = _err(client.post("/api/me/searches", json={"name": "n", "criteria": criteria}), 422, "validation_error")
    assert needle in d["message"]


@pytest.mark.parametrize("body", [
    {"criteria": CRIT},
    {"name": "   ", "criteria": CRIT},
    {"name": "n" * 81, "criteria": CRIT},
    {"name": 5, "criteria": CRIT},
    {"name": "ok", "criteria": CRIT, "alerts_enabled": "yes"},
    {"name": "ok"},
])
def test_bad_name_or_flag_422(profiled, body):
    _, client = profiled
    _err(client.post("/api/me/searches", json=body), 422, "validation_error")
    assert client.get("/api/me/searches").json()["data"]["searches"] == []


def test_limit_ten(profiled):
    _, client = profiled
    for i in range(10):
        _make(client, f"s{i}")
    _err(client.post("/api/me/searches", json={"name": "11", "criteria": CRIT}), 409, "search_limit")
    sid = client.get("/api/me/searches").json()["data"]["searches"][0]["id"]
    assert client.delete(f"/api/me/searches/{sid}").status_code == 200
    _make(client, "after delete")


def test_patch_partial_and_validation(profiled):
    _, client = profiled
    s = _make(client)
    r = client.patch(f"/api/me/searches/{s['id']}", json={"alerts_enabled": False})
    assert r.status_code == 200
    got = r.json()["data"]["search"]
    assert got["alerts_enabled"] is False and got["name"] == s["name"] and got["criteria"] == CRIT
    r = client.patch(f"/api/me/searches/{s['id']}", json={"name": "Renamed", "criteria": {"cities": ["Pune"]}})
    assert r.json()["data"]["search"]["criteria"]["cities"] == ["Pune"]
    assert r.json()["data"]["search"]["criteria"]["types"] == []
    _err(client.patch(f"/api/me/searches/{s['id']}", json={"criteria": {}}), 422, "validation_error")
    _err(client.patch(f"/api/me/searches/{s['id']}", json={"name": ""}), 422, "validation_error")
    after = client.get("/api/me/searches").json()["data"]["searches"][0]
    assert after["name"] == "Renamed"


def test_cross_user_isolation(profiled, make_user, signed_in_client):
    _, client = profiled
    s = _make(client)
    other = signed_in_client(make_user("other@example.test"))
    assert other.get("/api/me/searches").json()["data"]["searches"] == []
    _err(other.patch(f"/api/me/searches/{s['id']}", json={"name": "hax"}), 404, "not_found")
    _err(other.delete(f"/api/me/searches/{s['id']}"), 404, "not_found")
    _err(other.delete("/api/me/searches/999999"), 404, "not_found")
    assert client.get("/api/me/searches").json()["data"]["searches"][0]["name"] == s["name"]


def test_delete_and_audit(profiled):
    _, client = profiled
    s = _make(client)
    r = client.delete(f"/api/me/searches/{s['id']}")
    assert r.json()["data"] == {"deleted": True}
    assert client.get("/api/me/searches").json()["data"]["searches"] == []
    assert _audit("search.delete") == [{"search_id": s["id"]}]
    _err(client.delete(f"/api/me/searches/{s['id']}"), 404, "not_found")


def test_search_guards(profiled, make_client):
    _, client = profiled
    anon = make_client()
    assert anon.get("/api/me/searches").status_code == 401
    r = anon.post("/api/me/searches", json={"name": "n", "criteria": CRIT})
    assert r.status_code in (401, 403)
    client.headers.pop("X-Requested-With", None)
    assert client.post("/api/me/searches", json={"name": "n", "criteria": CRIT}).status_code == 403


def test_create_rate_limit(profiled):
    _, client = profiled
    # 60/h bucket: invalid requests count too, so burn it with cheap 422s.
    for _ in range(60):
        client.post("/api/me/searches", json={"name": "", "criteria": CRIT})
    r = client.post("/api/me/searches", json={"name": "n", "criteria": CRIT})
    _err(r, 429, "rate_limited")


def test_account_delete_removes_searches(profiled):
    user, client = profiled
    _make(client)
    r = client.request("DELETE", "/api/me", json={"confirm_email": "searcher@example.test"})
    assert r.status_code == 200, r.text
    with create_db_session() as s:
        assert s.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id)).first() is None


# --------------------------------------------------------------------------- email prefs


def test_email_prefs_default_patch_and_audit(trainer):
    user, client = trainer
    assert client.get("/api/me/email-prefs").json()["data"] == {"alerts": True, "digest": True}
    r = client.patch("/api/me/email-prefs", json={"digest": False})
    assert r.json()["data"] == {"alerts": True, "digest": False}
    r = client.patch("/api/me/email-prefs", json={"alerts": False})
    assert r.json()["data"] == {"alerts": False, "digest": False}
    assert client.get("/api/me/email-prefs").json()["data"] == {"alerts": False, "digest": False}
    with create_db_session() as s:
        assert s.get(EmailPref, user.id).alerts is False
    assert _audit("email_pref.update")[-1] == {"alerts": False, "digest": False}


@pytest.mark.parametrize("body", [{"alerts": "no"}, {"digest": 0}, {"alerts": None}, {"digest": "false"}])
def test_email_prefs_non_bool_422(trainer, body):
    _, client = trainer
    _err(client.patch("/api/me/email-prefs", json=body), 422, "validation_error")
    assert client.get("/api/me/email-prefs").json()["data"] == {"alerts": True, "digest": True}


def test_email_prefs_empty_patch_and_isolation(trainer, make_user, signed_in_client):
    _, client = trainer
    assert client.patch("/api/me/email-prefs", json={}).json()["data"] == {"alerts": True, "digest": True}
    client.patch("/api/me/email-prefs", json={"alerts": False})
    other = signed_in_client(make_user("o2@example.test"))
    assert other.get("/api/me/email-prefs").json()["data"] == {"alerts": True, "digest": True}


def test_email_prefs_guards(make_client):
    assert make_client().get("/api/me/email-prefs").status_code == 401


# --------------------------------------------------------------------------- workshops


def test_my_workshops(profiled, client, admin_headers, workshop):
    user, tclient = profiled
    assert tclient.get("/api/me/workshops").json()["data"] == {"workshops": []}
    with create_db_session() as s:
        pid = s.scalar(select(TrainerProfile.id).where(TrainerProfile.user_id == user.id))
    r = client.post(f"/api/admin/workshops/{workshop['id']}/facilitators",
                    json={"profile_id": pid, "role": "lead"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    items = tclient.get("/api/me/workshops").json()["data"]["workshops"]
    assert len(items) == 1
    w = items[0]
    assert set(w) == {"workshop_id", "name", "status", "role", "facilitator_url", "linked_at"}
    assert w["role"] == "lead" and w["workshop_id"] == workshop["id"]
    assert w["facilitator_url"].endswith(f"/f/{workshop['admin_token']}")


def test_my_workshops_no_profile_and_anon(trainer, make_client):
    _, client = trainer
    assert client.get("/api/me/workshops").json()["data"] == {"workshops": []}
    assert make_client().get("/api/me/workshops").status_code == 401


def test_my_workshops_other_trainers_not_shown(profiled, make_user, signed_in_client, client,
                                               admin_headers, workshop):
    other_user = make_user("o3@example.test")
    other = signed_in_client(other_user)
    other.post("/api/me/profile", json=PROFILE)
    with create_db_session() as s:
        pid = s.scalar(select(TrainerProfile.id).where(TrainerProfile.user_id == other_user.id))
    client.post(f"/api/admin/workshops/{workshop['id']}/facilitators",
                json={"profile_id": pid, "role": "co"}, headers=admin_headers)
    _, mine = profiled
    assert mine.get("/api/me/workshops").json()["data"]["workshops"] == []
    assert len(other.get("/api/me/workshops").json()["data"]["workshops"]) == 1


# --------------------------------------------------------------------------- visibility


def test_visibility_public_generates_slug_and_directory_block(profiled):
    user, client = profiled
    own = client.get("/api/me/profile").json()["data"]["profile"]
    assert own["directory"] == {"visibility": "private", "listed": False, "path": None,
                                "min_completeness": 60}
    r = client.patch("/api/me/profile", json={"visibility": "public"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]["profile"]["directory"]
    assert d["visibility"] == "public" and d["path"].startswith("/trainers/") and d["listed"] is False
    slug = d["path"]
    client.patch("/api/me/profile", json={"visibility": "private"})
    again = client.patch("/api/me/profile", json={"visibility": "public"}).json()["data"]["profile"]
    assert again["directory"]["path"] == slug  # slug frozen
    assert _audit("profile.update")[-1]["changed_fields"] == ["visibility"]


def test_visibility_listed_when_complete(trainer):
    _, client = trainer
    assert client.post("/api/me/profile", json=FULL).status_code == 200
    pct = client.get("/api/me/profile").json()["data"]["completeness"]["pct"]
    r = client.patch("/api/me/profile", json={"visibility": "public"}).json()["data"]["profile"]
    assert r["directory"]["listed"] is (pct >= 60)


@pytest.mark.parametrize("value", ["secret", "", None, 5, "PUBLIC"])
def test_visibility_invalid_422(profiled, value):
    _, client = profiled
    assert client.patch("/api/me/profile", json={"visibility": value}).status_code == 422
    assert client.get("/api/me/profile").json()["data"]["profile"]["visibility"] == "private"


def test_slug_in_body_ignored(profiled):
    user, client = profiled
    r = client.patch("/api/me/profile", json={"visibility": "public", "public_slug": "evil-slug",
                                              "directory": {"listed": True}})
    assert r.status_code == 200
    assert r.json()["data"]["profile"]["directory"]["path"] != "/trainers/evil-slug"
    with create_db_session() as s:
        assert s.scalar(select(TrainerProfile.public_slug).where(TrainerProfile.user_id == user.id)) != "evil-slug"
    client.patch("/api/me/profile", json={"public_slug": "evil-slug2"})
    with create_db_session() as s:
        assert s.scalar(select(TrainerProfile.public_slug).where(TrainerProfile.user_id == user.id)) != "evil-slug2"


def test_visibility_only_patch_keeps_autofill_content_patch_clears(profiled):
    user, client = profiled
    with create_db_session() as s:
        p = s.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user.id))
        p.autofilled_fields_json = json.dumps(["headline"])
        s.commit()
    r = client.patch("/api/me/profile", json={"visibility": "public"}).json()["data"]["profile"]
    assert r["autofilled_fields"] == ["headline"]
    r = client.patch("/api/me/profile", json={"visibility": "private", "city": "Pune"}).json()["data"]["profile"]
    assert r["autofilled_fields"] == []
    assert _audit("profile.update")[-1]["changed_fields"] == ["city", "visibility"]
