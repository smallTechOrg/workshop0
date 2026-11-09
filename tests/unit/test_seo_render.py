"""Phase 11e — pure SEO rendering (api.md §Phase 11e), on a fixture template."""

import json
import re
from datetime import datetime, timezone

from src.workshop0.services import seo

TEMPLATE = (
    "<!DOCTYPE html><html><head><meta charSet=\"utf-8\"/>"
    "<title>Workshop0</title>"
    '<meta name="description" content="Default site description"/>'
    '<link rel="stylesheet" href="/app/_next/x.css"/></head>'
    "<body><div id=\"root\">loading</div></body></html>"
)
BASE = "https://example.test"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def listing(**overrides) -> dict:
    body = {
        "id": 7,
        "slug": "genai-workshop-bengaluru-a3f9",
        "title": "GenAI Workshop",
        "type": "workshop",
        "summary": "Hands-on LLM workshop for PMs.",
        "description_md": "## Agenda\n- Prompting",
        "partner_display_name": "A Bengaluru fintech",
        "location_mode": "hybrid",
        "city": "Bengaluru",
        "locations": [{"city": "Bengaluru", "country": "India"}, {"city": "Pune", "country": None}],
        "compensation_min": 8000,
        "compensation_max": 12000,
        "compensation_currency": "INR",
        "compensation_unit": "day",
        "compensation_text": None,
        "deadline": "2026-12-01T18:29:59Z",
        "published_at": "2026-11-01T10:00:00Z",
        "status": "open",
    }
    body.update(overrides)
    return body


def render(item):
    return seo.render_listing_html(TEMPLATE, item, BASE, NOW)


def ld_json(page: str) -> dict:
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.DOTALL)
    assert len(blocks) == 1
    return json.loads(blocks[0])


def test_title_and_description_are_replaced_exactly_once():
    page = render(listing())
    assert page.count("<title>") == 1
    assert "<title>GenAI Workshop — Workshop0</title>" in page
    assert len(re.findall(r'<meta name="description"', page)) == 1
    assert "Default site description" not in page
    assert '<link rel="canonical" href="https://example.test/opportunities/genai-workshop-bengaluru-a3f9">' in page
    assert '<meta property="og:url" content="https://example.test/opportunities/genai-workshop-bengaluru-a3f9">' in page
    assert '<meta name="twitter:card" content="summary">' in page
    assert "noindex" not in page


def test_block_sits_between_markers_just_before_head_close():
    page = render(listing())
    start, end, close = page.index(seo.SEO_START), page.index(seo.SEO_END), page.index("</head>")
    assert start < end < close
    assert page[end + len(seo.SEO_END) : close] == ""
    assert "<title>" in page[start:end]
    assert '<link rel="stylesheet"' in page  # the rest of the head is kept


def test_hostile_title_is_escaped_everywhere_and_json_ld_round_trips():
    title = '</script><script>alert(1)</script>"&<b>'
    page = render(listing(title=title))
    assert "<script>alert" not in page
    assert "<b>" not in page
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;&quot;&amp;&lt;b&gt;" in page
    assert ld_json(page)["title"] == title
    assert page.count("</script>") == 1  # only the JSON-LD element closes


def test_json_for_script_escapes_line_separators():
    out = seo.json_for_script({"t": "a b c<>&"})
    assert " " not in out and " " not in out and "<" not in out and "&" not in out
    assert json.loads(out) == {"t": "a b c<>&"}


def test_description_is_cut_at_160_on_a_word_boundary():
    summary = ("word " * 60).strip()
    cut = seo.cut_description(summary)
    assert len(cut) <= 160 and cut.endswith("…")
    assert cut[:-1].split(" ")[-1] == "word"
    assert seo.cut_description("short one") == "short one"
    exact = "x" * 160
    assert seo.cut_description(exact) == exact
    page = render(listing(summary=summary))
    assert f'<meta name="description" content="{cut}">' in page


def test_jobposting_hybrid_two_places_and_day_salary():
    data = ld_json(render(listing()))
    assert data["@type"] == "JobPosting" and data["@context"] == "https://schema.org"
    assert data["employmentType"] == "CONTRACTOR"
    assert data["datePosted"] == "2026-11-01"
    assert data["validThrough"] == "2026-12-01T18:29:59Z"
    assert data["description"] == "Hands-on LLM workshop for PMs.\n\n## Agenda\n- Prompting"
    assert data["url"] == f"{BASE}/opportunities/genai-workshop-bengaluru-a3f9"
    assert data["hiringOrganization"] == {"@type": "Organization", "name": "A Bengaluru fintech"}
    assert data["jobLocation"] == [
        {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Bengaluru", "addressCountry": "India"}},
        {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Pune"}},
    ]
    assert data["baseSalary"] == {
        "@type": "MonetaryAmount",
        "currency": "INR",
        "value": {"@type": "QuantitativeValue", "minValue": 8000, "maxValue": 12000, "unitText": "DAY"},
    }
    assert "jobLocationType" not in data


def test_jobposting_remote_is_telecommute_india_without_job_location():
    data = ld_json(render(listing(location_mode="remote", locations=[], city=None)))
    assert data["jobLocationType"] == "TELECOMMUTE"
    assert data["applicantLocationRequirements"] == {"@type": "Country", "name": "India"}
    assert "jobLocation" not in data


def test_salary_rules_course_omitted_equal_gives_value_and_null_display_name():
    assert "baseSalary" not in ld_json(render(listing(compensation_unit="course")))
    assert "baseSalary" not in ld_json(render(listing(compensation_min=None, compensation_max=None)))
    same = ld_json(render(listing(compensation_min=5000, compensation_max=5000, compensation_unit="hour")))
    assert same["baseSalary"]["value"] == {"@type": "QuantitativeValue", "value": 5000, "unitText": "HOUR"}
    only_min = ld_json(render(listing(compensation_max=None, compensation_unit="month")))
    assert only_min["baseSalary"]["value"] == {"@type": "QuantitativeValue", "minValue": 8000, "unitText": "MONTH"}
    anon = ld_json(render(listing(partner_display_name=None)))
    assert anon["hiringOrganization"]["name"] == "smallTech partner network"


def test_closed_and_expired_are_noindex_without_json_ld():
    for status in ("closed", "expired"):
        page = render(listing(status=status))
        assert '<meta name="robots" content="noindex">' in page
        assert "application/ld+json" not in page
        assert "<title>GenAI Workshop — Workshop0</title>" in page
        assert 'rel="canonical"' in page


def test_not_found_is_generic_noindex_with_no_listing_text():
    page = render(None)
    assert "<title>Opportunity not available — Workshop0</title>" in page
    assert '<meta name="robots" content="noindex">' in page
    assert "application/ld+json" not in page
    assert "GenAI" not in page and "canonical" not in page
    assert page.count("<title>") == 1


def test_template_without_head_close_still_gets_the_block():
    page = seo.render_listing_html("<html><body>x</body></html>", None, BASE, NOW)
    assert page.startswith(seo.SEO_START)


def test_sitemap_and_robots():
    xml = seo.render_sitemap(BASE, [(f"{BASE}/opportunities/a-b-1234?x=1&y=2", NOW)])
    assert "<loc>https://example.test/opportunities</loc>" in xml
    assert "<loc>https://example.test/opportunities/a-b-1234?x=1&amp;y=2</loc><lastmod>2026-11-10</lastmod>" in xml
    robots = seo.render_robots(BASE)
    assert robots.splitlines()[0] == "User-agent: *"
    assert robots.splitlines()[-1] == "Sitemap: https://example.test/sitemap.xml"
    assert "Disallow: /network/me" in robots.splitlines()
