"""create_app(): routers, error envelope, pretty-link redirects, guarded static mount."""

from pathlib import Path
from urllib.parse import quote

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles

from src.workshop0 import __version__
from src.workshop0.config.settings import get_settings
from src.workshop0.observability.logging import RequestLoggingMiddleware, configure_logging

_REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_OUT_DIR = _REPO_ROOT / "frontend" / "out"
LANDING_HTML = FRONTEND_OUT_DIR / "index.html"


def _first_validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid input."
    first = errors[0]
    location = ".".join(
        str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path")
    )
    message = first.get("msg", "Invalid input.")
    message = message.removeprefix("Value error, ")
    return f"{location}: {message}" if location else message


def create_app() -> FastAPI:
    settings = get_settings()
    if not settings.resolved_admin_key:
        raise RuntimeError(
            "WORKSHOP0_ADMIN_KEY is not set. Add it to .env (see .env.example) — "
            "the facilitator access key is required to start."
        )
    configure_logging(settings.resolved_log_level)
    log = structlog.get_logger("workshop0")

    # Phase 11 — identity settings rules (issuer scheme, session secret) fail fast here,
    # before any route is built.
    from src.workshop0.auth import startup as auth_startup

    auth_startup.validate_settings(settings)

    app = FastAPI(title="Workshop0", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(RequestLoggingMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": {"code": "validation_error", "message": _first_validation_message(exc)}
            },
        )

    @app.exception_handler(Exception)
    async def _internal_error_handler(request: Request, exc: Exception):
        structlog.get_logger("workshop0").error(
            "internal_error", path=request.url.path, error=repr(exc)
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "internal_error",
                    "message": "Unexpected server error — check the server logs.",
                }
            },
        )

    from src.workshop0.api import (
        admin,
        board_admin,
        board_ai_admin,
        board_public,
        directory_public,
        facilitator,
        health,
        matching_admin,
        network_admin,
        network_me,
        network_public,
        outbox_admin,
        participant,
        partners_admin,
        pipeline_admin,
        public,
        seo,
    )
    from src.workshop0.auth import routes as auth_routes

    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(public.router)
    app.include_router(facilitator.router)
    app.include_router(participant.router)
    app.include_router(board_public.router)
    app.include_router(board_admin.router)
    app.include_router(partners_admin.router)
    app.include_router(board_ai_admin.router)
    # Phase 11 — network identity, trainer self-service, admin trainer pool.
    app.include_router(auth_routes.router)  # /api/auth
    app.include_router(network_me.router)  # /api/me
    app.include_router(network_admin.router)  # /api/admin/network (require_admin_key)
    # Phase 12 - router shells (routes filled by later slices).
    app.include_router(outbox_admin.router)  # /api/admin/outbox
    app.include_router(pipeline_admin.router)  # /api/admin/opportunities/{id}/applications...
    app.include_router(matching_admin.router)  # /api/admin/opportunities/{id}/shortlist|invites

    @app.get("/", include_in_schema=False)
    def _landing():
        """The public marketing landing page — the export root served as-is.

        The landing page has exactly ONE URL: `/`. When the frontend has not
        been built there is nowhere to fall back to (`/app/` redirects here,
        which would loop), so say so plainly with a 503.
        """
        if not LANDING_HTML.is_file():
            return PlainTextResponse(
                "frontend not built — run `pnpm build` in frontend/",
                status_code=503,
            )
        return FileResponse(
            LANDING_HTML, media_type="text/html", headers={"Cache-Control": "no-cache"}
        )

    # The landing page has exactly one URL. `/app` and `/app/` are the same
    # exported index.html by virtue of `basePath: '/app'`; send them to `/`.
    # Declared BEFORE the StaticFiles mount so routes win over the mount.
    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    def _app_root_redirect():
        return RedirectResponse(url="/", status_code=307)

    @app.get("/admin", include_in_schema=False)
    def _admin_redirect():
        return RedirectResponse(url="/app/admin/", status_code=307)

    @app.get("/j/{join_slug}", include_in_schema=False)
    def _join_redirect(join_slug: str):
        return RedirectResponse(url=f"/app/join/?s={quote(join_slug, safe='')}", status_code=307)

    @app.get("/p/{participant_token}", include_in_schema=False)
    def _participant_redirect(participant_token: str):
        return RedirectResponse(
            url=f"/app/p/?t={quote(participant_token, safe='')}", status_code=307
        )

    @app.get("/f/{admin_token}", include_in_schema=False)
    def _facilitator_redirect(admin_token: str):
        return RedirectResponse(url=f"/app/f/?t={quote(admin_token, safe='')}", status_code=307)

    # Phase 10 — Opportunity Board pretty links (before the static mount).
    @app.get("/opportunities", include_in_schema=False)
    def _opportunities_redirect():
        return RedirectResponse(url="/app/opportunities/", status_code=307)

    # Phase 11e — server-rendered listing pages, sitemap and robots (api/seo.py).
    app.include_router(seo.router)

    # Phase 13 - unsubscribe/cron and the public directory API (before the static mount).
    app.include_router(network_public.router)
    app.include_router(directory_public.router)

    # Phase 11 — invite + pretty network links (before the static mount).
    @app.get("/invite/{token}", include_in_schema=False)
    def _invite_redirect(token: str):
        return RedirectResponse(
            url=f"/app/network/join/?invite={quote(token, safe='')}", status_code=307
        )

    @app.get("/network", include_in_schema=False)
    def _network_redirect():
        return RedirectResponse(url="/app/network/", status_code=307)

    frontend_mounted = FRONTEND_OUT_DIR.is_dir()
    if frontend_mounted:
        app.mount("/app", StaticFiles(directory=FRONTEND_OUT_DIR, html=True), name="app")

    anthropic_key_present = bool(settings.anthropic_api_key.strip())
    anthropic_workspace_present = bool(settings.anthropic_workspace_id.strip())
    log.info(
        "app.startup",
        version=__version__,
        admin_key_present=bool(settings.resolved_admin_key),
        openrouter_key_present=bool(settings.openrouter_api_key),
        anthropic_key_present=anthropic_key_present,
        anthropic_workspace_present=anthropic_workspace_present,
        db_dialect=settings.database_url.split(":", 1)[0],
        frontend_mounted=frontend_mounted,
    )
    if anthropic_key_present and not anthropic_workspace_present:
        # Key without workspace id: every request would 400, so network AI is treated as
        # unavailable (agent.md §Provider). Logged once per app build.
        log.warning("ai.network_misconfigured", reason="workspace_id_missing")
    return app
