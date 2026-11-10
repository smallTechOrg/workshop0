"""Phase 13 / R2: server-rendered /trainers pages, sitemap and robots (PostgreSQL)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest

from src.workshop0.db.models import AppUser, CvDocument, Topic, TrainerProfile, TrainerTopic
from src.workshop0.db.session import create_db_session
from src.workshop0.services import directory

SENT = "ZZ-SENTINEL-9f3a"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
TEMPLATE = (
    '<!DOCTYPE html><html><head><title>Workshop0</title>'
    '<meta name="description" content="Default"/></head>'
    '<body><div id="v">trainer client</div></body></html>'
)
_n = {"i": 0}


@pytest.fixture(autouse=True)
def trainer_html(monkeypatch, tmp_path):
    path = tmp_path / "trainer.html"
    path.write_text(TEMPLATE, encoding="utf-8")
    import src.workshop0.api.seo as api_seo

    monkeypatch.setattr(api_seo, "TRAINER_HTML", path)
    api_seo._template_cache.clear()
    return path


def seed(name="Asha Rao", *, visibility="public", full=True, **over) -> dict:
    _n["i"] += 1
    with create_db_session() as s:
        user = AppUser(
            email=f"u{_n['i']}-{SENT}@example.test", email_verified=True, display_name=name,
            avatar_url="https://img.example/a.png", oidc_issuer="x", oidc_subject=f"sub-{_n['i']}",
        )
        s.add(user)
        s.flush()
        fields = dict(
            user_id=user.id, headline="GenAI trainer", consent_at=datetime.now(timezone.utc),
            consent_version="2026-11", visibility=visibility, bio_md="Teaches agents. " * 30, city="Pune",
            remote_ok=True, linkedin_url="https://linkedin.com/in/x", github_url=None, website_url=None,
            past_work_json=json.dumps([{"title": "Bootcamp", "kind": "workshop", "org": "Acme", "year": 2025}]),
            rate_min=111222, rate_max=333444, rate_currency="INR", rate_unit="day", pro_bono=True,
            availability_json=json.dumps({"mon": ["morning"]}), blackout_json="[]",
            autofilled_fields_json="[]", verified=True, verified_by=SENT,
        )
        if not full:
            fields.update(bio_md="", city=None, remote_ok=False, linkedin_url=None, past_work_json="[]",
                          rate_min=None, rate_max=None, pro_bono=False, availability_json="{}")
        fields.update(over)
        profile = TrainerProfile(**fields)
        s.add(profile)
        s.flush()
        topics = s.query(Topic).order_by(Topic.position).limit(3 if full else 0).all()
        for t in topics:
            s.add(TrainerTopic(profile_id=profile.id, topic_id=t.id, level="expert"))
        if full:
            s.add(CvDocument(user_id=user.id, source="text", sha256="0" * 64, text_extract=SENT,
                             draft_status="ready"))
        s.flush()
        if visibility == "public":
            directory.ensure_slug(s, profile, user)
        return {"id": profile.id, "user_id": user.id, "slug": profile.public_slug,
                "topics": [t.name for t in topics]}


def ld(html: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_index_redirect(client):
    r = client.get("/trainers", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/app/network/directory/"


def test_listed_trainer_page(client):
    t = seed()
    r = client.get(f"/trainers/{t['slug']}")
    assert r.status_code == 200 and "trainer client" in r.text
    h = r.text
    assert h.count("<title>") == 1 and "<title>Asha Rao — GenAI trainer — Workshop0</title>" in h
    assert "Default" not in h
    assert h.index("<!--w0-seo-->") < h.index("</head>") and h.index("<!--/w0-seo-->") < h.index("</head>")
    url = f"http://testserver/trainers/{t['slug']}"
    assert f'<link rel="canonical" href="{url}">' in h
    assert '<meta property="og:type" content="profile">' in h
    assert "og:image" not in h
    assert 'name="twitter:card" content="summary"' in h
    desc = re.search(r'<meta name="description" content="([^"]*)">', h).group(1)
    assert desc.startswith("GenAI trainer") and len(desc) <= 160
    person = ld(h)
    assert person["@type"] == "Person" and person["name"] == "Asha Rao" and person["url"] == url
    assert person["jobTitle"] == "GenAI trainer" and person["knowsAbout"] == t["topics"]
    assert person["sameAs"] == ["https://linkedin.com/in/x"]
    assert person["address"] == {"@type": "PostalAddress", "addressLocality": "Pune"}


def test_no_city_omits_address(client):
    t = seed(city=None)
    assert "address" not in ld(client.get(f"/trainers/{t['slug']}").text)


def test_page_leaks_nothing(client):
    t = seed()
    r = client.get(f"/trainers/{t['slug']}")
    for bad in (SENT, "example.test", "111222", "333444", "pro_bono", "verified_by", "img.example"):
        assert bad not in r.text
    assert f'"{t["id"]}"' not in r.text


def test_html_escaping_and_script_safety(client):
    t = seed(name='A "Q" <b>&', headline="</script><script>alert(1)</script>")
    h = client.get(f"/trainers/{t['slug']}").text
    assert "</script><script>alert" not in h
    assert "<b>" not in h
    assert ld(h)["name"] == 'A "Q" <b>&'


@pytest.mark.parametrize("make", ["private", "low", "unknown", "numeric", "malformed", "toolong"])
def test_everything_else_is_the_same_404(client, make):
    t = seed("Hidden Person", visibility="private") if make == "private" else None
    low = seed("Low Person", full=False) if make == "low" else None
    key = {
        "private": t and (t["slug"] or "x-1"), "low": low and low["slug"], "unknown": "nobody-0000",
        "numeric": str(seed()["id"]), "malformed": "bad_slug!", "toolong": "a" * 81,
    }[make] or "none-0"
    r = client.get(f"/trainers/{key}")
    assert r.status_code == 404
    block = re.search(r"<!--w0-seo-->(.*?)<!--/w0-seo-->", r.text, re.S).group(1)
    assert block == '<title>Trainer not available — Workshop0</title>\n<meta name="robots" content="noindex">'
    assert "Hidden Person" not in r.text and "Low Person" not in r.text and "application/ld+json" not in r.text


def test_mixed_case_and_trailing_slash_redirect(client):
    t = seed()
    r = client.get(f"/trainers/{t['slug'].upper()}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/trainers/{t['slug']}"
    r = client.get(f"/trainers/{t['slug']}/", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/trainers/{t['slug']}"


def test_mixed_case_unlisted_is_404(client):
    assert client.get("/trainers/Nobody-0000", follow_redirects=False).status_code == 404


def test_not_built_is_503(client, trainer_html):
    trainer_html.unlink()
    assert client.get("/trainers/x-1").status_code == 503


def test_sitemap_has_only_listed_trainers(client):
    a = seed("Aaron")
    b = seed("Zed")
    hidden = [seed("Priv", visibility="private"), seed("Low", full=False)]
    r = client.get("/sitemap.xml")
    locs = [el.text for el in ET.fromstring(r.content).iter(f"{NS}loc")]
    assert locs == [
        "http://testserver/opportunities", "http://testserver/trainers",
        f"http://testserver/trainers/{a['slug']}", f"http://testserver/trainers/{b['slug']}",
    ]
    for m in re.findall(r"<lastmod>(.*?)</lastmod>", r.text):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", m)
    for h in hidden:
        assert (h["slug"] or "no-slug") not in r.text
    assert SENT not in r.text and "@" not in r.text


def test_robots_has_new_disallows_in_order_and_sitemap_last(client):
    lines = client.get("/robots.txt").text.splitlines()
    i = lines.index("Disallow: /app/network/me/")
    assert lines[i + 1 : i + 4] == [
        "Disallow: /app/network/trainer/", "Disallow: /app/network/searches/",
        "Disallow: /app/network/unsubscribed/",
    ]
    assert lines[-1] == "Sitemap: http://testserver/sitemap.xml"


def test_configured_base_url(client, monkeypatch):
    import src.workshop0.config.settings as settings_module

    monkeypatch.setenv("WORKSHOP0_BASE_URL", "https://workshop0.smalltech.in")
    settings_module._settings = None
    t = seed()
    h = client.get(f"/trainers/{t['slug']}").text
    assert f'href="https://workshop0.smalltech.in/trainers/{t["slug"]}"' in h
    assert f"<loc>https://workshop0.smalltech.in/trainers/{t['slug']}</loc>" in client.get("/sitemap.xml").text
