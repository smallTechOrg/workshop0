"""`/api/admin/opportunities/{id}/shortlist|invites` (spec/api.md §Phase 12; agent.md §Shortlist ranker).

Admin-only (`require_admin_key`). Thin HTTP layer over `ai/shortlist_rank.py` and
`services/matching.py`; the invite route enqueues `opportunity.invite` mail (consent-gated).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.ai import shortlist_rank
from src.workshop0.api._common import api_error, ok, request_base_url, utcnow
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.models import (
    AiUsage,
    AppUser,
    MatchSuggestion,
    Opportunity,
    OpportunityInvite,
    TrainerProfile,
)
from src.workshop0.db.session import get_session
from src.workshop0.email import outbox, sender
from src.workshop0.security import require_admin_key
from src.workshop0.services import matching, pool, ratelimit
from src.workshop0.services.audit import record_action
from src.workshop0.services.listing_text import listing_fields
from src.workshop0.services.opportunities import effective_status, parse_path_id

log = structlog.get_logger("workshop0")

router = APIRouter(prefix="/api/admin/opportunities", dependencies=[Depends(require_admin_key)])

NOT_FOUND = "No opportunity matches this id."
RATE_BUCKET = "shortlist_rank"
RATE_LIMIT = 20
RATE_WINDOW_S = 3600
INVITE_MAX = 50


class InviteBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    profile_ids: list[int]


def _opportunity(session: Session, raw_id: str) -> Opportunity:
    opp = session.get(Opportunity, parse_path_id(raw_id, NOT_FOUND))
    if opp is None:
        raise api_error("not_found", NOT_FOUND, 404)
    return opp


def _money(value) -> float:
    return float(round(Decimal(str(value or 0)), 6))


def _payload(
    session: Session,
    opp: Opportunity,
    *,
    run_id: str | None,
    ranked_by: str | None,
    suggestions: list[dict],
    cost: Decimal,
) -> dict:
    rows = pool.trainer_rows(session, [s["profile_id"] for s in suggestions])
    invited = matching.invited_profile_ids(session, opp.id)
    return {
        "run_id": run_id,
        "ranked_by": ranked_by,
        "suggestions": [
            {
                "rank": s["rank"],
                "trainer": rows[s["profile_id"]],
                "rule_score": float(s["rule_score"]),
                "reason": s["reason"],
                "invited": s["profile_id"] in invited,
            }
            for s in suggestions
            if s["profile_id"] in rows
        ],
        "cost_usd": _money(cost),
    }


@router.post("/{opportunity_id}/shortlist")
def run_shortlist(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    opp = _opportunity(session, opportunity_id)
    ratelimit.enforce(session, RATE_BUCKET, RATE_LIMIT, RATE_WINDOW_S)
    run = shortlist_rank.run_shortlist(session, opp.id)
    session.commit()
    return ok(
        _payload(
            session,
            opp,
            run_id=run.run_id,
            ranked_by=run.ranked_by,
            suggestions=run.suggestions,
            cost=run.cost_usd,
        )
    )


@router.get("/{opportunity_id}/shortlist")
def latest_shortlist(opportunity_id: str, session: Session = Depends(get_session)) -> dict:
    opp = _opportunity(session, opportunity_id)
    latest = session.scalar(
        select(MatchSuggestion)
        .where(MatchSuggestion.opportunity_id == opp.id)
        .order_by(MatchSuggestion.id.desc())
        .limit(1)
    )
    if latest is None:
        return ok(_payload(session, opp, run_id=None, ranked_by=None, suggestions=[], cost=Decimal("0")))
    rows = session.scalars(
        select(MatchSuggestion)
        .where(MatchSuggestion.opportunity_id == opp.id, MatchSuggestion.run_id == latest.run_id)
        .order_by(MatchSuggestion.rank)
    ).all()
    cost = Decimal("0")
    if latest.ranked_by == "ai":
        usage = session.scalar(
            select(AiUsage)
            .where(AiUsage.opportunity_id == opp.id, AiUsage.purpose == shortlist_rank.PURPOSE)
            .order_by(AiUsage.id.desc())
            .limit(1)
        )
        cost = Decimal(str(usage.cost_usd)) if usage is not None else Decimal("0")
    suggestions = [
        {"rank": r.rank, "profile_id": r.profile_id, "rule_score": r.rule_score, "reason": r.reason}
        for r in rows
    ]
    return ok(
        _payload(session, opp, run_id=latest.run_id, ranked_by=latest.ranked_by, suggestions=suggestions, cost=cost)
    )


def _email_context(session: Session, opp: Opportunity, user: AppUser, base_url: str) -> dict:
    return {"name": user.display_name, **listing_fields(session, opp, base_url)}


@router.post("/{opportunity_id}/invites")
def invite_to_apply(
    opportunity_id: str,
    body: InviteBody,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    opp = _opportunity(session, opportunity_id)
    ids = list(dict.fromkeys(body.profile_ids))
    if not ids or len(ids) > INVITE_MAX:
        raise api_error("validation_error", f"profile_ids: choose between 1 and {INVITE_MAX} trainers", 422)
    if effective_status(opp, utcnow()) != "open":
        raise api_error("opportunity_closed", "Only open listings can invite trainers to apply.", 409)
    people = {
        p.id: (p, u)
        for p, u in session.execute(
            select(TrainerProfile, AppUser)
            .join(AppUser, AppUser.id == TrainerProfile.user_id)
            .where(TrainerProfile.id.in_(ids))
        )
    }
    missing = [i for i in ids if i not in people]
    if missing:
        raise api_error("validation_error", f"profile_ids: unknown trainer {missing[0]}", 422)

    existing = matching.invited_profile_ids(session, opp.id)
    base_url = request_base_url(request)
    results: list[dict] = []
    skipped = 0
    for pid in ids:
        profile, user = people[pid]
        created = pid not in existing
        if created:
            session.add(OpportunityInvite(opportunity_id=opp.id, profile_id=pid, created_by=actor.by))
        if profile.consent_at is None:
            email_status = "skipped_no_consent"
            skipped += 1
        else:
            row = outbox.enqueue(
                session,
                to=user.email,
                template="opportunity.invite",
                context=_email_context(session, opp, user, base_url),
                dedupe_key=f"opp-invite:{opp.id}:{pid}",
            )
            email_status = row.status
        results.append({"profile_id": pid, "created": created, "email": email_status})
    record_action(
        session,
        None,
        "admin",
        "opportunity.invite",
        {
            "profile_ids": ids,
            "created": [r["profile_id"] for r in results if r["created"]],
            "skipped_no_consent": [r["profile_id"] for r in results if r["email"] == "skipped_no_consent"],
            "by": actor.by,
        },
        subject_type="opportunity",
        subject_id=opp.id,
    )
    session.commit()
    sender.schedule_drain(background_tasks)
    log.info("opportunity.invite", opportunity_id=opp.id, invited=len(ids), skipped_no_consent=skipped)
    return ok({"invites": results})
