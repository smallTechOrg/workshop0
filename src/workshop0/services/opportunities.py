"""Opportunity management (C9) + public board queries (C10).

* `effective_status(opportunity, now)` is the ONLY Python implementation of the
  effective status; `effective_status_predicate(status, now)` is its SQL twin, used by
  every list filter (spec/data-model.md §Effective status). No scheduler: expiry is
  computed on read.
* Public serializers (`public_card`, `public_detail`) are explicit allow-lists — the
  internal partner name and notes are structurally unreachable from them.
* Every admin write is audited in `facilitator_action` (actor `admin`, no workshop,
  `subject_type="opportunity"`) — exactly one row per write, none for a no-op.
"""

import json
import math
from datetime import date, datetime

import structlog
from pydantic import BaseModel, StrictInt, field_validator
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from src.workshop0.api._common import api_error, as_utc, iso_z, utcnow
from src.workshop0.db.models import (
    FacilitatorAction,
    Opportunity,
    OpportunityTopic,
    Partner,
    Topic,
)
from src.workshop0.services.audit import record_action
from src.workshop0.services.partners import partner_ref, resolve_partner
from src.workshop0.services.topics import ADMIN_ACTOR, ADMIN_BY

log = structlog.get_logger("workshop0")

TYPES = ("workshop", "engagement", "role", "cofacilitation")
LOCATION_MODES = ("remote", "onsite", "hybrid")
STORED_STATUSES = ("draft", "open", "closed")
EFFECTIVE_STATUSES = ("draft", "open", "expired", "closed")
SORTS = ("newest", "deadline")

TITLE_MIN, TITLE_MAX = 3, 160
SUMMARY_MIN, SUMMARY_MAX = 1, 280
DESCRIPTION_MAX = 20_000
TOPICS_MIN, TOPICS_MAX = 1, 8
CITY_MAX = 80
DURATION_MAX = 80
COMPENSATION_MAX = 120
AMOUNT_MAX = 100_000_000
CURRENCIES = ("INR", "USD")
COMPENSATION_UNITS = ("hour", "day", "course", "month")
PARTNER_MAX = 160
NOTES_MAX = 5_000
ACTIVITY_LIMIT = 20

# Ids are INTEGER (int4) columns: anything outside 1..ID_MAX can never match a row,
# and must never reach the driver (it would overflow → 500).
ID_MAX = 2**31 - 1

NOT_AVAILABLE_MESSAGE = "This opportunity isn't available."
NOT_FOUND_MESSAGE = "No opportunity matches this id."
PUBLISH_DEADLINE_MESSAGE = "deadline: set a future deadline to publish"

# Field order = the order changed_fields are reported in.
FIELDS = (
    "title",
    "type",
    "summary",
    "description_md",
    "topic_ids",
    "location_mode",
    "city",
    "starts_on",
    "ends_on",
    "duration_text",
    "compensation_min",
    "compensation_max",
    "compensation_currency",
    "compensation_unit",
    "compensation_text",
    "deadline",
    "partner_display_name",
    "partner_id",
    "internal_notes",
    "status",
)
# May never be null (sending null in a PATCH is a validation error, not a clear).
REQUIRED_FIELDS = ("title", "type", "summary", "topic_ids", "location_mode", "deadline", "status")


def validation_error(message: str):
    return api_error("validation_error", message, 422)


# --------------------------------------------------------------------------- status


def effective_status(opportunity: Opportunity, now: datetime) -> str:
    """draft → draft · closed → closed · open & deadline > now → open · else expired."""
    if opportunity.status != "open":
        return opportunity.status
    return "open" if as_utc(opportunity.deadline) > as_utc(now) else "expired"


def effective_status_predicate(status: str, now: datetime) -> ColumnElement[bool]:
    """The SQL twin of `effective_status` — `status='open' AND deadline > :now`, etc."""
    if status == "open":
        return and_(Opportunity.status == "open", Opportunity.deadline > now)
    if status == "expired":
        return and_(Opportunity.status == "open", Opportunity.deadline <= now)
    return Opportunity.status == status


def _effective_status_expr(now: datetime):
    return case(
        (
            Opportunity.status == "open",
            case((Opportunity.deadline > now, "open"), else_="expired"),
        ),
        else_=Opportunity.status,
    )


# --------------------------------------------------------------------------- request models


def _bounded(value: str | None, *, low: int, high: int, required: bool) -> str | None:
    """Trim; blank optional → None; enforce length bounds."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed and not required:
        return None
    if not (low <= len(trimmed) <= high):
        raise ValueError(
            f"must be {low}–{high} characters" if required else f"must be at most {high} characters"
        )
    return trimmed


def _one_of(value: str | None, allowed: tuple[str, ...]) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if trimmed not in allowed:
        raise ValueError(f"must be one of {', '.join(allowed)}")
    return trimmed


class OpportunityPatch(BaseModel):
    """Any subset of the POST fields. Omitted = unchanged; optional field null = cleared."""

    title: str | None = None
    type: str | None = None
    summary: str | None = None
    description_md: str | None = None
    topic_ids: list[int] | None = None
    location_mode: str | None = None
    city: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    duration_text: str | None = None
    compensation_min: StrictInt | None = None
    compensation_max: StrictInt | None = None
    compensation_currency: str | None = None
    compensation_unit: str | None = None
    compensation_text: str | None = None
    deadline: datetime | None = None
    partner_display_name: str | None = None
    partner_id: StrictInt | None = None
    partner_internal_name: str | None = None  # legacy: resolved to a partner, never stored as input
    internal_notes: str | None = None
    status: str | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        return _bounded(v, low=TITLE_MIN, high=TITLE_MAX, required=True)

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        return _one_of(v, TYPES)

    @field_validator("summary")
    @classmethod
    def _summary(cls, v):
        return _bounded(v, low=SUMMARY_MIN, high=SUMMARY_MAX, required=True)

    @field_validator("description_md")
    @classmethod
    def _description(cls, v):
        if v is None:
            return None
        if len(v) > DESCRIPTION_MAX:
            raise ValueError(f"must be at most {DESCRIPTION_MAX} characters")
        return v.strip()

    @field_validator("topic_ids")
    @classmethod
    def _topic_ids(cls, v):
        if v is None:
            return None
        if not (TOPICS_MIN <= len(v) <= TOPICS_MAX):
            raise ValueError(f"choose {TOPICS_MIN} to {TOPICS_MAX} topics")
        if len(set(v)) != len(v):
            raise ValueError("choose each topic only once")
        return v

    @field_validator("location_mode")
    @classmethod
    def _location_mode(cls, v):
        return _one_of(v, LOCATION_MODES)

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        return _bounded(v, low=1, high=CITY_MAX, required=False)

    @field_validator("duration_text")
    @classmethod
    def _duration(cls, v):
        return _bounded(v, low=1, high=DURATION_MAX, required=False)

    @field_validator("compensation_min", "compensation_max")
    @classmethod
    def _amount(cls, v):
        if v is not None and not (0 <= v <= AMOUNT_MAX):
            raise ValueError(f"must be between 0 and {AMOUNT_MAX}")
        return v

    @field_validator("compensation_currency")
    @classmethod
    def _currency(cls, v):
        return _one_of(v, CURRENCIES)

    @field_validator("compensation_unit")
    @classmethod
    def _unit(cls, v):
        return _one_of(v, COMPENSATION_UNITS)

    @field_validator("compensation_text")
    @classmethod
    def _compensation(cls, v):
        return _bounded(v, low=1, high=COMPENSATION_MAX, required=False)

    @field_validator("deadline")
    @classmethod
    def _deadline(cls, v):
        if v is None:
            return None
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("include a time zone, e.g. 2026-11-30T18:29:59Z")
        return as_utc(v)

    @field_validator("partner_display_name", "partner_internal_name")
    @classmethod
    def _partner(cls, v):
        return _bounded(v, low=1, high=PARTNER_MAX, required=False)

    @field_validator("internal_notes")
    @classmethod
    def _notes(cls, v):
        return _bounded(v, low=1, high=NOTES_MAX, required=False)

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        return _one_of(v, STORED_STATUSES)


# POST fields with a spec default: omitted OR null → the default (blank optional → null).
CREATE_DEFAULTS = {"description_md": "", "location_mode": "remote", "status": "draft"}


class OpportunityCreate(OpportunityPatch):
    """POST body: title, type, summary, topic_ids and deadline are required."""

    title: str
    type: str
    summary: str
    description_md: str | None = ""
    topic_ids: list[int]
    location_mode: str | None = "remote"
    deadline: datetime
    status: str | None = "draft"


def parse_path_id(raw: str, message: str) -> int:
    """Path ids: a non-integer or out-of-range id simply matches nothing → 404."""
    if not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        raise api_error("not_found", message, 404)
    value = int(raw)
    if not 1 <= value <= ID_MAX:
        raise api_error("not_found", message, 404)
    return value


# --------------------------------------------------------------------------- serializers


def public_url(base_url: str, opportunity_id: int) -> str:
    return f"{base_url}/opportunities/{opportunity_id}"


def _iso_or_none(value: datetime | None) -> str | None:
    return iso_z(value) if value is not None else None


def _date_or_none(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def topics_by_opportunity(session: Session, opportunity_ids: list[int]) -> dict[int, list[Topic]]:
    """Batch-load each listing's topics (display order = topic position)."""
    result: dict[int, list[Topic]] = {oid: [] for oid in opportunity_ids}
    if not opportunity_ids:
        return result
    rows = session.execute(
        select(OpportunityTopic.opportunity_id, Topic)
        .join(Topic, Topic.id == OpportunityTopic.topic_id)
        .where(OpportunityTopic.opportunity_id.in_(opportunity_ids))
        .order_by(Topic.position, Topic.id)
    ).all()
    for opportunity_id, topic in rows:
        result[opportunity_id].append(topic)
    return result


def public_card(opp: Opportunity, topics: list[Topic], base_url: str, now: datetime) -> dict:
    """PublicOpportunityCard — an explicit allow-list (never "model minus fields")."""
    return {
        "id": opp.id,
        "title": opp.title,
        "type": opp.type,
        "summary": opp.summary,
        "partner_display_name": opp.partner_display_name,
        "topics": [{"slug": t.slug, "name": t.name} for t in topics],
        "location_mode": opp.location_mode,
        "city": opp.city,
        "starts_on": _date_or_none(opp.starts_on),
        "ends_on": _date_or_none(opp.ends_on),
        "duration_text": opp.duration_text,
        "compensation_min": opp.compensation_min,
        "compensation_max": opp.compensation_max,
        "compensation_currency": opp.compensation_currency,
        "compensation_unit": opp.compensation_unit,
        "compensation_text": opp.compensation_text,
        "deadline": iso_z(opp.deadline),
        "published_at": _iso_or_none(opp.published_at),
        "status": effective_status(opp, now),
        "public_url": public_url(base_url, opp.id),
    }


def public_detail(opp: Opportunity, topics: list[Topic], base_url: str, now: datetime) -> dict:
    return {**public_card(opp, topics, base_url, now), "description_md": opp.description_md}


def admin_row(
    opp: Opportunity,
    topics: list[Topic],
    base_url: str,
    now: datetime,
    partner: Partner | None = None,
) -> dict:
    """AdminOpportunity list row (omits description_md and internal_notes).

    `partner` is the listing's partner row (callers batch-load it); `partner_internal_name`
    is derived from it, never read from the legacy mirror column.
    """
    return {
        "id": opp.id,
        "title": opp.title,
        "type": opp.type,
        "summary": opp.summary,
        "topics": [
            {"id": t.id, "slug": t.slug, "name": t.name, "active": t.active} for t in topics
        ],
        "location_mode": opp.location_mode,
        "city": opp.city,
        "starts_on": _date_or_none(opp.starts_on),
        "ends_on": _date_or_none(opp.ends_on),
        "duration_text": opp.duration_text,
        "compensation_min": opp.compensation_min,
        "compensation_max": opp.compensation_max,
        "compensation_currency": opp.compensation_currency,
        "compensation_unit": opp.compensation_unit,
        "compensation_text": opp.compensation_text,
        "deadline": iso_z(opp.deadline),
        "partner_display_name": opp.partner_display_name,
        "partner_id": opp.partner_id,
        "partner": partner_ref(partner) if partner is not None else None,
        "partner_internal_name": partner.internal_name if partner is not None else None,
        "status": effective_status(opp, now),
        "stored_status": opp.status,
        "public_url": public_url(base_url, opp.id),
        "published_at": _iso_or_none(opp.published_at),
        "closed_at": _iso_or_none(opp.closed_at),
        "created_at": iso_z(opp.created_at),
        "updated_at": iso_z(opp.updated_at),
    }


def admin_full(
    opp: Opportunity,
    topics: list[Topic],
    base_url: str,
    now: datetime,
    partner: Partner | None = None,
) -> dict:
    row = admin_row(opp, topics, base_url, now, partner)
    row["description_md"] = opp.description_md
    row["internal_notes"] = opp.internal_notes
    return row


def _full(session: Session, opp: Opportunity, base_url: str) -> dict:
    topics = topics_by_opportunity(session, [opp.id])[opp.id]
    partner = session.get(Partner, opp.partner_id) if opp.partner_id is not None else None
    return admin_full(opp, topics, base_url, utcnow(), partner)


def _partners_for(session: Session, rows: list[Opportunity]) -> dict[int, Partner]:
    ids = {o.partner_id for o in rows if o.partner_id is not None}
    if not ids:
        return {}
    return {p.id: p for p in session.scalars(select(Partner).where(Partner.id.in_(ids)))}


# --------------------------------------------------------------------------- public reads


def list_public(
    session: Session,
    *,
    base_url: str,
    type_: str | None,
    topic_slugs: list[str],
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    if type_ is not None and type_ not in TYPES:
        raise validation_error(f"type: must be one of {', '.join(TYPES)}")
    if sort not in SORTS:
        raise validation_error(f"sort: must be one of {', '.join(SORTS)}")
    now = utcnow()
    conditions = [effective_status_predicate("open", now)]
    if type_ is not None:
        conditions.append(Opportunity.type == type_)
    if topic_slugs:  # ANY semantics; unknown slugs simply match nothing
        conditions.append(
            Opportunity.id.in_(
                select(OpportunityTopic.opportunity_id)
                .join(Topic, Topic.id == OpportunityTopic.topic_id)
                .where(Topic.slug.in_(topic_slugs))
            )
        )
    order = (
        (Opportunity.deadline.asc(), Opportunity.id.asc())
        if sort == "deadline"
        else (Opportunity.published_at.desc(), Opportunity.id.desc())
    )
    total = int(session.scalar(select(func.count(Opportunity.id)).where(*conditions)) or 0)
    rows = list(
        session.scalars(
            select(Opportunity)
            .where(*conditions)
            .order_by(*order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    topics = topics_by_opportunity(session, [o.id for o in rows])
    return {
        "opportunities": [public_card(o, topics[o.id], base_url, now) for o in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def get_public(session: Session, opportunity_id: int, *, base_url: str) -> dict:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.status == "draft":
        raise api_error("not_found", NOT_AVAILABLE_MESSAGE, 404)
    topics = topics_by_opportunity(session, [opp.id])[opp.id]
    return public_detail(opp, topics, base_url, utcnow())


# --------------------------------------------------------------------------- admin reads


def status_counts(session: Session, now: datetime) -> dict[str, int]:
    expr = _effective_status_expr(now)
    counts = {status: 0 for status in EFFECTIVE_STATUSES}
    for status, count in session.execute(
        select(expr, func.count(Opportunity.id)).group_by(expr)
    ).all():
        counts[status] = int(count)
    return counts


def list_admin(
    session: Session,
    *,
    base_url: str,
    status: str | None,
    type_: str | None,
    q: str | None,
    page: int,
    page_size: int,
) -> dict:
    if status is not None and status not in EFFECTIVE_STATUSES:
        raise validation_error(f"status: must be one of {', '.join(EFFECTIVE_STATUSES)}")
    if type_ is not None and type_ not in TYPES:
        raise validation_error(f"type: must be one of {', '.join(TYPES)}")
    now = utcnow()
    conditions = []
    if status is not None:
        conditions.append(effective_status_predicate(status, now))
    if type_ is not None:
        conditions.append(Opportunity.type == type_)
    needle = (q or "").strip().lower()
    if needle:
        pattern = f"%{_escape_like(needle)}%"
        conditions.append(
            or_(
                func.lower(Opportunity.title).like(pattern, escape="\\"),
                func.lower(Opportunity.partner_display_name).like(pattern, escape="\\"),
                func.lower(Partner.internal_name).like(pattern, escape="\\"),
            )
        )
    join_on = Opportunity.partner_id == Partner.id
    total = int(
        session.scalar(
            select(func.count(Opportunity.id))
            .select_from(Opportunity)
            .outerjoin(Partner, join_on)
            .where(*conditions)
        )
        or 0
    )
    rows = list(
        session.scalars(
            select(Opportunity)
            .outerjoin(Partner, join_on)
            .where(*conditions)
            .order_by(Opportunity.updated_at.desc(), Opportunity.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    topics = topics_by_opportunity(session, [o.id for o in rows])
    partners = _partners_for(session, rows)
    return {
        "opportunities": [
            admin_row(o, topics[o.id], base_url, now, partners.get(o.partner_id)) for o in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
        "counts": status_counts(session, now),
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_or_404(session: Session, opportunity_id: int) -> Opportunity:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise api_error("not_found", NOT_FOUND_MESSAGE, 404)
    return opp


def activity(session: Session, opportunity_id: int) -> list[dict]:
    rows = session.scalars(
        select(FacilitatorAction)
        .where(
            FacilitatorAction.subject_type == "opportunity",
            FacilitatorAction.subject_id == opportunity_id,
        )
        .order_by(FacilitatorAction.created_at.desc(), FacilitatorAction.id.desc())
        .limit(ACTIVITY_LIMIT)
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "detail": json.loads(row.detail_json or "{}"),
            "created_at": iso_z(row.created_at),
        }
        for row in rows
    ]


def get_admin(session: Session, opportunity_id: int, *, base_url: str) -> dict:
    opp = _get_or_404(session, opportunity_id)
    return {"opportunity": _full(session, opp, base_url), "activity": activity(session, opp.id)}


# --------------------------------------------------------------------------- admin writes


def _current_values(opp: Opportunity, topic_ids: list[int]) -> dict:
    values = {field: getattr(opp, field) for field in FIELDS if field != "topic_ids"}
    values["topic_ids"] = topic_ids
    if values["deadline"] is not None:
        values["deadline"] = as_utc(values["deadline"])
    return values


def _validate_topics(
    session: Session, topic_ids: list[int], already_attached: set[int]
) -> None:
    """Every id must exist; inactive topics are allowed only if the listing already has them."""
    in_range = [tid for tid in topic_ids if 1 <= tid <= ID_MAX]  # others can't exist
    found = dict(
        session.execute(select(Topic.id, Topic.active).where(Topic.id.in_(in_range))).all()
    )
    for topic_id in topic_ids:
        if topic_id not in found:
            raise validation_error(f"topic_ids: topic {topic_id} does not exist")
        if not found[topic_id] and topic_id not in already_attached:
            raise validation_error(f"topic_ids: topic {topic_id} is inactive")


def _validate_compensation(merged: dict) -> None:
    low, high = merged["compensation_min"], merged["compensation_max"]
    currency, unit = merged["compensation_currency"], merged["compensation_unit"]
    if low is not None and high is not None and high < low:
        raise validation_error("compensation_max: must be at least compensation_min")
    if low is None and high is None:
        if currency is not None or unit is not None:
            raise validation_error(
                "compensation_min: enter an amount, or clear the currency and unit"
            )
        return
    if currency is None:
        raise validation_error("compensation_currency: required with an amount")
    if unit is None:
        raise validation_error("compensation_unit: required with an amount")


def _resolve_partner(
    session: Session,
    body: OpportunityPatch,
    merged: dict,
    *,
    current_partner_id: int | None,
    by: str,
) -> Partner | None:
    """Resolve + merge the listing's partner (id or legacy name) via `resolve_partner`."""
    given = body.model_fields_set
    partner = resolve_partner(
        session,
        partner_id=body.partner_id,
        partner_id_given="partner_id" in given,
        internal_name=body.partner_internal_name,
        internal_name_given="partner_internal_name" in given,
        display_name_hint=merged["partner_display_name"],
        current_partner_id=current_partner_id,
        by=by,
    )
    merged["partner_id"] = partner.id if partner is not None else None
    return partner


def _validate_merged(
    session: Session,
    merged: dict,
    provided: dict,
    *,
    previous: dict | None,
    now: datetime,
) -> None:
    """Cross-field rules over the post-write state (spec/api.md §POST validation)."""
    for field in REQUIRED_FIELDS:
        if field in provided and provided[field] is None:
            raise validation_error(f"{field}: is required")
    if "topic_ids" in provided:
        attached = set(previous["topic_ids"]) if previous else set()
        _validate_topics(session, merged["topic_ids"], attached)
    if merged["location_mode"] == "remote":
        merged["city"] = None
    elif not merged["city"]:
        raise validation_error("city: required for onsite or hybrid")
    _validate_compensation(merged)
    if merged["starts_on"] and merged["ends_on"] and merged["ends_on"] < merged["starts_on"]:
        raise validation_error("ends_on: must be on or after starts_on")
    # Publish rule (data-model.md): a write whose result is stored `open` and which
    # moves the listing to `open` or changes its deadline must leave deadline > now.
    if merged["status"] == "open":
        becomes_open = previous is None or previous["status"] != "open"
        deadline_changed = previous is not None and merged["deadline"] != previous["deadline"]
        if (becomes_open or deadline_changed) and not merged["deadline"] > now:
            raise validation_error(PUBLISH_DEADLINE_MESSAGE)


def _apply(opp: Opportunity, merged: dict, partner: Partner | None) -> None:
    for field in FIELDS:
        if field != "topic_ids":
            setattr(opp, field, merged[field])
    # Legacy mirror (data-model.md §Phase 11b): new code never reads it.
    opp.partner_internal_name = partner.internal_name if partner is not None else None


def _set_topics(session: Session, opportunity_id: int, old: list[int], new: list[int]) -> None:
    for topic_id in set(old) - set(new):
        row = session.get(OpportunityTopic, (opportunity_id, topic_id))
        if row is not None:
            session.delete(row)
    for topic_id in new:
        if topic_id not in old:
            session.add(OpportunityTopic(opportunity_id=opportunity_id, topic_id=topic_id))


def _status_action(from_status: str, to_status: str) -> str:
    return {"open": "opportunity.publish", "draft": "opportunity.unpublish", "closed": "opportunity.close"}[
        to_status
    ]


def create_opportunity(
    session: Session, body: OpportunityCreate, *, base_url: str, by: str = ADMIN_BY
) -> dict:
    now = utcnow()
    provided = body.model_dump()
    for field, default in CREATE_DEFAULTS.items():
        if provided[field] is None:
            provided[field] = default
    merged = dict(provided)
    merged.setdefault("partner_id", None)
    _validate_merged(session, merged, provided, previous=None, now=now)
    partner = _resolve_partner(session, body, merged, current_partner_id=None, by=by)

    opp = Opportunity(created_at=now, updated_at=now)
    _apply(opp, merged, partner)
    if opp.status == "open":
        opp.published_at = now
    if opp.status == "closed":
        opp.closed_at = now
    session.add(opp)
    session.flush()
    _set_topics(session, opp.id, [], merged["topic_ids"])
    changed = [f for f in FIELDS if f != "status" and merged[f] not in (None, "", [])]
    record_action(
        session,
        None,
        ADMIN_ACTOR,
        "opportunity.create",
        {"title": opp.title, "changed_fields": changed, "to_status": opp.status, "by": by},
        subject_type="opportunity",
        subject_id=opp.id,
    )
    session.commit()
    log.info("opportunity.created", opportunity_id=opp.id, type=opp.type, status=opp.status)
    return _full(session, opp, base_url)


def update_opportunity(
    session: Session,
    opportunity_id: int,
    body: OpportunityPatch,
    *,
    base_url: str,
    by: str = ADMIN_BY,
) -> dict:
    opp = _get_or_404(session, opportunity_id)
    now = utcnow()
    old_topic_ids = [t.id for t in topics_by_opportunity(session, [opp.id])[opp.id]]
    previous = _current_values(opp, old_topic_ids)
    provided = body.model_dump(include=body.model_fields_set)
    if "description_md" in provided and provided["description_md"] is None:
        provided["description_md"] = ""
    provided.pop("partner_internal_name", None)  # legacy input, resolved below
    merged = {**previous, **provided}
    _validate_merged(session, merged, provided, previous=previous, now=now)
    partner = _resolve_partner(
        session, body, merged, current_partner_id=opp.partner_id, by=by
    )

    changed = [
        f
        for f in FIELDS
        if f != "status"
        and (
            set(merged[f]) != set(previous[f]) if f == "topic_ids" else merged[f] != previous[f]
        )
    ]
    from_status, to_status = previous["status"], merged["status"]
    status_changed = from_status != to_status
    if not changed and not status_changed:
        session.commit()  # a legacy name that resolved to the same partner writes nothing
        return _full(session, opp, base_url)  # no-op: no write, no audit row

    _apply(opp, merged, partner)
    if "topic_ids" in changed:
        _set_topics(session, opp.id, old_topic_ids, merged["topic_ids"])
    if status_changed:
        if to_status == "open" and opp.published_at is None:
            opp.published_at = now
        if to_status == "closed":
            opp.closed_at = now
        elif from_status == "closed":
            opp.closed_at = None
    opp.updated_at = now

    detail: dict = {"title": opp.title, "changed_fields": changed, "by": by}
    if status_changed:
        detail.update({"from_status": from_status, "to_status": to_status})
        action = _status_action(from_status, to_status)
    else:
        action = "opportunity.update"
    record_action(
        session, None, ADMIN_ACTOR, action, detail,
        subject_type="opportunity", subject_id=opp.id,
    )
    session.commit()
    if status_changed:
        log.info(
            "opportunity.status_changed",
            opportunity_id=opp.id,
            from_status=from_status,
            to_status=to_status,
            changed_fields=changed,
        )
    else:
        log.info("opportunity.updated", opportunity_id=opp.id, changed_fields=changed)
    return _full(session, opp, base_url)
