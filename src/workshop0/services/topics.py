"""Topic taxonomy (C8) — slug derivation, admin create/update, public + admin serializers.

Topics are migration-seeded reference data (40 rows, alembic 0005) plus admin edits.
Slugs are derived once at creation and are immutable (they live in public filter URLs).
Names are unique case-insensitively (enforced here; the DB enforces exact uniqueness).
"""

import re
from datetime import datetime

import structlog
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, utcnow
from src.workshop0.db.models import Opportunity, OpportunityTopic, Topic
from src.workshop0.services.audit import record_action

log = structlog.get_logger("workshop0")

NAME_MIN, NAME_MAX = 2, 80
CATEGORY_MIN, CATEGORY_MAX = 2, 48
SLUG_MAX = 48
TOPIC_EXISTS_MESSAGE = "A topic with this name already exists."
ADMIN_ACTOR = "admin"
ADMIN_BY = "admin-key"  # becomes the admin user's email from Phase 11

_NON_SLUG_RUN = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lower-case; runs of non-[a-z0-9] → '-'; trimmed of '-'; ≤48 chars.

    `"C# / .NET 2"` → `"c-net-2"`. May return "" (caller rejects it)."""
    slug = _NON_SLUG_RUN.sub("-", name.lower()).strip("-")
    return slug[:SLUG_MAX].rstrip("-")


def _check_name(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not (NAME_MIN <= len(trimmed) <= NAME_MAX):
        raise ValueError(f"must be {NAME_MIN}–{NAME_MAX} characters")
    return trimmed


def _check_category(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not (CATEGORY_MIN <= len(trimmed) <= CATEGORY_MAX):
        raise ValueError(f"must be {CATEGORY_MIN}–{CATEGORY_MAX} characters")
    return trimmed


class _TopicValidators(BaseModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def _valid_name(cls, value: str | None) -> str | None:
        return _check_name(value)

    @field_validator("category", check_fields=False)
    @classmethod
    def _valid_category(cls, value: str | None) -> str | None:
        return _check_category(value)


class TopicCreate(_TopicValidators):
    name: str
    category: str


class TopicPatch(_TopicValidators):
    name: str | None = None
    category: str | None = None
    active: bool | None = None


# --------------------------------------------------------------------------- serializers


def admin_topic(topic: Topic, opportunity_count: int) -> dict:
    return {
        "id": topic.id,
        "slug": topic.slug,
        "name": topic.name,
        "category": topic.category,
        "position": topic.position,
        "active": topic.active,
        "opportunity_count": opportunity_count,
    }


def public_topic(topic: Topic, open_count: int) -> dict:
    """Explicit allow-list — the public topic shape."""
    return {
        "slug": topic.slug,
        "name": topic.name,
        "category": topic.category,
        "open_count": open_count,
    }


def _opportunity_counts(session: Session, *, open_only_at: datetime | None) -> dict[int, int]:
    query = select(OpportunityTopic.topic_id, func.count(OpportunityTopic.opportunity_id))
    if open_only_at is not None:
        query = query.join(Opportunity, Opportunity.id == OpportunityTopic.opportunity_id).where(
            Opportunity.status == "open", Opportunity.deadline > open_only_at
        )
    return dict(session.execute(query.group_by(OpportunityTopic.topic_id)).all())


def list_admin_topics(session: Session) -> list[dict]:
    counts = _opportunity_counts(session, open_only_at=None)
    topics = session.scalars(select(Topic).order_by(Topic.position, Topic.id))
    return [admin_topic(t, counts.get(t.id, 0)) for t in topics]


def list_public_topics(session: Session, now: datetime) -> list[dict]:
    counts = _opportunity_counts(session, open_only_at=now)
    topics = session.scalars(
        select(Topic).where(Topic.active.is_(True)).order_by(Topic.position, Topic.id)
    )
    return [public_topic(t, counts.get(t.id, 0)) for t in topics]


def _admin_topic_with_count(session: Session, topic: Topic) -> dict:
    count = session.scalar(
        select(func.count(OpportunityTopic.opportunity_id)).where(
            OpportunityTopic.topic_id == topic.id
        )
    )
    return admin_topic(topic, int(count or 0))


# --------------------------------------------------------------------------- writes


def _name_taken(session: Session, name: str, *, exclude_id: int | None = None) -> bool:
    query = select(Topic.id).where(func.lower(Topic.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Topic.id != exclude_id)
    return session.scalar(query.limit(1)) is not None


def _topic_exists_error():
    return api_error("topic_exists", TOPIC_EXISTS_MESSAGE, 409)


def create_topic(session: Session, body: TopicCreate, *, by: str = ADMIN_BY) -> dict:
    slug = slugify(body.name)
    if not slug:
        raise api_error(
            "validation_error", "name: must contain at least one letter or digit", 422
        )
    slug_taken = session.scalar(select(Topic.id).where(Topic.slug == slug).limit(1)) is not None
    if slug_taken or _name_taken(session, body.name):
        raise _topic_exists_error()

    max_position = session.scalar(select(func.max(Topic.position)))
    now = utcnow()
    topic = Topic(
        slug=slug,
        name=body.name,
        category=body.category,
        position=(max_position + 1) if max_position is not None else 0,
        active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(topic)
    try:
        session.flush()
    except IntegrityError:  # a concurrent create won the race on slug/name
        session.rollback()
        raise _topic_exists_error() from None
    record_action(
        session,
        None,
        ADMIN_ACTOR,
        "topic.create",
        {"name": topic.name, "slug": topic.slug, "category": topic.category, "by": by},
        subject_type="topic",
        subject_id=topic.id,
    )
    session.commit()
    log.info("topic.created", topic_id=topic.id, slug=topic.slug)
    return _admin_topic_with_count(session, topic)


def update_topic(
    session: Session, topic_id: int, body: TopicPatch, *, by: str = ADMIN_BY
) -> dict:
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise api_error("not_found", "No topic matches this id.", 404)

    provided = body.model_dump(include=body.model_fields_set)
    for field, value in provided.items():
        if value is None:
            raise api_error("validation_error", f"{field}: cannot be empty", 422)

    changed: list[str] = []
    if "name" in provided and provided["name"] != topic.name:
        if _name_taken(session, provided["name"], exclude_id=topic.id):
            raise _topic_exists_error()
        topic.name = provided["name"]
        changed.append("name")
    if "category" in provided and provided["category"] != topic.category:
        topic.category = provided["category"]
        changed.append("category")
    if "active" in provided and provided["active"] != topic.active:
        topic.active = provided["active"]
        changed.append("active")

    if changed:
        topic.updated_at = utcnow()
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise _topic_exists_error() from None
        record_action(
            session,
            None,
            ADMIN_ACTOR,
            "topic.update",
            {"name": topic.name, "slug": topic.slug, "changed_fields": changed, "by": by},
            subject_type="topic",
            subject_id=topic.id,
        )
        session.commit()
        log.info("topic.updated", topic_id=topic.id, slug=topic.slug, changed_fields=changed)
    return _admin_topic_with_count(session, topic)
