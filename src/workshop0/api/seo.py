"""Server-rendered public listing pages, sitemap and robots (api.md §Phase 11e).

Registered in create_app() BEFORE the /app static mount. Listing data reaches the HTML
only through the public allow-list serializer (`opportunities.public_detail`).
"""

import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from src.workshop0.api._common import request_base_url, utcnow
from src.workshop0.db.session import get_session
from src.workshop0.services import opportunities, seo

_REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_OUT_DIR = _REPO_ROOT / "frontend" / "out"
VIEW_HTML = FRONTEND_OUT_DIR / "opportunities/view/index.html"

NOT_BUILT_MESSAGE = "frontend not built — run `pnpm build` in frontend/"
_KEY_RE = re.compile(r"[A-Za-z0-9-]{1,80}")
_NUMERIC_RE = re.compile(r"[0-9]{1,12}")
_HTML_HEADERS = {"Cache-Control": "no-cache"}

router = APIRouter(include_in_schema=False)

_template_cache: dict[str, tuple[Path, float, str]] = {}


def _load_template() -> str | None:
    """VIEW_HTML read once, re-read when its mtime (or the patched path) changes."""
    path = Path(VIEW_HTML)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _template_cache.get("view")
    if cached and cached[0] == path and cached[1] == mtime:
        return cached[2]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    _template_cache["view"] = (path, mtime, text)
    return text


def _redirect(slug: str, request: Request) -> RedirectResponse:
    query = request.url.query
    target = f"/opportunities/{slug}" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=301)


def _page(listing: dict | None, base_url: str, status_code: int) -> Response:
    template = _load_template()
    if template is None:
        return PlainTextResponse(NOT_BUILT_MESSAGE, status_code=503)
    body = seo.render_listing_html(template, listing, base_url, utcnow())
    return HTMLResponse(body, status_code=status_code, headers=_HTML_HEADERS)


@router.get("/opportunities/{key}/")
def listing_trailing_slash(key: str, request: Request) -> RedirectResponse:
    query = request.url.query
    path = f"/opportunities/{quote(key, safe='')}"
    return RedirectResponse(url=path + (f"?{query}" if query else ""), status_code=301)


@router.get("/opportunities/{key}")
def listing_page(key: str, request: Request, session: Session = Depends(get_session)) -> Response:
    base_url = request_base_url(request)
    opp = opportunities.find_public(session, key) if _KEY_RE.fullmatch(key) else None
    if opp is None:
        return _page(None, base_url, 404)
    if _NUMERIC_RE.fullmatch(key) or key != opp.slug:
        return _redirect(opp.slug, request)
    topics = opportunities.topics_by_opportunity(session, [opp.id])[opp.id]
    listing = opportunities.public_detail(opp, topics, base_url, utcnow())
    return _page(listing, base_url, 200)


@router.get("/sitemap.xml")
def sitemap(request: Request, session: Session = Depends(get_session)) -> Response:
    base_url = request_base_url(request)
    entries = [
        (opportunities.public_url(base_url, opp.slug), opp.updated_at)
        for opp in opportunities.list_open(session, utcnow())
    ]
    return Response(
        seo.render_sitemap(base_url, entries), media_type="application/xml; charset=utf-8"
    )


@router.get("/robots.txt")
def robots(request: Request) -> PlainTextResponse:
    return PlainTextResponse(seo.render_robots(request_base_url(request)))
