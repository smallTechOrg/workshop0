"""Server-rendered SEO for public listings, the sitemap and robots.txt (api.md §Phase 11e).

Pure functions. Every listing input is the PUBLIC detail dict built by the allow-list
serializer `services/opportunities.public_detail` — this module never sees an ORM row,
so admin-only fields are unreachable by construction. Only these keys are read:
title, summary, description_md, slug, type, location_mode, locations, published_at,
deadline, status, partner_display_name and the public compensation fields.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from xml.sax.saxutils import escape as xml_escape

SEO_START = "<!--w0-seo-->"
SEO_END = "<!--/w0-seo-->"
SITE_NAME = "Workshop0"
NOT_FOUND_TITLE = f"Opportunity not available — {SITE_NAME}"
DESCRIPTION_LIMIT = 160
DEFAULT_ORGANIZATION = "smallTech partner network"
NOINDEX = '<meta name="robots" content="noindex">'
_SALARY_UNITS = {"hour": "HOUR", "day": "DAY", "month": "MONTH"}

_TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title\s*>", re.IGNORECASE | re.DOTALL)
_DESCRIPTION_RE = re.compile(
    r"""<meta\b[^>]*\bname\s*=\s*["']?description["']?[^>]*>""", re.IGNORECASE
)
_HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.IGNORECASE)

ROBOTS_LINES = (
    "User-agent: *",
    "Disallow: /admin",
    "Disallow: /app/admin/",
    "Disallow: /api/",
    "Disallow: /network/me",
    "Disallow: /app/network/me/",
    "Disallow: /app/opportunities/view/",
    "Disallow: /f/",
    "Disallow: /p/",
    "Disallow: /app/f/",
    "Disallow: /app/p/",
)


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def cut_description(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    """At most `limit` characters; when cut, at a word boundary with `…` appended."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    if " " in head and text[limit - 1] != " ":
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.-—") + "…"


def listing_url(base_url: str, slug: str) -> str:
    return f"{base_url}/opportunities/{slug}"


def json_for_script(obj: dict) -> str:
    """JSON safe inside a <script> element: no `<`, `>`, `&`, U+2028 or U+2029 survive."""
    text = json.dumps(obj, ensure_ascii=False)
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def build_jobposting(listing: dict, url: str) -> dict:
    """schema.org JobPosting from the public listing dict (open listings only)."""
    published = listing.get("published_at") or ""
    posting: dict = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": listing["title"],
        "description": f"{listing.get('summary') or ''}\n\n{listing.get('description_md') or ''}",
        "datePosted": published[:10],
        "validThrough": listing["deadline"],
        "employmentType": "CONTRACTOR",
        "url": url,
        "hiringOrganization": {
            "@type": "Organization",
            "name": listing.get("partner_display_name") or DEFAULT_ORGANIZATION,
        },
    }
    if not published:
        del posting["datePosted"]
    if listing.get("location_mode") == "remote":
        posting["jobLocationType"] = "TELECOMMUTE"
        posting["applicantLocationRequirements"] = {"@type": "Country", "name": "India"}
    else:
        places = []
        for item in listing.get("locations") or []:
            address = {"@type": "PostalAddress", "addressLocality": item["city"]}
            if item.get("country"):
                address["addressCountry"] = item["country"]
            places.append({"@type": "Place", "address": address})
        if places:
            posting["jobLocation"] = places
    salary = _base_salary(listing)
    if salary is not None:
        posting["baseSalary"] = salary
    return posting


def _base_salary(listing: dict) -> dict | None:
    unit = _SALARY_UNITS.get(listing.get("compensation_unit") or "")
    low, high = listing.get("compensation_min"), listing.get("compensation_max")
    if unit is None or (low is None and high is None):
        return None
    value: dict = {"@type": "QuantitativeValue"}
    if low is not None and high is not None and low == high:
        value["value"] = low
    else:
        if low is not None:
            value["minValue"] = low
        if high is not None:
            value["maxValue"] = high
    value["unitText"] = unit
    return {
        "@type": "MonetaryAmount",
        "currency": listing.get("compensation_currency") or "INR",
        "value": value,
    }


def build_head_block(listing: dict | None, base_url: str) -> str:
    """The marker-wrapped block injected before </head>."""
    if listing is None:
        lines = [f"<title>{_esc(NOT_FOUND_TITLE)}</title>", NOINDEX]
        return SEO_START + "\n".join(lines) + SEO_END
    url = listing_url(base_url, listing["slug"])
    title = _esc(listing["title"])
    description = _esc(cut_description(listing.get("summary") or ""))
    is_open = listing.get("status") == "open"
    lines = [f"<title>{title} — {SITE_NAME}</title>"]
    if not is_open:
        lines.append(NOINDEX)
    lines += [
        f'<meta name="description" content="{description}">',
        f'<link rel="canonical" href="{_esc(url)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{description}">',
        f'<meta property="og:url" content="{_esc(url)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{description}">',
    ]
    if is_open:
        lines.append(
            '<script type="application/ld+json">'
            + json_for_script(build_jobposting(listing, url))
            + "</script>"
        )
    return SEO_START + "\n".join(lines) + SEO_END


def render_listing_html(
    template: str, listing: dict | None, base_url: str, now: datetime | None = None
) -> str:
    """The exported view page with its own <title>/description removed and the SEO
    block inserted before </head>. `listing` is the public detail dict (its effective
    `status` was computed at `now` by the serializer) or None for not-found."""
    page = _TITLE_RE.sub("", template)
    page = _DESCRIPTION_RE.sub("", page)
    block = build_head_block(listing, base_url)
    match = _HEAD_CLOSE_RE.search(page)
    if match is None:
        return block + page
    return page[: match.start()] + block + page[match.start() :]


def render_sitemap(base_url: str, entries: list[tuple[str, date | datetime]]) -> str:
    """`entries` = (public_url, updated_at) per effective-open listing, already ordered."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"<url><loc>{xml_escape(base_url + '/opportunities')}</loc></url>",
    ]
    for url, updated in entries:
        day = updated.date() if isinstance(updated, datetime) else updated
        parts.append(
            f"<url><loc>{xml_escape(url)}</loc><lastmod>{day.isoformat()}</lastmod></url>"
        )
    parts.append("</urlset>")
    return "\n".join(parts) + "\n"


def render_robots(base_url: str) -> str:
    return "\n".join((*ROBOTS_LINES, f"Sitemap: {base_url}/sitemap.xml")) + "\n"
