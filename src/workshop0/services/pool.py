"""Admin trainer pool (spec/api.md §Phase 11 Admin pool; capabilities.md C13).

Everything here is admin-only: rates, emails, notes and tags are serialized freely
because the router sits behind `require_admin`. Never call these serializers from a
non-admin surface.

- `list_trainers` / `export_csv` share one filter builder (`q`, `topic` ANY-of,
  `verified`, `tag`), so the CSV row count always equals the filtered `total`.
- Writes (`set_verified`, `add_note`, `set_tags`, `prepare_cv_download`) each append
  exactly one audit row (`facilitator_action`, actor `admin`, `subject_type="trainer"`,
  `subject_id=<profile id>`, `detail.by` = the AdminActor).
- Spend: network rows are `ai_usage WHERE workshop_id IS NULL`; a trainer's drafting cost
  is the network rows linked to their current `cv_document`.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import structlog
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, iso_z, utcnow
from src.workshop0.db.models import (
    AdminNote,
    AiUsage,
    AppUser,
    CvDocument,
    FacilitatorAction,
    Topic,
    TrainerProfile,
    TrainerTag,
    TrainerTopic,
)
from src.workshop0.services import profiles
from src.workshop0.services.audit import record_action

log = structlog.get_logger("workshop0")

ADMIN_ACTOR = "admin"
SUBJECT = "trainer"
NOT_FOUND_MESSAGE = "No trainer matches this id."
NO_CV_MESSAGE = "This trainer has no CV on file."
ACTIVITY_LIMIT = 20
NOTE_MAX = 4000
TAG_MAX_COUNT = 20
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9 -]{0,39}$")
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CSV_COLUMNS = (
    "id",
    "display_name",
    "email",
    "headline",
    "city",
    "remote_ok",
    "topics",
    "rate_min",
    "rate_max",
    "rate_currency",
    "rate_unit",
    "pro_bono",
    "verified",
    "completeness_pct",
    "tags",
    "linkedin_url",
    "github_url",
    "website_url",
    "available_from",
    "created_at",
    "updated_at",
)


# --------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class TrainerFilters:
    q: str | None = None
    topics: list[str] = field(default_factory=list)
    verified: bool | None = None
    tag: str | None = None


def normalize_tag(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


class NoteCreate(BaseModel):
    # The app's validation handler drops a loc segment literally named "body" (it is the
    # request-body marker), so this field's messages carry their own "body: " prefix and
    # a missing/null body is reported by the validator rather than as "Field required".
    body: str | None = Field(default=None, validate_default=True)

    @field_validator("body")
    @classmethod
    def _valid_body(cls, value: str | None) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("body: write a note first")
        if len(cleaned) > NOTE_MAX:
            raise ValueError(f"body: must be at most {NOTE_MAX} characters")
        return cleaned


class TagsReplace(BaseModel):
    tags: list[str]

    @field_validator("tags")
    @classmethod
    def _valid_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            tag = normalize_tag(raw)
            if not tag:
                continue
            if not TAG_RE.match(tag):
                raise ValueError(
                    f"{tag[:40]!r} is not a valid tag — use 1–40 lower-case letters, digits, "
                    "spaces or '-', starting with a letter or digit"
                )
            if tag not in cleaned:
                cleaned.append(tag)
        if len(cleaned) > TAG_MAX_COUNT:
            raise ValueError(f"at most {TAG_MAX_COUNT} tags per trainer")
        return cleaned


# --------------------------------------------------------------------------- queries


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(filters: TrainerFilters) -> list:
    conditions: list = []
    needle = (filters.q or "").strip().lower()
    if needle:
        pattern = f"%{_escape_like(needle)}%"
        conditions.append(
            or_(
                func.lower(AppUser.display_name).like(pattern, escape="\\"),
                func.lower(AppUser.email).like(pattern, escape="\\"),
                func.lower(TrainerProfile.headline).like(pattern, escape="\\"),
                func.lower(TrainerProfile.bio_md).like(pattern, escape="\\"),
            )
        )
    slugs = sorted({s.strip().lower() for s in filters.topics if s and s.strip()})
    if slugs:
        conditions.append(
            TrainerProfile.id.in_(
                select(TrainerTopic.profile_id)
                .join(Topic, Topic.id == TrainerTopic.topic_id)
                .where(Topic.slug.in_(slugs))
            )
        )
    if filters.verified is not None:
        conditions.append(TrainerProfile.verified.is_(filters.verified))
    tag = normalize_tag(filters.tag or "")
    if tag:
        conditions.append(
            exists().where(TrainerTag.profile_id == TrainerProfile.id, TrainerTag.tag == tag)
        )
    return conditions


def _base_select(filters: TrainerFilters):
    return (
        select(TrainerProfile, AppUser)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(*_conditions(filters))
    )


_ORDER = (TrainerProfile.created_at.desc(), TrainerProfile.id.desc())


def _count(session: Session, filters: TrainerFilters) -> int:
    stmt = (
        select(func.count(TrainerProfile.id))
        .select_from(TrainerProfile)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(*_conditions(filters))
    )
    return int(session.scalar(stmt) or 0)


def _topics_by_profile(session: Session, profile_ids: list[int]) -> dict[int, list[dict]]:
    result: dict[int, list[dict]] = {pid: [] for pid in profile_ids}
    if not profile_ids:
        return result
    rows = session.execute(
        select(TrainerTopic.profile_id, TrainerTopic.level, Topic.slug, Topic.name)
        .join(Topic, Topic.id == TrainerTopic.topic_id)
        .where(TrainerTopic.profile_id.in_(profile_ids))
        .order_by(Topic.position, Topic.id)
    ).all()
    for profile_id, level, slug, name in rows:
        result[profile_id].append({"slug": slug, "name": name, "level": level})
    return result


def _tags_by_profile(session: Session, profile_ids: list[int]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {pid: [] for pid in profile_ids}
    if not profile_ids:
        return result
    rows = session.execute(
        select(TrainerTag.profile_id, TrainerTag.tag)
        .where(TrainerTag.profile_id.in_(profile_ids))
        .order_by(TrainerTag.tag)
    ).all()
    for profile_id, tag in rows:
        result[profile_id].append(tag)
    return result


# --------------------------------------------------------------------------- serializers


def _iso_or_none(value: datetime | None) -> str | None:
    return iso_z(value) if value is not None else None


def _rate(profile: TrainerProfile) -> dict | None:
    """Admin-only. `unit` is shown exactly as stored (hour|day|course|month)."""
    if profile.rate_min is None and profile.rate_max is None and not profile.pro_bono:
        return None
    return {
        "min": profile.rate_min,
        "max": profile.rate_max,
        "currency": profile.rate_currency,
        "unit": profile.rate_unit,
        "pro_bono": bool(profile.pro_bono),
    }


def _completeness(profile: TrainerProfile) -> profiles.Completeness:
    return profiles.completeness(profile)


def _row(profile: TrainerProfile, user: AppUser, topics: list[dict], tags: list[str]) -> dict:
    return {
        "id": profile.id,
        "user_id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "headline": profile.headline,
        "city": profile.city,
        "remote_ok": bool(profile.remote_ok),
        "topics": topics,
        "rate": _rate(profile),
        "verified": bool(profile.verified),
        "completeness_pct": _completeness(profile).pct,
        "tags": tags,
        "created_at": iso_z(profile.created_at),
        "updated_at": iso_z(profile.updated_at),
    }


def _loads(raw: str | None, default):
    try:
        value = json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _full(profile: TrainerProfile, user: AppUser, topics: list[dict], tags: list[str]) -> dict:
    done = _completeness(profile)
    full = _row(profile, user, topics, tags)
    full.update(
        {
            "bio_md": profile.bio_md,
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "website_url": profile.website_url,
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
            "verified_at": _iso_or_none(profile.verified_at),
            "verified_by": profile.verified_by,
            "consent_at": _iso_or_none(profile.consent_at),
            "consent_version": profile.consent_version,
            "completeness": {"pct": done.pct, "missing": list(done.missing)},
            "last_login_at": _iso_or_none(user.last_login_at),
        }
    )
    return full


def _cv_meta(cv: CvDocument | None) -> dict | None:
    if cv is None:
        return None
    return {
        "id": cv.id,
        "source": cv.source,
        "original_filename": cv.original_filename,
        "content_type": cv.content_type,
        "size_bytes": cv.size_bytes,
        "draft_status": cv.draft_status,
        "has_file": cv.storage_key is not None,
        "created_at": iso_z(cv.created_at),
    }


def _money(value) -> float:
    return float(round(Decimal(value or 0), 6))


# --------------------------------------------------------------------------- reads


def list_trainers(session: Session, filters: TrainerFilters, *, page: int, page_size: int) -> dict:
    total = _count(session, filters)
    rows = session.execute(
        _base_select(filters).order_by(*_ORDER).offset((page - 1) * page_size).limit(page_size)
    ).all()
    ids = [profile.id for profile, _ in rows]
    topics = _topics_by_profile(session, ids)
    tags = _tags_by_profile(session, ids)
    return {
        "trainers": [_row(p, u, topics[p.id], tags[p.id]) for p, u in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def _get_or_404(session: Session, profile_id: int) -> tuple[TrainerProfile, AppUser]:
    row = session.execute(
        select(TrainerProfile, AppUser)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(TrainerProfile.id == profile_id)
    ).first()
    if row is None:
        raise api_error("not_found", NOT_FOUND_MESSAGE, 404)
    return row[0], row[1]


def _cv_for_user(session: Session, user_id: int) -> CvDocument | None:
    return session.scalar(select(CvDocument).where(CvDocument.user_id == user_id))


def trainer_ai_cost(session: Session, cv: CvDocument | None) -> float:
    """Drafting spend for this trainer: network `ai_usage` rows on their current CV."""
    if cv is None:
        return 0.0
    total = session.scalar(
        select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(
            AiUsage.workshop_id.is_(None), AiUsage.cv_document_id == cv.id
        )
    )
    return _money(total)


def _notes(session: Session, profile_id: int) -> list[dict]:
    rows = session.scalars(
        select(AdminNote)
        .where(AdminNote.profile_id == profile_id)
        .order_by(AdminNote.created_at.desc(), AdminNote.id.desc())
    )
    return [
        {"id": n.id, "body": n.body, "author": n.author, "created_at": iso_z(n.created_at)}
        for n in rows
    ]


def activity(session: Session, profile_id: int) -> list[dict]:
    rows = session.scalars(
        select(FacilitatorAction)
        .where(
            FacilitatorAction.subject_type == SUBJECT,
            FacilitatorAction.subject_id == profile_id,
        )
        .order_by(FacilitatorAction.created_at.desc(), FacilitatorAction.id.desc())
        .limit(ACTIVITY_LIMIT)
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "detail": _loads(row.detail_json, {}),
            "created_at": iso_z(row.created_at),
        }
        for row in rows
    ]


def get_trainer(session: Session, profile_id: int) -> dict:
    profile, user = _get_or_404(session, profile_id)
    topics = _topics_by_profile(session, [profile.id])[profile.id]
    tags = _tags_by_profile(session, [profile.id])[profile.id]
    cv = _cv_for_user(session, user.id)
    return {
        "trainer": _full(profile, user, topics, tags),
        "notes": _notes(session, profile.id),
        "tags": tags,
        "cv": _cv_meta(cv),
        "ai_cost_usd": trainer_ai_cost(session, cv),
        "activity": activity(session, profile.id),
    }


def network_ai_spend(session: Session) -> dict:
    """Totals over `ai_usage WHERE workshop_id IS NULL` (help-desk rows excluded)."""
    network = AiUsage.workshop_id.is_(None)
    total_cost, calls, prompt, completion = session.execute(
        select(
            func.coalesce(func.sum(AiUsage.cost_usd), 0),
            func.count(AiUsage.id),
            func.coalesce(func.sum(AiUsage.prompt_tokens), 0),
            func.coalesce(func.sum(AiUsage.completion_tokens), 0),
        ).where(network)
    ).one()
    by_purpose = session.execute(
        select(AiUsage.purpose, func.coalesce(func.sum(AiUsage.cost_usd), 0), func.count(AiUsage.id))
        .where(network)
        .group_by(AiUsage.purpose)
        .order_by(AiUsage.purpose)
    ).all()
    return {
        "total_cost_usd": _money(total_cost),
        "call_count": int(calls or 0),
        "prompt_tokens": int(prompt or 0),
        "completion_tokens": int(completion or 0),
        "by_purpose": [
            {"purpose": purpose, "cost_usd": _money(cost), "count": int(count)}
            for purpose, cost, count in by_purpose
        ],
    }


# --------------------------------------------------------------------------- CSV


def _csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return "'" + text  # neutralise spreadsheet formula injection
    return text


def csv_filename(now: datetime | None = None) -> str:
    return f"workshop0-trainers-{(now or utcnow()).strftime('%Y%m%d')}.csv"


def export_csv(session: Session, filters: TrainerFilters) -> str:
    """UTF-8 BOM + header + one row per filtered trainer. Never includes CV text."""
    rows = session.execute(_base_select(filters).order_by(*_ORDER)).all()
    ids = [profile.id for profile, _ in rows]
    topics = _topics_by_profile(session, ids)
    tags = _tags_by_profile(session, ids)
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for profile, user in rows:
        record = {
            "id": profile.id,
            "display_name": user.display_name,
            "email": user.email,
            "headline": profile.headline,
            "city": profile.city,
            "remote_ok": bool(profile.remote_ok),
            "topics": "; ".join(f"{t['slug']}:{t['level']}" for t in topics[profile.id]),
            "rate_min": profile.rate_min,
            "rate_max": profile.rate_max,
            "rate_currency": profile.rate_currency,
            "rate_unit": profile.rate_unit,
            "pro_bono": bool(profile.pro_bono),
            "verified": bool(profile.verified),
            "completeness_pct": _completeness(profile).pct,
            "tags": "; ".join(tags[profile.id]),
            "linkedin_url": profile.linkedin_url,
            "github_url": profile.github_url,
            "website_url": profile.website_url,
            "available_from": profile.available_from.isoformat() if profile.available_from else None,
            "created_at": iso_z(profile.created_at),
            "updated_at": iso_z(profile.updated_at),
        }
        writer.writerow([_csv_cell(record[c]) for c in CSV_COLUMNS])
    log.info("network.pool_exported", row_count=len(rows))
    return buffer.getvalue()


# --------------------------------------------------------------------------- writes


def _audit(session: Session, action: str, profile_id: int, detail: dict) -> None:
    record_action(
        session, None, ADMIN_ACTOR, action, detail, subject_type=SUBJECT, subject_id=profile_id
    )


def set_verified(session: Session, profile_id: int, *, verified: bool, by: str) -> dict:
    profile, user = _get_or_404(session, profile_id)
    was = bool(profile.verified)
    profile.verified = verified
    profile.verified_at = utcnow() if verified else None
    profile.verified_by = by if verified else None
    _audit(
        session,
        "trainer.verify" if verified else "trainer.unverify",
        profile.id,
        {"display_name": user.display_name, "from": was, "to": verified, "by": by},
    )
    session.commit()
    log.info("network.trainer_verified", profile_id=profile.id, verified=verified)
    return get_trainer(session, profile.id)


def add_note(session: Session, profile_id: int, body: NoteCreate, *, by: str) -> dict:
    profile, user = _get_or_404(session, profile_id)
    note = AdminNote(profile_id=profile.id, body=body.body, author=by, created_at=utcnow())
    session.add(note)
    session.flush()
    _audit(
        session,
        "trainer.note",
        profile.id,
        {"display_name": user.display_name, "note_id": note.id, "by": by},
    )
    session.commit()
    log.info("network.trainer_noted", profile_id=profile.id, note_id=note.id)
    return {
        "note": {
            "id": note.id,
            "body": note.body,
            "author": note.author,
            "created_at": iso_z(note.created_at),
        },
        "notes": _notes(session, profile.id),
    }


def set_tags(session: Session, profile_id: int, body: TagsReplace, *, by: str) -> dict:
    profile, user = _get_or_404(session, profile_id)
    current = set(_tags_by_profile(session, [profile.id])[profile.id])
    wanted = set(body.tags)
    added = sorted(wanted - current)
    removed = sorted(current - wanted)
    if removed:
        session.execute(
            delete(TrainerTag).where(
                TrainerTag.profile_id == profile.id, TrainerTag.tag.in_(removed)
            )
        )
    for tag in added:
        session.add(TrainerTag(profile_id=profile.id, tag=tag))
    _audit(
        session,
        "trainer.tag",
        profile.id,
        {
            "display_name": user.display_name,
            "tags": sorted(wanted),
            "added": added,
            "removed": removed,
            "by": by,
        },
    )
    session.commit()
    log.info("network.trainer_tagged", profile_id=profile.id, tag_count=len(wanted))
    return {"tags": sorted(wanted)}


@dataclass(frozen=True)
class CvDownload:
    storage_key: str | None
    filename: str
    text: str | None  # pasted-text CVs have no blob; served as a .txt attachment


def _download_name(profile: TrainerProfile, cv: CvDocument) -> str:
    if cv.storage_key is None:
        return f"cv-{profile.id}.txt"
    if cv.original_filename:
        return cv.original_filename
    extension = cv.storage_key.rsplit(".", 1)[-1] if "." in cv.storage_key else cv.source
    return f"cv-{profile.id}.{extension}"


def prepare_cv_download(session: Session, profile_id: int, *, by: str) -> CvDownload:
    """Resolve the trainer's CV and stage the `cv.download` audit row. NOT committed: the
    caller commits once the blob response exists, so a missing blob leaves no audit row."""
    profile, user = _get_or_404(session, profile_id)
    cv = _cv_for_user(session, user.id)
    if cv is None:
        raise api_error("not_found", NO_CV_MESSAGE, 404)
    download = CvDownload(
        storage_key=cv.storage_key,
        filename=_download_name(profile, cv),
        text=cv.text_extract if cv.storage_key is None else None,
    )
    _audit(
        session,
        "cv.download",
        profile.id,
        {"display_name": user.display_name, "cv_id": cv.id, "source": cv.source, "by": by},
    )
    session.flush()
    log.info("network.cv_downloaded", profile_id=profile.id, cv_id=cv.id, source=cv.source)
    return download
