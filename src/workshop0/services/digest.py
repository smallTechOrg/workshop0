"""Phase 13: weekly digest of new listings matching a trainer's saved searches."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.db.models import AppUser, EmailOutbox, SavedSearch, TrainerProfile
from src.workshop0.email import outbox
from src.workshop0.services import alerts, email_prefs, unsubscribe
from src.workshop0.services.listing_text import listing_fields

IST = timezone(timedelta(hours=5, minutes=30))
MAX_ITEMS = 10


def iso_week_label(now: datetime) -> str:
    """ISO calendar week in IST, e.g. `2026-W46`."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    year, week, _ = now.astimezone(IST).isocalendar()
    return f"{year}-W{week:02d}"


def run_weekly(session: Session, *, now: datetime, base_url: str) -> dict:
    """Enqueue one `network.digest` per eligible user; never commits."""
    from src.workshop0.services.opportunities import effective_status_predicate, topics_by_opportunity
    from src.workshop0.db.models import Opportunity

    week = iso_week_label(now)
    listings = list(
        session.scalars(
            select(Opportunity)
            .where(
                effective_status_predicate("open", now),
                Opportunity.published_at.is_not(None),
                Opportunity.published_at >= now - timedelta(days=7),
            )
            .order_by(Opportunity.published_at.desc(), Opportunity.id.desc())
        )
    )
    result = {"enqueued": 0, "week": week, "listings": len(listings)}
    if not listings:
        return result

    topics = topics_by_opportunity(session, [o.id for o in listings])
    slugs = {o.id: frozenset(t.slug for t in topics.get(o.id, [])) for o in listings}

    rows = session.execute(
        select(SavedSearch, AppUser)
        .join(AppUser, AppUser.id == SavedSearch.user_id)
        .join(TrainerProfile, TrainerProfile.user_id == SavedSearch.user_id)
        .where(TrainerProfile.consent_at.is_not(None))
        .order_by(SavedSearch.id)
    ).all()
    users: dict[int, AppUser] = {}
    hits: dict[int, set[int]] = defaultdict(set)
    for search, user in rows:
        try:
            criteria = json.loads(search.criteria_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(criteria, dict):
            continue
        for opp in listings:
            if alerts.matches(criteria, opp, slugs[opp.id]):
                hits[user.id].add(opp.id)
                users[user.id] = user
    if not users:
        return result

    prefs = email_prefs.prefs_for(session, list(users))
    fields = {o.id: listing_fields(session, o, base_url) for o in listings}
    for user_id, user in users.items():
        if not prefs[user_id].digest:
            continue
        key = f"digest:{user_id}:{week}"
        if session.scalar(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == key)) is not None:
            continue
        mine = [o.id for o in listings if o.id in hits[user_id]]
        items = [
            {k: fields[i][k] for k in ("title", "partner", "compensation", "cities", "url")}
            for i in mine[:MAX_ITEMS]
        ]
        outbox.enqueue(
            session,
            to=user.email,
            template="network.digest",
            context={
                "name": user.display_name,
                "count": len(mine),
                "listings": items,
                "more": max(len(mine) - MAX_ITEMS, 0),
                "board_url": f"{base_url}/opportunities",
                "unsubscribe_url": unsubscribe.url(base_url, user_id, "digest"),
                "manage_url": f"{base_url}/app/network/searches/",
            },
            dedupe_key=key,
        )
        result["enqueued"] += 1
    return result
