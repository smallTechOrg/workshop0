"""Phase 13: `/api/email/unsubscribe` and `/api/cron/weekly-digest`."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, ok, request_base_url, utcnow
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AppUser
from src.workshop0.db.session import get_session
from src.workshop0.email import sender
from src.workshop0.services import audit, digest, email_prefs, unsubscribe

router = APIRouter(tags=["network-public"])

_INVALID = "/app/network/unsubscribed/?error=invalid_link"


@router.get("/api/email/unsubscribe")
def unsubscribe_link(t: str = Query(default=""), session: Session = Depends(get_session)):
    try:
        user_id, kind = unsubscribe.read_token(t)
    except ValueError:
        return RedirectResponse(_INVALID, status_code=303)
    if session.get(AppUser, user_id) is None:
        return RedirectResponse(_INVALID, status_code=303)
    email_prefs.set_prefs(session, user_id, **{kind: False})
    audit.record_action(session, None, "user", "email.unsubscribe", {"kind": kind})
    session.commit()
    return RedirectResponse(f"/app/network/unsubscribed/?kind={kind}", status_code=303)


@router.post("/api/cron/weekly-digest")
def weekly_digest(
    request: Request,
    background: BackgroundTasks,
    x_cron_key: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict:
    settings = get_settings()
    if not settings.cron_enabled:
        raise api_error("not_found", "Not found.", 404)
    expected = settings.workshop0_cron_key.get_secret_value().strip()
    if not x_cron_key or not hmac.compare_digest(x_cron_key.encode(), expected.encode()):
        raise api_error("invalid_cron_key", "Invalid cron key.", 401)
    result = digest.run_weekly(session, now=utcnow(), base_url=request_base_url(request))
    audit.record_action(session, None, "cron", "cron.weekly_digest", dict(result))
    session.commit()
    sender.schedule_drain(background, limit=100)
    return ok(result)
