"""Phase 13 / R1: public trainer directory (C18) on PostgreSQL. Seeds rows directly so every
completeness / visibility combination is controlled; leak-tests the serialized JSON."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from src.workshop0.db.models import AppUser, CvDocument, Topic, TrainerProfile, TrainerTopic
from src.workshop0.db.session import create_db_session
from src.workshop0.services import directory, slugs

SENT = "ZZ-SENTINEL-9f3a"
NOT_FOUND = {"code": "not_found", "message": "This trainer profile isn't available."}
_n = {"i": 0}


def seed(name="Asha Rao", *, visibility="public", slug="auto", full=True, topics=3, cv=True, **over) -> dict:
    """Insert user + profile. `full` => 100 % complete. Returns {id, user_id, slug}."""
    _n["i"] += 1
    with create_db_session() as s:
        user = AppUser(
            email=f"u{_n['i']}-{SENT}@example.test".lower(), email_verified=True, display_name=name,
            avatar_url="https://img.example/a.png", oidc_issuer="x", oidc_subject=f"sub-{_n['i']}-{name}",
        )
        s.add(user)
        s.flush()
        fields = dict(
            user_id=user.id, headline="GenAI trainer", consent_at=datetime.now(timezone.utc),
            consent_version="2026-11", visibility=visibility, bio_md="bio " * 30, city="Pune", remote_ok=True,
            linkedin_url="https://linkedin.com/in/x", github_url=None, website_url=None,
            past_work_json=json.dumps([{"title": "Bootcamp", "kind": "workshop", "org": "Acme", "year": 2025,
                                        "secret": SENT}]),
            rate_min=100, rate_max=200, rate_currency="INR", rate_unit="day", pro_bono=True,
            availability_json=json.dumps({"mon": ["morning"]}), available_from=date(2026, 12, 1),
            blackout_json=json.dumps([{"start": "2026-12-20", "end": "2027-01-02"}]),
            autofilled_fields_json=json.dumps(["bio_md"]), verified=True, verified_by=SENT,
        )
        if not full:
            fields.update(bio_md="", city=None, remote_ok=False, linkedin_url=None, past_work_json="[]",
                          rate_min=None, rate_max=None, pro_bono=False, availability_json="{}", available_from=None)
        fields.update(over)
        profile = TrainerProfile(**fields)
        s.add(profile)
        s.flush()
        topic_rows = s.query(Topic).order_by(Topic.position).limit(topics).all()
        for t in topic_rows:
            s.add(TrainerTopic(profile_id=profile.id, topic_id=t.id, level="expert"))
        if cv:
            s.add(CvDocument(user_id=user.id, source="text", sha256="0" * 64, text_extract=SENT,
                             draft_status="ready"))
        s.flush()
        if slug == "auto" and visibility == "public":
            directory.ensure_slug(s, profile, user)
        elif slug != "auto":
            profile.public_slug = slug
        return {"id": profile.id, "user_id": user.id, "slug": profile.public_slug,
                "topic_slugs": [t.slug for t in topic_rows]}


def get(client, slug):
    return client.get(f"/api/public/trainers/{slug}")


# ------------------------------------------------------------------ happy path


def test_listed_trainer_list_and_detail(client):
    t = seed()
    body = client.get("/api/public/trainers").json()["data"]
    assert body["total"] == 1 and body["page"] == 1 and body["page_size"] == 24
    card = body["items"][0]
    assert set(card) == {"slug", "display_name", "avatar_url", "headline", "city", "remote_ok", "topics",
                         "verified", "links", "public_url"}
    assert card["slug"] == t["slug"] and card["display_name"] == "Asha Rao" and card["verified"] is True
    assert card["links"] == {"linkedin": "https://linkedin.com/in/x", "github": None, "website": None}
    assert card["public_url"].endswith(f"/trainers/{t['slug']}")
    assert len(card["topics"]) == 3 and set(card["topics"][0]) == {"slug", "name", "level"}
    detail = get(client, t["slug"]).json()["data"]
    assert set(detail) == set(card) | {"bio_md", "past_work"}
    assert detail["past_work"] == [{"title": "Bootcamp", "kind": "workshop", "org": "Acme", "year": 2025}]


def test_no_leak_in_raw_json(client):
    t = seed(name="Leak Test")
    for r in (client.get("/api/public/trainers"), get(client, t["slug"])):
        text = r.text
        assert SENT not in text
        for key in ("email", "rate_", "pro_bono", "availability", "blackout", "cv", "text_extract", "notes",
                    "tags", "consent", "autofilled", "visibility", "verified_by", "verified_at", "user_id",
                    "public_slug", '"id"', "secret"):
            assert key not in text, key
    assert str(t["id"]) not in get(client, t["slug"]).json()["data"]["public_url"].split("/trainers/")[0]


# ------------------------------------------------------------------ 404 uniformity


def test_all_unavailable_variants_are_identical_404(client):
    private = seed("Priv", visibility="private", slug="priv-aaaa")
    low = seed("Low", full=False, topics=0, cv=False)
    never = seed("Never", visibility="public", slug=None)
    listed = seed("Okay")
    keys = [private["slug"], low["slug"], "unknown-1234", str(private["id"]), str(listed["id"]),
            "x" * 81, "UNKNOWN", "a b", "%00", ""]
    responses = [get(client, k) for k in keys if k]
    bodies = set()
    for r in responses:
        assert r.status_code in (404,), r.text
        bodies.add(json.dumps(r.json(), sort_keys=True))
    assert len(bodies) == 1
    assert json.loads(bodies.pop())["detail"] == NOT_FOUND
    assert never["slug"] is None
    assert get(client, listed["slug"]).status_code == 200
    # trailing slash route variant is just another 404/redirect, never a 500
    assert client.get("/api/public/trainers/").status_code != 500


def test_mixed_case_key_resolves(client):
    t = seed()
    assert get(client, t["slug"].upper()).status_code == 200


def test_threshold_exactly_60_listed_50_not(client):
    ok60 = seed("Sixty", cv=False, topics=2, rate_min=None, rate_max=None, pro_bono=False)
    from src.workshop0.services import profiles

    def pct(pid):
        with create_db_session() as s:
            p = s.get(TrainerProfile, pid)
            return profiles.completeness(p).pct

    assert pct(ok60["id"]) == 70
    at60 = seed("AtSixty", cv=False, topics=2, rate_min=None, rate_max=None, pro_bono=False,
                available_from=None)
    assert pct(at60["id"]) == 60 and get(client, at60["slug"]).status_code == 200
    at50 = seed("AtFifty", cv=False, topics=2, rate_min=None, rate_max=None, pro_bono=False,
                available_from=None, past_work_json="[]")
    assert pct(at50["id"]) == 50 and get(client, at50["slug"]).status_code == 404
    slugs_listed = [i["slug"] for i in client.get("/api/public/trainers").json()["data"]["items"]]
    assert at50["slug"] not in slugs_listed and at60["slug"] in slugs_listed


def test_toggle_private_then_public_keeps_slug_and_404s_meanwhile(client):
    t = seed()
    with create_db_session() as s:
        s.get(TrainerProfile, t["id"]).visibility = "private"
    assert get(client, t["slug"]).status_code == 404
    with create_db_session() as s:
        p = s.get(TrainerProfile, t["id"])
        p.visibility = "public"
        assert directory.ensure_slug(s, p, s.get(AppUser, t["user_id"])) == t["slug"]
    assert get(client, t["slug"]).status_code == 200


# ------------------------------------------------------------------ list behaviour


def test_ordering_topic_filter_pagination(client):
    names = ["zed", "Éva", "bob", "Alice", "carl"]
    made = [seed(n, topics=3 if n != "carl" else 5) for n in names]
    items = client.get("/api/public/trainers").json()["data"]["items"]
    assert [i["display_name"] for i in items] == ["Alice", "bob", "carl", "zed", "Éva"]
    order = [i["display_name"].casefold() for i in items]
    assert order == sorted(order)
    only = made[2]["topic_slugs"]
    extra = [t for t in made[4]["topic_slugs"] if t not in only][0]
    r = client.get("/api/public/trainers", params={"topic": extra}).json()["data"]
    assert [i["display_name"] for i in r["items"]] == ["carl"] and r["total"] == 1
    r = client.get("/api/public/trainers", params={"topic": "no-such-topic"})
    assert r.status_code == 200 and r.json()["data"]["items"] == [] and r.json()["data"]["total"] == 0


def test_pagination_pages(client):
    for i in range(26):
        seed(f"Person {i:02d}")
    p1 = client.get("/api/public/trainers").json()["data"]
    p2 = client.get("/api/public/trainers", params={"page": 2}).json()["data"]
    p3 = client.get("/api/public/trainers", params={"page": 3}).json()["data"]
    assert (len(p1["items"]), len(p2["items"]), len(p3["items"])) == (24, 2, 0)
    assert p1["total"] == p2["total"] == p3["total"] == 26
    assert client.get("/api/public/trainers", params={"page": 0}).status_code == 422


def test_empty_directory(client):
    r = client.get("/api/public/trainers")
    assert r.json()["data"] == {"items": [], "page": 1, "page_size": 24, "total": 0}


def test_unlisted_never_in_list_or_total(client):
    seed("Hidden", visibility="private", slug="hidden-1111")
    seed("Thin", full=False, topics=0, cv=False)
    assert client.get("/api/public/trainers").json()["data"]["total"] == 0


# ------------------------------------------------------------------ ensure_slug / sitemap


@pytest.mark.parametrize(
    ("name", "base"), [("Zoë Müller", "zoe-muller"), ("आशा राव", "trainer"), ("", "trainer"), ("  !! ", "trainer")]
)
def test_ensure_slug_rules(client, name, base):
    t = seed(name or "x", visibility="private", slug=None)
    with create_db_session() as s:
        u = s.get(AppUser, t["user_id"])
        u.display_name = name
        p = s.get(TrainerProfile, t["id"])
        slug = directory.ensure_slug(s, p, u)
        assert slug.rpartition("-")[0] == base
        assert len(slug.rpartition("-")[2]) in (4, 6) and "-" in slug
        assert SENT not in slug and str(u.id) != slug
        u.display_name = "Renamed Person"
        assert directory.ensure_slug(s, p, u) == slug  # frozen


def test_ensure_slug_collisions_retry(client, monkeypatch):
    first = seed("Dup Name")
    t = seed("Dup Name", visibility="private", slug=None)
    base, _, suffix = first["slug"].rpartition("-")
    calls = iter([bytes.fromhex(suffix).hex()] * 3)
    monkeypatch.setattr(slugs, "new_suffix", lambda n=2: next(calls, "%0*x" % (n * 2, 0x1234)))
    with create_db_session() as s:
        got = directory.ensure_slug(s, s.get(TrainerProfile, t["id"]), s.get(AppUser, t["user_id"]))
    assert got != first["slug"] and got.startswith("dup-name-")


def test_slug_base_fallback_default_unchanged():
    assert slugs.slug_base("!!!", None) == "opportunity"
    assert slugs.slug_base("!!!", None, fallback="trainer") == "trainer"


def test_sitemap_entries_only_listed(client):
    a = seed("Beta")
    b = seed("Alpha")
    seed("Priv", visibility="private", slug="priv-bbbb")
    seed("Thin", full=False, topics=0, cv=False)
    with create_db_session() as s:
        entries = directory.sitemap_entries(s, "http://x")
    assert [e[0] for e in entries] == [b["slug"], a["slug"]]
    assert all(isinstance(e[1], datetime) for e in entries)
