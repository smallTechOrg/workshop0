"""Trainer-profile domain: ProfileInput validation, own-profile serialization, completeness,
CV ingest and account deletion (spec/api.md §Phase 11, data-model.md §trainer_profile).

The HTTP layer (`api/network_me.py`) stays thin; every rule lives here.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, object_session

from src.workshop0.api._common import api_error, iso_z, utcnow
from src.workshop0.db.models import (
    AppUser,
    AuthSession,
    CvDocument,
    NetworkInvite,
    Topic,
    TrainerProfile,
    TrainerTopic,
)
from src.workshop0.services.audit import record_action
from src.workshop0.services.workshops import mask_email

if TYPE_CHECKING:
    from src.workshop0.storage.blobstore import BlobStore

log = structlog.get_logger("workshop0")

CONSENT_VERSION = "2026-11"
MAX_CV_BYTES = 5 * 1024 * 1024
TEXT_MIN, TEXT_MAX = 200, 30000
TEXT_EXTRACT_MAX = 60000

LEVELS = ("intermediate", "advanced", "expert")
PAST_WORK_KINDS = ("workshop", "talk", "course", "other")
CURRENCIES = ("INR", "USD")
RATE_UNITS = ("hour", "day", "course", "month")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_PARTS = ("morning", "afternoon", "evening")
MAX_TOPICS = 15
MAX_PAST_WORK = 30
MAX_BLACKOUTS = 20

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# ProfileInput keys (api.md §Phase 11) — also the vocabulary of `autofilled_fields`.
PROFILE_FIELDS = (
    "headline",
    "bio_md",
    "city",
    "remote_ok",
    "linkedin_url",
    "github_url",
    "website_url",
    "topics",
    "past_work",
    "rate_min",
    "rate_max",
    "rate_currency",
    "rate_unit",
    "pro_bono",
    "availability",
    "available_from",
    "blackouts",
)


def validation_error(message: str):
    return api_error("validation_error", message, 422)


def not_found(message: str):
    return api_error("not_found", message, 404)


# --------------------------------------------------------------------------- completeness


@dataclass(frozen=True)
class Completeness:
    pct: int
    missing: list[str] = field(default_factory=list)


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _has_weekly_availability(availability: Any) -> bool:
    return isinstance(availability, dict) and any(bool(v) for v in availability.values())


def completeness(
    profile: TrainerProfile,
    *,
    topic_count: int | None = None,
    has_cv: bool | None = None,
) -> Completeness:
    """Ten weighted checks, 10 % each (headline, bio, topics, location, link, past work,
    rate, weekly availability, available_from, CV on file).

    `topic_count` / `has_cv` may be passed by callers that batch-load them (the admin pool);
    otherwise they are read through the profile's own session."""
    if topic_count is None or has_cv is None:
        session = object_session(profile)
        if session is None:
            raise ValueError("completeness() needs an attached profile or explicit topic_count/has_cv")
        if topic_count is None:
            topic_count = session.scalar(
                select(func.count()).select_from(TrainerTopic).where(TrainerTopic.profile_id == profile.id)
            ) or 0
        if has_cv is None:
            has_cv = (
                session.scalar(select(CvDocument.id).where(CvDocument.user_id == profile.user_id))
                is not None
            )

    checks: list[tuple[str, bool]] = [
        ("headline", bool((profile.headline or "").strip())),
        ("bio", len((profile.bio_md or "").strip()) >= 80),
        ("topics", topic_count >= 3),
        ("location", bool((profile.city or "").strip()) or bool(profile.remote_ok)),
        ("link", any([profile.linkedin_url, profile.github_url, profile.website_url])),
        ("past_work", len(_loads(profile.past_work_json, [])) >= 1),
        (
            "rate",
            bool(profile.pro_bono)
            or (
                profile.rate_min is not None
                and profile.rate_max is not None
                and bool(profile.rate_currency)
                and bool(profile.rate_unit)
            ),
        ),
        ("availability", _has_weekly_availability(_loads(profile.availability_json, {}))),
        ("available_from", profile.available_from is not None),
        ("cv", bool(has_cv)),
    ]
    missing = [name for name, passed in checks if not passed]
    return Completeness(pct=10 * (len(checks) - len(missing)), missing=missing)


# --------------------------------------------------------------------------- ProfileInput


def _trim(value: Any, *, high: int, low: int = 0, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError("is required")
        return None
    if not isinstance(value, str):
        raise ValueError("must be text")
    trimmed = value.strip()
    if not trimmed and not required:
        return None
    if not (low <= len(trimmed) <= high):
        raise ValueError(f"must be {low}–{high} characters" if required else f"must be at most {high} characters")
    return trimmed


def _https_url(value: Any, *, host: str | None) -> str | None:
    url = _trim(value, high=300)
    if url is None:
        return None
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname or " " in url:
        raise ValueError("must be an https:// link")
    if host and not (hostname == host or hostname.endswith("." + host)):
        raise ValueError(f"must be a {host} link")
    return url


class TopicIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    level: str = "intermediate"

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("topic slug is required")
        return v

    @field_validator("level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in LEVELS:
            raise ValueError(f"level must be one of {', '.join(LEVELS)}")
        return v


class PastWorkIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    kind: str = "other"
    org: str | None = None
    year: int | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _trim(v, low=1, high=200, required=True)  # type: ignore[return-value]

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        v = (v or "other").strip().lower()
        if v not in PAST_WORK_KINDS:
            raise ValueError(f"kind must be one of {', '.join(PAST_WORK_KINDS)}")
        return v

    @field_validator("org")
    @classmethod
    def _org(cls, v: str | None) -> str | None:
        return _trim(v, high=200)

    @field_validator("year")
    @classmethod
    def _year(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not (1980 <= v <= datetime.now(timezone.utc).year):
            raise ValueError(f"year must be between 1980 and {datetime.now(timezone.utc).year}")
        return v


class BlackoutIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: date
    end: date


class ProfilePatch(BaseModel):
    """Partial ProfileInput: omitted = unchanged. `headline` and `topics` may never be null."""

    model_config = ConfigDict(extra="ignore")

    headline: str | None = None
    bio_md: str | None = None
    city: str | None = None
    remote_ok: bool | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    topics: list[TopicIn] | None = None
    past_work: list[PastWorkIn] | None = None
    rate_min: int | None = None
    rate_max: int | None = None
    rate_currency: str | None = None
    rate_unit: str | None = None
    pro_bono: bool | None = None
    availability: dict[str, list[str]] | None = None
    available_from: date | None = None
    blackouts: list[BlackoutIn] | None = None
    visibility: str | None = None  # Phase 13; `public_slug` / `directory` in a body are ignored

    @field_validator("visibility")
    @classmethod
    def _visibility(cls, v):
        if v not in ("private", "public"):
            raise ValueError("must be private or public")
        return v

    @field_validator("headline")
    @classmethod
    def _headline(cls, v):
        return _trim(v, low=3, high=160, required=True)

    @field_validator("bio_md")
    @classmethod
    def _bio(cls, v):
        return _trim(v, high=4000)

    @field_validator("city")
    @classmethod
    def _city(cls, v):
        return _trim(v, high=80)

    @field_validator("linkedin_url")
    @classmethod
    def _linkedin(cls, v):
        return _https_url(v, host="linkedin.com")

    @field_validator("github_url")
    @classmethod
    def _github(cls, v):
        return _https_url(v, host="github.com")

    @field_validator("website_url")
    @classmethod
    def _website(cls, v):
        return _https_url(v, host=None)

    @field_validator("topics")
    @classmethod
    def _topics(cls, v):
        if v is None:
            return v
        if not v:
            raise ValueError("pick at least one topic")
        if len(v) > MAX_TOPICS:
            raise ValueError(f"at most {MAX_TOPICS} topics")
        slugs = [t.slug for t in v]
        if len(set(slugs)) != len(slugs):
            raise ValueError("each topic may appear only once")
        return v

    @field_validator("past_work")
    @classmethod
    def _past_work(cls, v):
        if v is not None and len(v) > MAX_PAST_WORK:
            raise ValueError(f"at most {MAX_PAST_WORK} items")
        return v

    @field_validator("rate_min", "rate_max")
    @classmethod
    def _rate(cls, v):
        if v is not None and not (0 <= v <= 100_000_000):
            raise ValueError("must be a whole number of at least 0")
        return v

    @field_validator("rate_currency")
    @classmethod
    def _currency(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip().upper()
        if v not in CURRENCIES:
            raise ValueError(f"must be one of {', '.join(CURRENCIES)}")
        return v

    @field_validator("rate_unit")
    @classmethod
    def _unit(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in RATE_UNITS:
            raise ValueError(f"must be one of {', '.join(RATE_UNITS)}")
        return v

    @field_validator("availability")
    @classmethod
    def _availability(cls, v):
        if v is None:
            return v
        cleaned: dict[str, list[str]] = {}
        for day, parts in v.items():
            key = day.strip().lower()
            if key not in WEEKDAYS:
                raise ValueError(f"days must be among {', '.join(WEEKDAYS)}")
            normalized = []
            for part in parts:
                p = part.strip().lower()
                if p not in DAY_PARTS:
                    raise ValueError(f"times of day must be among {', '.join(DAY_PARTS)}")
                if p not in normalized:
                    normalized.append(p)
            if normalized:
                cleaned[key] = [p for p in DAY_PARTS if p in normalized]
        return {d: cleaned[d] for d in WEEKDAYS if d in cleaned}

    @field_validator("blackouts")
    @classmethod
    def _blackouts(cls, v):
        if v is None:
            return v
        if len(v) > MAX_BLACKOUTS:
            raise ValueError(f"at most {MAX_BLACKOUTS} date ranges")
        for item in v:
            if item.end < item.start:
                raise ValueError("each date range must end on or after its start")
        return v


class ProfileCreate(ProfilePatch):
    """Full ProfileInput + consent. Only `headline` and ≥1 topic are required."""

    headline: str  # type: ignore[assignment]
    topics: list[TopicIn]  # type: ignore[assignment]
    consent: bool | None = None


# Fields that may not be cleared with null on PATCH; booleans fall back to their defaults.
_NOT_NULL = ("headline", "topics")
_BOOL_DEFAULTS = {"remote_ok": True, "pro_bono": False}


def _resolve_topics(
    session: Session, topics: list[TopicIn], *, keep_ids: set[int] | None = None
) -> list[tuple[Topic, str]]:
    slugs = [t.slug for t in topics]
    rows = {t.slug: t for t in session.scalars(select(Topic).where(Topic.slug.in_(slugs)))}
    resolved: list[tuple[Topic, str]] = []
    for item in topics:
        topic = rows.get(item.slug)
        if topic is None or (not topic.active and topic.id not in (keep_ids or set())):
            raise validation_error(f"topics: unknown topic '{item.slug}'")
        resolved.append((topic, item.level))
    return resolved


def _current_topic_ids(session: Session, profile_id: int) -> set[int]:
    return set(session.scalars(select(TrainerTopic.topic_id).where(TrainerTopic.profile_id == profile_id)))


def _check_rates(rate_min: int | None, rate_max: int | None) -> None:
    if rate_min is not None and rate_max is not None and rate_min > rate_max:
        raise validation_error("rate_min: must not be more than rate_max")


def _column_value(name: str, value: Any) -> tuple[str, Any]:
    """ProfileInput key → (model attribute, stored value)."""
    if name == "past_work":
        return "past_work_json", json.dumps([p.model_dump() for p in (value or [])], ensure_ascii=False)
    if name == "availability":
        return "availability_json", json.dumps(value or {}, ensure_ascii=False)
    if name == "blackouts":
        items = [{"start": b.start.isoformat(), "end": b.end.isoformat()} for b in (value or [])]
        return "blackout_json", json.dumps(items)
    if name == "bio_md":
        return "bio_md", value or ""
    if name in _BOOL_DEFAULTS and value is None:
        return name, _BOOL_DEFAULTS[name]
    return name, value


def _apply(profile: TrainerProfile, values: dict[str, Any]) -> None:
    for name, value in values.items():
        if name == "topics":
            continue
        attr, stored = _column_value(name, value)
        setattr(profile, attr, stored)


def _set_topics(session: Session, profile_id: int, resolved: list[tuple[Topic, str]]) -> None:
    session.execute(delete(TrainerTopic).where(TrainerTopic.profile_id == profile_id))
    for topic, level in resolved:
        session.add(TrainerTopic(profile_id=profile_id, topic_id=topic.id, level=level))


# --------------------------------------------------------------------------- serialization


def _cv_for(session: Session, user_id: int) -> CvDocument | None:
    return session.scalar(select(CvDocument).where(CvDocument.user_id == user_id))


def cv_meta(cv: CvDocument) -> dict:
    """Owner/admin CV metadata — never the extracted text."""
    return {
        "id": cv.id,
        "source": cv.source,
        "original_filename": cv.original_filename,
        "content_type": cv.content_type,
        "size_bytes": cv.size_bytes,
        "draft_status": cv.draft_status,
        "created_at": iso_z(cv.created_at),
    }


def cv_summary(cv: CvDocument) -> dict:
    """The upload response shape: `{"id", "source", "original_filename", "draft_status"}`."""
    return {
        "id": cv.id,
        "source": cv.source,
        "original_filename": cv.original_filename,
        "draft_status": cv.draft_status,
    }


def _profile_topics(session: Session, profile_id: int) -> list[dict]:
    rows = session.execute(
        select(Topic.slug, Topic.name, TrainerTopic.level)
        .join(TrainerTopic, TrainerTopic.topic_id == Topic.id)
        .where(TrainerTopic.profile_id == profile_id)
        .order_by(Topic.position, Topic.id)
    )
    return [{"slug": slug, "name": name, "level": level} for slug, name, level in rows]


def _directory_block(profile: TrainerProfile, topics: list[dict], has_cv: bool) -> dict:
    from src.workshop0.services import directory  # lazy: directory imports this module

    slug = profile.public_slug
    return {
        "visibility": profile.visibility,
        "listed": directory._is_listed(profile, topics, has_cv),
        "path": directory.public_path(slug) if slug else None,
        "min_completeness": directory.MIN_COMPLETENESS,
    }


def own_profile(session: Session, profile: TrainerProfile, user: AppUser) -> dict:
    """OwnProfile — the ONLY non-admin payload carrying rates, email and CV fields.
    An explicit allow-list (never "model minus some fields")."""
    topics = _profile_topics(session, profile.id)
    cv = _cv_for(session, user.id)
    score = completeness(profile, topic_count=len(topics), has_cv=cv is not None)
    return {
        "profile": {
            "id": profile.id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "headline": profile.headline,
            "bio_md": profile.bio_md or "",
            "city": profile.city,
            "remote_ok": bool(profile.remote_ok),
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "website_url": profile.website_url,
            "topics": topics,
            "past_work": _loads(profile.past_work_json, []),
            "rate_min": profile.rate_min,
            "rate_max": profile.rate_max,
            "rate_currency": profile.rate_currency,
            "rate_unit": profile.rate_unit,
            "pro_bono": bool(profile.pro_bono),
            "availability": _loads(profile.availability_json, {}),
            "available_from": profile.available_from.isoformat() if profile.available_from else None,
            "blackouts": _loads(profile.blackout_json, []),
            "visibility": profile.visibility,
            "directory": _directory_block(profile, topics, cv is not None),
            "verified": bool(profile.verified),
            "verified_at": iso_z(profile.verified_at) if profile.verified_at else None,
            "consent_at": iso_z(profile.consent_at),
            "consent_version": profile.consent_version,
            "autofilled_fields": _loads(profile.autofilled_fields_json, []),
            "cv": cv_meta(cv) if cv else None,
            "created_at": iso_z(profile.created_at),
            "updated_at": iso_z(profile.updated_at),
        },
        "completeness": {"pct": score.pct, "missing": score.missing},
    }


def get_profile(session: Session, user_id: int) -> TrainerProfile | None:
    return session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))


def _user(session: Session, user_id: int) -> AppUser:
    user = session.get(AppUser, user_id)
    if user is None:  # session outlived the account (deleted elsewhere)
        raise api_error("not_signed_in", "Please sign in again.", 401)
    return user


def read_own(session: Session, user_id: int) -> dict:
    profile = get_profile(session, user_id)
    if profile is None:
        raise not_found("You have not created a profile yet.")
    return own_profile(session, profile, _user(session, user_id))


# --------------------------------------------------------------------------- create / patch


def _draft_for(session: Session, user_id: int) -> tuple[dict | None, list[str]]:
    cv = _cv_for(session, user_id)
    if cv is None or cv.draft_status != "ready":
        return None, []
    return parse_draft(cv.draft_json)


def _comparable(name: str, value: Any) -> Any:
    """Normalise a ProfileInput value (validated model or draft JSON) for equality checks."""
    if isinstance(value, list):
        out = []
        for item in value:
            out.append(item.model_dump(mode="json") if isinstance(item, BaseModel) else item)
        if name == "topics":
            return sorted((t.get("slug"), t.get("level")) for t in out if isinstance(t, dict))
        return out
    if isinstance(value, date):
        return value.isoformat()
    return value


def _enqueue_welcome(
    session: Session, profile: TrainerProfile, user: AppUser, base_url: str | None
) -> None:
    """`network.welcome` on profile create (consent was just recorded). Never blocks creation."""
    from src.workshop0.config.settings import get_settings
    from src.workshop0.email.outbox import enqueue

    if not getattr(user, "email", None):
        return
    base = (base_url or get_settings().resolved_base_url or "http://localhost:8001").rstrip("/")
    try:
        enqueue(
            session,
            to=user.email,
            template="network.welcome",
            context={
                "name": user.display_name or "",
                "applications_url": f"{base}/app/network/applications/",
            },
            dedupe_key=f"welcome:{profile.id}",
        )
    except Exception:  # an email problem must never fail profile creation
        log.warning("email.enqueue_failed", template="network.welcome")


def create_profile(
    session: Session, user_id: int, body: ProfileCreate, *, base_url: str | None = None
) -> dict:
    if body.consent is not True:
        raise validation_error("consent: please agree to continue")
    if get_profile(session, user_id) is not None:
        raise api_error("profile_exists", "You already have a profile — edit it instead.", 409)
    user = _user(session, user_id)
    values = {name: getattr(body, name) for name in PROFILE_FIELDS}
    _check_rates(values["rate_min"], values["rate_max"])
    resolved = _resolve_topics(session, body.topics)

    now = utcnow()
    profile = TrainerProfile(user_id=user_id, consent_at=now, consent_version=CONSENT_VERSION)
    _apply(profile, values)

    # Fields still exactly as the CV drafter proposed them stay flagged "please check".
    draft, drafted = _draft_for(session, user_id)
    if draft:
        unchanged = [
            f for f in drafted
            if f in PROFILE_FIELDS and _comparable(f, values[f]) == _comparable(f, draft.get(f))
        ]
        profile.autofilled_fields_json = json.dumps(unchanged)

    invite = session.scalar(
        select(NetworkInvite)
        .where(NetworkInvite.accepted_user_id == user_id, NetworkInvite.accepted_at.is_not(None))
        .order_by(NetworkInvite.accepted_at.desc())
        .limit(1)
    )
    if invite is not None:
        profile.verified = True
        profile.verified_at = now
        profile.verified_by = invite.created_by

    session.add(profile)
    session.flush()
    _set_topics(session, profile.id, resolved)
    record_action(
        session,
        None,
        "user",
        "profile.create",
        {"topics": [t.slug for t, _ in resolved], "verified_by_invite": invite is not None},
        subject_type="trainer",
        subject_id=profile.id,
    )
    session.flush()
    _enqueue_welcome(session, profile, user, base_url)
    log.info(
        "profile.created",
        profile_id=profile.id,
        user_id=user_id,
        topics=len(resolved),
        verified=bool(profile.verified),
    )
    return own_profile(session, profile, user)


def update_profile(session: Session, user_id: int, body: ProfilePatch) -> dict:
    profile = get_profile(session, user_id)
    if profile is None:
        raise not_found("You have not created a profile yet.")
    user = _user(session, user_id)
    sent = {name: getattr(body, name) for name in body.model_fields_set if name in PROFILE_FIELDS}
    for name in _NOT_NULL:
        if name in sent and sent[name] is None:
            raise validation_error(f"{name}: is required")
    _check_rates(sent.get("rate_min", profile.rate_min), sent.get("rate_max", profile.rate_max))
    resolved = None
    if "topics" in sent:
        resolved = _resolve_topics(session, sent["topics"], keep_ids=_current_topic_ids(session, profile.id))

    visibility = body.visibility if "visibility" in body.model_fields_set else None
    _apply(profile, sent)
    if resolved is not None:
        _set_topics(session, profile.id, resolved)
    if visibility is not None:
        from src.workshop0.services import directory  # lazy: directory imports this module

        profile.visibility = visibility
        if visibility == "public":
            directory.ensure_slug(session, profile, user)
    # A visibility-only patch is not a review of the pre-fill; any content field is.
    if sent or visibility is None:
        profile.autofilled_fields_json = "[]"
    profile.updated_at = utcnow()
    changed = sorted(set(sent) | ({"visibility"} if visibility is not None else set()))
    record_action(
        session,
        None,
        "user",
        "profile.update",
        {"changed_fields": changed},
        subject_type="trainer",
        subject_id=profile.id,
    )
    session.flush()
    log.info("profile.updated", profile_id=profile.id, changed_fields=changed)
    return own_profile(session, profile, user)


# --------------------------------------------------------------------------- CV ingest


@dataclass(frozen=True)
class CvUpload:
    data: bytes
    kind: str  # pdf | docx
    filename: str | None
    content_type: str


def classify_upload(data: bytes, filename: str | None, content_type: str | None) -> CvUpload:
    """Size + type gate by magic bytes (never trusting the declared type alone)."""
    if len(data) > MAX_CV_BYTES:
        raise api_error("file_too_large", "That file is over 5 MB — please upload a smaller CV.", 413)
    name = (filename or "").strip()[:200] or None
    lowered = (name or "").lower()
    if b"%PDF-" in data[:1024]:  # the spec allows leading junk before the header
        return CvUpload(data, "pdf", name, "application/pdf")
    if data.startswith(b"PK\x03\x04") and (
        lowered.endswith(".docx") or (content_type or "").split(";")[0].strip() == DOCX_CONTENT_TYPE
    ):
        return CvUpload(data, "docx", name, DOCX_CONTENT_TYPE)
    raise api_error("unsupported_file", "Please upload a PDF or a Word (.docx) file.", 415)


def _store_cv(
    session: Session,
    user_id: int,
    *,
    source: str,
    original_filename: str | None,
    storage_key: str | None,
    content_type: str | None,
    raw: bytes,
    text: str,
) -> tuple[CvDocument, str | None]:
    """Insert or replace (in place, keeping the id so drafting spend stays attributed) the
    user's one cv_document. Returns the row and the previous blob key to delete."""
    cv = _cv_for(session, user_id)
    old_key = None
    replaced = cv is not None
    if cv is None:
        cv = CvDocument(user_id=user_id)
        session.add(cv)
    else:
        old_key = cv.storage_key
    cv.source = source
    cv.original_filename = original_filename
    cv.storage_key = storage_key
    cv.content_type = content_type
    cv.size_bytes = len(raw)
    cv.sha256 = hashlib.sha256(raw).hexdigest()
    cv.text_extract = text[:TEXT_EXTRACT_MAX]
    cv.draft_status = "pending"
    cv.draft_json = None
    cv.created_at = utcnow()
    session.flush()
    record_action(
        session,
        None,
        "user",
        "cv.upload",
        {"source": source, "size_bytes": len(raw), "replaced": replaced},
        subject_type="user",
        subject_id=user_id,
    )
    return cv, (old_key if old_key != storage_key else None)


def ingest_file(session: Session, store: BlobStore, user_id: int, upload: CvUpload) -> tuple[CvDocument, str | None]:
    from src.workshop0.services.cv_text import CvUnreadable, extract_text

    try:
        text = extract_text(upload.data, upload.kind)  # type: ignore[arg-type]
    except CvUnreadable:
        raise api_error(
            "cv_unreadable",
            "We couldn't read any text from that file — paste your CV text instead.",
            422,
        ) from None
    key = f"cv/{user_id}/{uuid.uuid4().hex}.{upload.kind}"
    store.put(key, upload.data, upload.content_type)
    try:
        cv, old_key = _store_cv(
            session,
            user_id,
            source=upload.kind,
            original_filename=upload.filename,
            storage_key=key,
            content_type=upload.content_type,
            raw=upload.data,
            text=text,
        )
    except Exception:
        _safe_delete(store, key)
        raise
    log.info("cv.uploaded", user_id=user_id, cv_id=cv.id, source=upload.kind, size_bytes=len(upload.data))
    return cv, old_key


def validate_pasted_text(text: Any) -> str:
    if not isinstance(text, str):
        raise validation_error("text: please paste your CV text")
    trimmed = text.strip()
    if len(trimmed) < TEXT_MIN:
        raise validation_error(f"text: please paste at least {TEXT_MIN} characters of your CV")
    if len(trimmed) > TEXT_MAX:
        raise validation_error(f"text: please paste at most {TEXT_MAX} characters")
    return trimmed


def ingest_text(session: Session, user_id: int, text: str) -> tuple[CvDocument, str | None]:
    raw = text.encode("utf-8")
    cv, old_key = _store_cv(
        session,
        user_id,
        source="text",
        original_filename=None,
        storage_key=None,
        content_type="text/plain",
        raw=raw,
        text=text,
    )
    log.info("cv.uploaded", user_id=user_id, cv_id=cv.id, source="text", size_bytes=len(raw))
    return cv, old_key


def _safe_delete(store: BlobStore, key: str | None) -> None:
    if not key:
        return
    try:
        store.delete(key)
    except Exception as exc:  # noqa: BLE001 — a stale blob must never fail the request
        log.error("cv.blob_delete_failed", key_prefix=key.rsplit("/", 1)[0], error=type(exc).__name__)


def delete_blob(store: BlobStore, key: str | None) -> None:
    _safe_delete(store, key)


# --------------------------------------------------------------------------- draft polling


def parse_draft(raw: str | None) -> tuple[dict | None, list[str]]:
    """`draft_json` holds the drafter's validated output. Accepts either the bare ProfileInput
    draft or a `{"draft": …, "autofilled_fields": […]}` wrapper."""
    data = _loads(raw, None)
    if not isinstance(data, dict):
        return None, []
    if isinstance(data.get("draft"), dict):
        draft = data["draft"]
        fields = data.get("autofilled_fields")
    else:
        draft, fields = data, None
    if not isinstance(fields, list):
        from src.workshop0.ai.profile_draft import autofilled_fields_of

        fields = autofilled_fields_of(draft)
    return draft, [f for f in fields if isinstance(f, str)]


def draft_state(session: Session, user_id: int) -> dict:
    cv = _cv_for(session, user_id)
    if cv is None:
        raise not_found("Upload or paste your CV first.")
    draft, fields = (parse_draft(cv.draft_json) if cv.draft_status == "ready" else (None, []))
    return {"draft_status": cv.draft_status, "draft": draft, "autofilled_fields": fields if draft else []}


def mark_draft_failed_if_pending(session: Session, cv_document_id: int) -> None:
    cv = session.get(CvDocument, cv_document_id)
    if cv is not None and cv.draft_status == "pending":
        cv.draft_status = "failed"


def own_cv(session: Session, user_id: int) -> CvDocument:
    cv = _cv_for(session, user_id)
    if cv is None:
        raise not_found("You have no CV on file.")
    return cv


# --------------------------------------------------------------------------- deletion


def delete_account(session: Session, user_id: int, confirm_email: Any) -> str | None:
    """Delete the CV row, profile (cascades topics/tags/notes), sessions and the user; write
    `account.delete` with only the masked email. Returns the blob key for the caller to
    delete once the transaction has committed."""
    user = _user(session, user_id)
    if not isinstance(confirm_email, str) or confirm_email.strip().lower() != user.email.lower():
        raise validation_error("confirm_email: type your account email to confirm")
    cv = _cv_for(session, user_id)
    blob_key = cv.storage_key if cv else None
    profile = get_profile(session, user_id)
    masked = mask_email(user.email)

    if cv is not None:
        session.delete(cv)
    if profile is not None:
        session.delete(profile)
    session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
    session.flush()
    session.delete(user)
    record_action(
        session,
        None,
        "user",
        "account.delete",
        {"email": masked},
        subject_type="user",
        subject_id=user_id,
    )
    session.flush()
    log.info("account.deleted", user_id=user_id, email=masked)
    return blob_key
