"""Apply / withdraw / pipeline / bulk status (spec/api.md §Phase 12, C14).

Thin routers call these functions; they own the rules. Callers commit. Emails go through
`email.outbox.enqueue` in the caller's transaction (consent-gated for status changes);
routes call `sender.schedule_drain` after the commit.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import datetime
from typing import Any

import structlog
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, iso_z, utcnow
from src.workshop0.db.models import (
    AppUser,
    Application,
    Opportunity,
    OpportunityInvite,
    TrainerProfile,
)
from src.workshop0.email import outbox
from src.workshop0.services import opportunities as opps
from src.workshop0.services import matching
from src.workshop0.services.audit import record_action
from src.workshop0.services.pool import _csv_cell
from src.workshop0.services.topics import ADMIN_ACTOR

log = structlog.get_logger("workshop0")

NOTE_MAX = 1000
BULK_MAX = 200
APPLY_LIMIT, APPLY_WINDOW_S = 30, 3600
PIPELINE_STATUSES = ("applied", "shortlisted", "selected", "not_selected")
ALL_STATUSES = PIPELINE_STATUSES + ("withdrawn",)
WITHDRAWABLE = ("applied", "shortlisted")
STATUS_LABELS = {
    "applied": "Applied",
    "shortlisted": "Shortlisted",
    "selected": "Selected",
    "not_selected": "Not selected",
    "withdrawn": "Withdrawn",
}
APPLICATIONS_PATH = "/app/network/applications/"


# --------------------------------------------------------------------------- bodies


class ApplyBody(BaseModel):
    opportunity_id: int
    note: str | None = None

    @field_validator("note")
    @classmethod
    def _note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > NOTE_MAX:
            raise ValueError(f"must be at most {NOTE_MAX} characters")
        return v or None


class BulkStatusBody(BaseModel):
    application_ids: list[int]
    status: str
    notify: bool = True

    @field_validator("application_ids")
    @classmethod
    def _ids(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("choose at least one application")
        if len(v) > BULK_MAX:
            raise ValueError(f"at most {BULK_MAX} applications per move")
        return list(dict.fromkeys(v))

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in PIPELINE_STATUSES:
            raise ValueError(f"must be one of {', '.join(PIPELINE_STATUSES)}")
        return v


# --------------------------------------------------------------------------- helpers


def _profile_for(session: Session, user_id: int) -> TrainerProfile:
    profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))
    if profile is None:
        raise api_error(
            "profile_required", "Create your trainer profile before applying.", 409
        )
    return profile


def _applications_url(base_url: str) -> str:
    return f"{base_url}{APPLICATIONS_PATH}"


def _email_context(
    opp: Opportunity, user: AppUser, base_url: str, *, status: str | None = None
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "name": user.display_name,
        "title": opp.title,
        "url": opps.public_url(base_url, opp.slug),  # slug URL, never the numeric id
        "applications_url": _applications_url(base_url),
    }
    ctx["public_url"] = ctx["url"]
    if status is not None:
        ctx["status"] = status
        ctx["status_label"] = STATUS_LABELS.get(status, status)
    return ctx


def _card(session: Session, opp: Opportunity, base_url: str, now: datetime) -> dict:
    topics = opps.topics_by_opportunity(session, [opp.id])[opp.id]
    return opps.public_card(opp, topics, base_url, now)


def _serialize_mine(app: Application, card: dict) -> dict:
    return {
        "id": app.id,
        "opportunity_id": app.opportunity_id,
        "status": app.status,
        "note": app.note,
        "source": app.source,
        "status_changed_at": iso_z(app.status_changed_at),
        "created_at": iso_z(app.created_at),
        "opportunity": card,
    }


# --------------------------------------------------------------------------- trainer


def apply(session: Session, user_id: int, body: ApplyBody, *, base_url: str) -> dict:
    now = utcnow()
    profile = _profile_for(session, user_id)
    opp = session.get(Opportunity, body.opportunity_id) if 1 <= body.opportunity_id <= opps.ID_MAX else None
    if opp is None or opp.status == "draft":
        # A draft is not public: indistinguishable from a missing listing.
        raise api_error("not_found", opps.NOT_FOUND_MESSAGE, 404)
    if opps.effective_status(opp, now) != "open":
        raise api_error(
            "opportunity_closed", "This opportunity is no longer accepting applications.", 409
        )
    existing = session.scalar(
        select(Application.id).where(
            Application.opportunity_id == opp.id, Application.profile_id == profile.id
        )
    )
    if existing is not None:
        raise api_error("already_applied", "You've already applied to this opportunity.", 409)
    invited = session.scalar(
        select(OpportunityInvite.id).where(
            OpportunityInvite.opportunity_id == opp.id, OpportunityInvite.profile_id == profile.id
        )
    )
    app = Application(
        opportunity_id=opp.id,
        profile_id=profile.id,
        status="applied",
        note=body.note,
        source="invited" if invited is not None else "self",
        status_changed_at=now,
        created_at=now,
        updated_at=now,
    )
    try:
        with session.begin_nested():
            session.add(app)
    except IntegrityError:  # concurrent double-click: the unique constraint is the arbiter
        raise api_error("already_applied", "You've already applied to this opportunity.", 409)
    user = session.get(AppUser, user_id)
    outbox.enqueue(
        session,
        to=user.email,
        template="application.received",
        context=_email_context(opp, user, base_url),
        dedupe_key=f"applied:{app.id}",
    )
    log.info("application.created", application_id=app.id, opportunity_id=opp.id, source=app.source)
    return _serialize_mine(app, _card(session, opp, base_url, now))


def list_mine(session: Session, user_id: int, *, base_url: str) -> dict:
    profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))
    if profile is None:
        return {"applications": []}
    now = utcnow()
    rows = list(
        session.scalars(
            select(Application)
            .where(Application.profile_id == profile.id)
            .order_by(Application.created_at.desc(), Application.id.desc())
        )
    )
    opp_rows = {
        o.id: o
        for o in session.scalars(
            select(Opportunity).where(Opportunity.id.in_([a.opportunity_id for a in rows]))
        )
    } if rows else {}
    topics = opps.topics_by_opportunity(session, list(opp_rows))
    return {
        "applications": [
            _serialize_mine(
                a, opps.public_card(opp_rows[a.opportunity_id], topics[a.opportunity_id], base_url, now)
            )
            for a in rows
        ]
    }


def withdraw(session: Session, user_id: int, application_id: int, *, base_url: str) -> dict:
    profile = _profile_for(session, user_id)
    app = session.get(Application, application_id) if 1 <= application_id <= opps.ID_MAX else None
    if app is None or app.profile_id != profile.id:  # someone else's id is just "not found"
        raise api_error("not_found", "No application matches this id.", 404)
    if app.status not in WITHDRAWABLE:
        raise api_error(
            "cannot_withdraw",
            "Only applied or shortlisted applications can be withdrawn.",
            409,
        )
    now = utcnow()
    app.status = "withdrawn"
    app.status_changed_at = now
    app.updated_at = now
    opp = session.get(Opportunity, app.opportunity_id)
    log.info("application.status_changed", application_id=app.id, to_status="withdrawn", by="trainer")
    return _serialize_mine(app, _card(session, opp, base_url, now))


def matches(session: Session, user_id: int, *, base_url: str, limit: int = 10) -> dict:
    profile = _profile_for(session, user_id)
    now = utcnow()
    found = matching.matches_for(session, profile, limit=limit)
    topics = opps.topics_by_opportunity(session, [m.opportunity.id for m in found])
    return {
        "matches": [
            {
                "opportunity": opps.public_card(
                    m.opportunity, topics[m.opportunity.id], base_url, now
                ),
                "rule_score": round(float(m.rule_score), 3),
                "invited": bool(m.invited),
            }
            for m in found
        ]
    }


# --------------------------------------------------------------------------- admin


def _opp_or_404(session: Session, opportunity_id: int) -> Opportunity:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise api_error("not_found", opps.NOT_FOUND_MESSAGE, 404)
    return opp


def _pipeline_rows(session: Session, opportunity_id: int, status: str | None):
    stmt = (
        select(Application, TrainerProfile, AppUser)
        .join(TrainerProfile, TrainerProfile.id == Application.profile_id)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(Application.opportunity_id == opportunity_id)
        .order_by(Application.created_at.asc(), Application.id.asc())
    )
    if status is not None:
        stmt = stmt.where(Application.status == status)
    return stmt


def _pipeline_row(app: Application, profile: TrainerProfile, user: AppUser) -> dict:
    return {
        "id": app.id,
        "opportunity_id": app.opportunity_id,
        "status": app.status,
        "note": app.note,
        "source": app.source,
        "status_changed_at": iso_z(app.status_changed_at),
        "created_at": iso_z(app.created_at),
        "trainer": {
            "id": profile.id,
            "user_id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "headline": profile.headline,
            "city": profile.city,
            "remote_ok": bool(profile.remote_ok),
            "verified": bool(profile.verified),
        },
    }


def list_pipeline(
    session: Session, opportunity_id: int, *, status: str | None, page: int, page_size: int
) -> dict:
    _opp_or_404(session, opportunity_id)
    if status is not None and status not in ALL_STATUSES:
        raise opps.validation_error(f"status: must be one of {', '.join(ALL_STATUSES)}")
    stmt = _pipeline_rows(session, opportunity_id, status)
    total = int(
        session.scalar(
            select(func.count(Application.id)).where(
                Application.opportunity_id == opportunity_id,
                *([Application.status == status] if status is not None else []),
            )
        )
        or 0
    )
    rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    counts = {s: 0 for s in ALL_STATUSES}
    counts.update(
        {
            s: int(n)
            for s, n in session.execute(
                select(Application.status, func.count(Application.id))
                .where(Application.opportunity_id == opportunity_id)
                .group_by(Application.status)
            ).all()
        }
    )
    return {
        "applications": [_pipeline_row(*r) for r in rows],
        "counts": counts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def bulk_status(
    session: Session, opportunity_id: int, body: BulkStatusBody, *, base_url: str, by: str
) -> dict:
    opp = _opp_or_404(session, opportunity_id)
    apps = {
        a.id: a
        for a in session.scalars(
            select(Application)
            .where(Application.id.in_(body.application_ids))
            .with_for_update()
        )
    }
    missing = [i for i in body.application_ids if i not in apps or apps[i].opportunity_id != opp.id]
    if missing:
        raise api_error(
            "not_found", f"No application on this listing matches id {missing[0]}.", 404
        )
    withdrawn = [i for i, a in apps.items() if a.status == "withdrawn"]
    if withdrawn:
        raise api_error(
            "application_withdrawn",
            f"Application {withdrawn[0]} was withdrawn by the trainer and can't be moved.",
            409,
        )
    now = utcnow()
    changed, unchanged = [], []
    for app_id in body.application_ids:
        app = apps[app_id]
        if app.status == body.status:
            unchanged.append(app_id)
            continue
        app.status = body.status
        app.status_changed_at = now
        app.updated_at = now
        changed.append(app_id)

    queued, skipped = 0, []
    if body.notify and changed:
        for app_id in changed:
            app = apps[app_id]
            profile = session.get(TrainerProfile, app.profile_id)
            user = session.get(AppUser, profile.user_id)
            if profile.consent_at is None:  # consent gate: no row, noted in the audit entry
                skipped.append(app_id)
                continue
            outbox.enqueue(
                session,
                to=user.email,
                template="application.status_changed",
                context=_email_context(opp, user, base_url, status=body.status),
                dedupe_key=f"status:{app_id}:{body.status}",
            )
            queued += 1

    if changed:
        detail: dict[str, Any] = {
            "opportunity_id": opp.id,
            "application_ids": changed,
            "to_status": body.status,
            "notify": body.notify,
            "emails_queued": queued,
            "by": by,
        }
        if skipped:
            detail["skipped_no_consent"] = skipped
        record_action(
            session, None, ADMIN_ACTOR, "application.status", detail,
            subject_type="opportunity", subject_id=opp.id,
        )
        log.info(
            "application.status_changed",
            opportunity_id=opp.id,
            count=len(changed),
            to_status=body.status,
            emails_queued=queued,
        )
    return {
        "changed": changed,
        "unchanged": unchanged,
        "status": body.status,
        "emails_queued": queued,
        "skipped_no_consent": skipped,
    }


CSV_COLUMNS = (
    "application_id", "status", "source", "name", "email", "headline", "city",
    "verified", "note", "applied_at", "status_changed_at",
)


def export_csv(session: Session, opportunity_id: int) -> tuple[str, str]:
    """(filename, csv text) for the whole pipeline (every status, withdrawn included)."""
    opp = _opp_or_404(session, opportunity_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for app, profile, user in session.execute(_pipeline_rows(session, opp.id, None)).all():
        writer.writerow(
            _csv_cell(v)
            for v in (
                app.id, app.status, app.source, user.display_name, user.email, profile.headline,
                profile.city, bool(profile.verified), app.note, iso_z(app.created_at),
                iso_z(app.status_changed_at),
            )
        )
    return f"workshop0-applicants-{opp.slug}.csv", buffer.getvalue()
