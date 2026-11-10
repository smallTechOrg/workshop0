"""Phase 13: a trainer's saved board searches (C17). Criteria go through
`alerts.validate_criteria`; every read and write is scoped to the owning user, so another
user's id is indistinguishable from an unknown one (404 `not_found`)."""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, iso_z, utcnow
from src.workshop0.db.models import SavedSearch, TrainerProfile
from src.workshop0.services import alerts
from src.workshop0.services.audit import record_action

log = structlog.get_logger("workshop0")

LIMIT = 10
NAME_MAX = 80


def _bad(message: str):
    return api_error("validation_error", message, 422)


def _name(value: Any) -> str:
    if not isinstance(value, str):
        raise _bad("name: must be text")
    name = " ".join(value.split())
    if not name or len(name) > NAME_MAX:
        raise _bad(f"name: must be 1-{NAME_MAX} characters")
    return name


def _enabled(value: Any) -> bool:
    if not isinstance(value, bool):
        raise _bad("alerts_enabled: must be true or false")
    return value


def _serialize(row: SavedSearch) -> dict:
    try:
        criteria = json.loads(row.criteria_json)
    except ValueError:  # pragma: no cover — written only by this module
        criteria = {}
    criteria = {k: list(criteria.get(k) or []) for k in alerts.KEYS}
    return {
        "id": row.id,
        "name": row.name,
        "criteria": criteria,
        "alerts_enabled": bool(row.alerts_enabled),
        "created_at": iso_z(row.created_at),
        "updated_at": iso_z(row.updated_at),
    }


def _profile(session: Session, user_id: int) -> TrainerProfile:
    profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))
    if profile is None:
        raise api_error("profile_required", "Create your trainer profile first.", 409)
    return profile


def _owned(session: Session, user_id: int, search_id: int) -> SavedSearch:
    row = session.scalar(
        select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user_id)
    )
    if row is None:
        raise api_error("not_found", "That saved search doesn't exist.", 404)
    return row


def list_for(session: Session, user_id: int) -> list[dict]:
    rows = session.scalars(
        select(SavedSearch)
        .where(SavedSearch.user_id == user_id)
        .order_by(SavedSearch.created_at.desc(), SavedSearch.id.desc())
    )
    return [_serialize(r) for r in rows]


def create(session: Session, user_id: int, body: dict) -> dict:
    profile = _profile(session, user_id)
    if not isinstance(body, dict):
        raise _bad("body: must be an object")
    name = _name(body.get("name"))
    criteria = alerts.validate_criteria(session, body.get("criteria"))
    enabled = _enabled(body["alerts_enabled"]) if "alerts_enabled" in body else True
    count = session.scalar(
        select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user_id)
    )
    if (count or 0) >= LIMIT:
        raise api_error("search_limit", f"You can save up to {LIMIT} searches.", 409)
    now = utcnow()
    row = SavedSearch(
        user_id=user_id,
        name=name,
        criteria_json=json.dumps(criteria, ensure_ascii=False),
        alerts_enabled=enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    record_action(
        session, None, "user", "search.create",
        {"search_id": row.id, "alerts_enabled": enabled},
        subject_type="trainer", subject_id=profile.id,
    )
    log.info("search.created", search_id=row.id, user_id=user_id)
    return _serialize(row)


def update(session: Session, user_id: int, search_id: int, body: dict) -> dict:
    row = _owned(session, user_id, search_id)
    if not isinstance(body, dict):
        raise _bad("body: must be an object")
    changed: list[str] = []
    if "name" in body:
        row.name = _name(body["name"])
        changed.append("name")
    if "criteria" in body:
        row.criteria_json = json.dumps(
            alerts.validate_criteria(session, body["criteria"]), ensure_ascii=False
        )
        changed.append("criteria")
    if "alerts_enabled" in body:
        row.alerts_enabled = _enabled(body["alerts_enabled"])
        changed.append("alerts_enabled")
    if changed:
        row.updated_at = utcnow()
        profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))
        record_action(
            session, None, "user", "search.update",
            {"search_id": row.id, "changed_fields": changed},
            subject_type="trainer", subject_id=profile.id if profile else None,
        )
    session.flush()
    return _serialize(row)


def delete(session: Session, user_id: int, search_id: int) -> None:
    row = _owned(session, user_id, search_id)
    profile = session.scalar(select(TrainerProfile).where(TrainerProfile.user_id == user_id))
    record_action(
        session, None, "user", "search.delete", {"search_id": row.id},
        subject_type="trainer", subject_id=profile.id if profile else None,
    )
    session.delete(row)
    session.flush()
