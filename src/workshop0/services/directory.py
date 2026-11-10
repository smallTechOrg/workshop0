"""Phase 13: public trainer directory (C18).

A profile is *listed* iff visibility = 'public' AND public_slug is set AND completeness >= 60.
Every public payload is built by `_card` / `get_public`, an explicit allow-list: no ORM row or
`dict(model)` ever reaches a response.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.workshop0.db.models import AppUser, CvDocument, Topic, TrainerProfile, TrainerTopic
from src.workshop0.services import profiles, slugs

MIN_COMPLETENESS = 60
PAGE_SIZE = 24
SLUG_RE = re.compile(r"^[a-z0-9-]{1,80}$")
FALLBACK_BASE = "trainer"
_MAX_ATTEMPTS = 20


def public_path(slug: str) -> str:
    return "/trainers/" + slug


def ensure_slug(session: Session, profile: TrainerProfile, user: AppUser) -> str:
    """Return the profile's slug, generating (and flushing) it the first time. Frozen after."""
    if profile.public_slug:
        return profile.public_slug
    base = slugs.slug_base(user.display_name or "", None, fallback=FALLBACK_BASE)
    taken: set[str] = set()
    for _ in range(_MAX_ATTEMPTS):
        candidate = slugs.make_unique_slug(
            base,
            lambda s: s in taken
            or session.scalar(select(TrainerProfile.id).where(TrainerProfile.public_slug == s)) is not None,
        )
        try:
            with session.begin_nested():
                profile.public_slug = candidate
                session.flush()
            return candidate
        except IntegrityError:
            profile.public_slug = None
            taken.add(candidate)
    raise RuntimeError("could not allocate a trainer slug")  # pragma: no cover


# --------------------------------------------------------------------------- loading


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _batch(session: Session, rows: list[tuple[TrainerProfile, AppUser]]):
    ids = [p.id for p, _ in rows]
    user_ids = [p.user_id for p, _ in rows]
    topic_rows: dict[int, list[dict]] = {i: [] for i in ids}
    if ids:
        for pid, slug, name, level in session.execute(
            select(TrainerTopic.profile_id, Topic.slug, Topic.name, TrainerTopic.level)
            .join(Topic, Topic.id == TrainerTopic.topic_id)
            .where(TrainerTopic.profile_id.in_(ids))
            .order_by(Topic.position, Topic.slug)
        ):
            topic_rows[pid].append({"slug": slug, "name": name, "level": level})
    cv_users: set[int] = set()
    if user_ids:
        cv_users = set(session.scalars(select(CvDocument.user_id).where(CvDocument.user_id.in_(user_ids))))
    return topic_rows, cv_users


def _is_listed(profile: TrainerProfile, topics: list[dict], has_cv: bool) -> bool:
    if profile.visibility != "public" or not profile.public_slug:
        return False
    return profiles.completeness(profile, topic_count=len(topics), has_cv=has_cv).pct >= MIN_COMPLETENESS


def _links(profile: TrainerProfile) -> dict:
    return {
        "linkedin": profile.linkedin_url or None,
        "github": profile.github_url or None,
        "website": profile.website_url or None,
    }


def _card(profile: TrainerProfile, user: AppUser, topics: list[dict], base_url: str) -> dict:
    return {
        "slug": profile.public_slug,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url or None,
        "headline": profile.headline,
        "city": profile.city or None,
        "remote_ok": bool(profile.remote_ok),
        "topics": [{"slug": t["slug"], "name": t["name"], "level": t["level"]} for t in topics],
        "verified": bool(profile.verified),
        "links": _links(profile),
        "public_url": base_url.rstrip("/") + public_path(profile.public_slug),
    }


def _past_work(profile: TrainerProfile) -> list[dict]:
    out = []
    for item in _loads(profile.past_work_json, []):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": item.get("title"),
                "kind": item.get("kind"),
                "org": item.get("org"),
                "year": item.get("year"),
            }
        )
    return out


def _candidates(session: Session, topic: str | None = None) -> list[tuple[TrainerProfile, AppUser]]:
    stmt = (
        select(TrainerProfile, AppUser)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(TrainerProfile.visibility == "public", TrainerProfile.public_slug.is_not(None))
    )
    if topic:
        stmt = stmt.where(
            TrainerProfile.id.in_(
                select(TrainerTopic.profile_id).join(Topic, Topic.id == TrainerTopic.topic_id).where(Topic.slug == topic)
            )
        )
    return [(p, u) for p, u in session.execute(stmt).all()]


def _listed(session: Session, topic: str | None = None):
    rows = _candidates(session, topic)
    topic_rows, cv_users = _batch(session, rows)
    listed = [
        (p, u, topic_rows[p.id])
        for p, u in rows
        if _is_listed(p, topic_rows[p.id], p.user_id in cv_users)
    ]
    listed.sort(key=lambda r: ((r[1].display_name or "").casefold(), r[0].public_slug))
    return listed


# --------------------------------------------------------------------------- public API


def list_public(session: Session, *, topic: str | None, page: int, base_url: str) -> dict:
    page = max(1, int(page or 1))
    topic = (topic or "").strip().lower() or None
    listed = _listed(session, topic)
    start = (page - 1) * PAGE_SIZE
    return {
        "items": [_card(p, u, t, base_url) for p, u, t in listed[start : start + PAGE_SIZE]],
        "page": page,
        "page_size": PAGE_SIZE,
        "total": len(listed),
    }


def get_public(session: Session, slug: str, *, base_url: str) -> dict | None:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        return None
    row = session.execute(
        select(TrainerProfile, AppUser)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(TrainerProfile.public_slug == slug)
    ).first()
    if row is None:
        return None
    profile, user = row
    topic_rows, cv_users = _batch(session, [(profile, user)])
    topics = topic_rows[profile.id]
    if not _is_listed(profile, topics, profile.user_id in cv_users):
        return None
    detail = _card(profile, user, topics, base_url)
    detail["bio_md"] = profile.bio_md or ""
    detail["past_work"] = _past_work(profile)
    return detail


def sitemap_entries(session: Session, base_url: str) -> list[tuple[str, datetime]]:
    """(slug, profile.updated_at) for each listed trainer, in directory order."""
    return [(p.public_slug, p.updated_at) for p, _u, _t in _listed(session)]
