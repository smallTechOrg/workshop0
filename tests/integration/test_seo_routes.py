"""Phase 11e — server-rendered listing pages, sitemap and robots (PostgreSQL)."""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import db_execute

TEMPLATE = (
    "<!DOCTYPE html><html><head><title>Workshop0</title>"
    '<meta name="description" content="Default"/></head>'
    '<body><div id="view">client renders here</div></body></html>'
)
ROBOTS = """User-agent: *
Disallow: /admin
Disallow: /app/admin/
Disallow: /api/
Disallow: /network/me
Disallow: /app/network/me/
Disallow: /app/opportunities/view/
Disallow: /f/
Disallow: /p/
Disallow: /app/f/
Disallow: /app/p/
Sitemap: {base}/sitemap.xml
"""
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@pytest.fixture(autouse=True)
def view_html(monkeypatch, tmp_path):
    import src.workshop0.api.seo as seo_api

    path = tmp_path / "view.html"
    path.write_text(TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(seo_api, "VIEW_HTML", path)
    return path


def _close(client, admin_headers, oid):
    response = client.patch(f"/api/admin/opportunities/{oid}", json={"status": "closed"}, headers=admin_headers)
    assert response.status_code == 200, response.text


def _expire(oid):
    db_execute(
        "UPDATE opportunity SET deadline = :d WHERE id = :id",
        d=datetime.now(timezone.utc) - timedelta(hours=1),
        id=oid,
    )


def _assert_404(response, *absent):
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Opportunity not available — Workshop0</title>" in response.text
    assert '<meta name="robots" content="noindex">' in response.text
    assert "application/ld+json" not in response.text
    for needle in absent:
        assert needle not in response.text


def test_open_slug_serves_html_with_canonical_and_job_posting(client, create_opportunity):
    opp = create_opportunity(
        status="open", title="GenAI Workshop", location_mode="onsite",
        locations=[{"city": "Bengaluru", "country": "India"}],
    )
    response = client.get(f"/opportunities/{opp['slug']}", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    html = response.text
    assert f'<link rel="canonical" href="http://testserver/opportunities/{opp["slug"]}">' in html
    assert "<title>GenAI Workshop — Workshop0</title>" in html and html.count("<title>") == 1
    assert "noindex" not in html
    assert "client renders here" in html
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert data["@type"] == "JobPosting"
    assert data["jobLocation"][0]["address"]["addressLocality"] == "Bengaluru"
    assert data["url"] == opp["public_url"]


def test_numeric_id_301s_to_slug_keeping_the_query(client, create_opportunity):
    opp = create_opportunity(status="open")
    response = client.get(f"/opportunities/{opp['id']}?from=type%3Dworkshop", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"/opportunities/{opp['slug']}?from=type%3Dworkshop"
    plain = client.get(f"/opportunities/{opp['id']}", follow_redirects=False)
    assert plain.headers["location"] == f"/opportunities/{opp['slug']}"


def test_upper_case_slug_301s_to_lower_case(client, create_opportunity):
    opp = create_opportunity(status="open")
    response = client.get(f"/opportunities/{opp['slug'].upper()}", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"/opportunities/{opp['slug']}"


def test_trailing_slash_301s_to_slashless(client, create_opportunity):
    opp = create_opportunity(status="open")
    response = client.get(f"/opportunities/{opp['slug']}/?from=x", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == f"/opportunities/{opp['slug']}?from=x"
    assert client.get(f"/opportunities/{opp['slug']}/").status_code == 200


def test_drafts_unknown_and_malformed_keys_are_404_without_leaking(client, create_opportunity):
    draft = create_opportunity(title="ZZ-SECRET-DRAFT Title")
    assert draft["status"] == "draft"
    _assert_404(client.get(f"/opportunities/{draft['slug']}", follow_redirects=False), "ZZ-SECRET-DRAFT", draft["slug"])
    _assert_404(client.get(f"/opportunities/{draft['id']}", follow_redirects=False), "ZZ-SECRET-DRAFT")
    _assert_404(client.get("/opportunities/does-not-exist-0000", follow_redirects=False))
    _assert_404(client.get("/opportunities/999999", follow_redirects=False))
    _assert_404(client.get("/opportunities/a%20b%26c", follow_redirects=False))
    _assert_404(client.get("/opportunities/" + "a" * 81, follow_redirects=False))
    _assert_404(client.get("/opportunities/" + "9" * 13, follow_redirects=False))


def test_closed_and_expired_are_200_noindex_without_json_ld(client, admin_headers, create_opportunity):
    closed = create_opportunity(status="open", title="Closed One")
    _close(client, admin_headers, closed["id"])
    expired = create_opportunity(status="open", title="Expired One")
    _expire(expired["id"])
    for opp, title in ((closed, "Closed One"), (expired, "Expired One")):
        response = client.get(f"/opportunities/{opp['slug']}", follow_redirects=False)
        assert response.status_code == 200
        assert '<meta name="robots" content="noindex">' in response.text
        assert "application/ld+json" not in response.text
        assert f"<title>{title} — Workshop0</title>" in response.text


def test_missing_template_is_503(client, create_opportunity, monkeypatch, tmp_path):
    import src.workshop0.api.seo as seo_api

    opp = create_opportunity(status="open")
    monkeypatch.setattr(seo_api, "VIEW_HTML", tmp_path / "missing" / "index.html")
    response = client.get(f"/opportunities/{opp['slug']}", follow_redirects=False)
    assert response.status_code == 503
    assert "frontend not built" in response.text


def test_template_is_re_read_when_it_changes(client, create_opportunity, view_html):
    import os

    opp = create_opportunity(status="open")
    assert "client renders here" in client.get(f"/opportunities/{opp['slug']}").text
    view_html.write_text(TEMPLATE.replace("client renders here", "rebuilt export"), encoding="utf-8")
    stat = view_html.stat()
    os.utime(view_html, (stat.st_atime, stat.st_mtime + 5))
    assert "rebuilt export" in client.get(f"/opportunities/{opp['slug']}").text


def test_sitemap_lists_exactly_the_open_listings(client, admin_headers, create_opportunity):
    open_a = create_opportunity(status="open", title="Open A")
    open_b = create_opportunity(status="open", title="Open B")
    closed = create_opportunity(status="open", title="Closed")
    _close(client, admin_headers, closed["id"])
    expired = create_opportunity(status="open", title="Expired")
    _expire(expired["id"])
    draft = create_opportunity(title="Draft")
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    root = ET.fromstring(response.content)
    assert root.tag == f"{SITEMAP_NS}urlset"
    locs = [el.text for el in root.iter(f"{SITEMAP_NS}loc")]
    assert locs[0] == "http://testserver/opportunities"
    assert set(locs) == {"http://testserver/opportunities", open_a["public_url"], open_b["public_url"]}
    assert len(locs) == 3
    assert locs[1:] == [open_b["public_url"], open_a["public_url"]]  # newest published first
    for el in root.iter(f"{SITEMAP_NS}lastmod"):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", el.text)
    for gone in (closed, expired, draft):
        assert gone["slug"] not in response.text


def test_empty_sitemap_has_only_the_board(client):
    root = ET.fromstring(client.get("/sitemap.xml").content)
    assert [el.text for el in root.iter(f"{SITEMAP_NS}loc")] == ["http://testserver/opportunities"]


def test_robots_is_exact(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.text == ROBOTS.format(base="http://testserver")


def test_configured_base_url_is_used_everywhere(client, create_opportunity, monkeypatch):
    import src.workshop0.config.settings as settings_module

    monkeypatch.setenv("WORKSHOP0_BASE_URL", "https://workshop0.smalltech.in")
    settings_module._settings = None
    opp = create_opportunity(status="open")
    url = f"https://workshop0.smalltech.in/opportunities/{opp['slug']}"
    assert opp["public_url"] == url
    html = client.get(f"/opportunities/{opp['slug']}").text
    assert f'<link rel="canonical" href="{url}">' in html
    assert f'<meta property="og:url" content="{url}">' in html
    sitemap = client.get("/sitemap.xml").text
    assert f"<loc>{url}</loc>" in sitemap
    assert "<loc>https://workshop0.smalltech.in/opportunities</loc>" in sitemap
    assert client.get("/robots.txt").text == ROBOTS.format(base="https://workshop0.smalltech.in")


def test_board_redirect_is_unchanged(client):
    response = client.get("/opportunities", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/opportunities/"
