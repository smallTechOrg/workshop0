"""Phase 13: workshop <-> trainer facilitator links (C19).

Linking grants a trainer the workshop's existing facilitator link and nothing else; it never
touches `admin_token`. Admin payloads may carry `email`; `workshops_for` is the trainer's own view.
"""

from __future__ import annotations

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, as_utc
from src.workshop0.db.models import AppUser, TrainerProfile, Workshop, WorkshopFacilitator
from src.workshop0.services.audit import record_action

ROLES = ("lead", "co", "ta")
MAX_FACILITATORS = 10
ADMIN_ACTOR = "admin"


def _validation_error(message: str):
    return api_error("validation_error", message, 422)


def _workshop(session: Session, workshop_id: int) -> Workshop:
    workshop = session.get(Workshop, workshop_id)
    if workshop is None:
        raise api_error("not_found", "Workshop not found.", 404)
    return workshop


def _iso(dt) -> str:
    return as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _role_order():
    return case(
        (WorkshopFacilitator.role == "lead", 0),
        (WorkshopFacilitator.role == "co", 1),
        else_=2,
    )


def list_for_workshop(session: Session, workshop_id: int) -> list[dict]:
    _workshop(session, workshop_id)
    return _rows(session, workshop_id)


def _rows(session: Session, workshop_id: int) -> list[dict]:
    stmt = (
        select(WorkshopFacilitator, TrainerProfile, AppUser)
        .join(TrainerProfile, TrainerProfile.id == WorkshopFacilitator.profile_id)
        .join(AppUser, AppUser.id == TrainerProfile.user_id)
        .where(WorkshopFacilitator.workshop_id == workshop_id)
        .order_by(_role_order(), WorkshopFacilitator.created_at, WorkshopFacilitator.profile_id)
    )
    return [
        {
            "profile_id": link.profile_id,
            "role": link.role,
            "display_name": user.display_name,
            "headline": profile.headline,
            "email": user.email,
            "linked_by": link.linked_by,
            "created_at": _iso(link.created_at),
        }
        for link, profile, user in session.execute(stmt).all()
    ]


def _parse_item(raw, index: int) -> tuple[int, str]:
    label = f"facilitators[{index}]"
    if not isinstance(raw, dict):
        raise _validation_error(f"{label}: must be an object")
    profile_id, role = raw.get("profile_id"), raw.get("role")
    if isinstance(profile_id, bool) or not isinstance(profile_id, int):
        raise _validation_error(f"{label}.profile_id: must be an integer")
    if role not in ROLES:
        raise _validation_error(f"{label}.role: must be one of lead, co, ta")
    return profile_id, role


def _validate(session: Session, items) -> list[tuple[int, str]]:
    if not isinstance(items, list):
        raise _validation_error("facilitators: must be a list")
    if len(items) > MAX_FACILITATORS:
        raise _validation_error(f"facilitators: at most {MAX_FACILITATORS} entries")
    parsed = [_parse_item(raw, i) for i, raw in enumerate(items)]
    seen: set[int] = set()
    leads = 0
    for i, (profile_id, role) in enumerate(parsed):
        if profile_id in seen:
            raise _validation_error(f"facilitators[{i}].profile_id: duplicate profile")
        seen.add(profile_id)
        if role == "lead":
            leads += 1
            if leads > 1:
                raise _validation_error(f"facilitators[{i}].role: only one lead per workshop")
    if seen:
        found = set(session.scalars(select(TrainerProfile.id).where(TrainerProfile.id.in_(seen))))
        for i, (profile_id, _role) in enumerate(parsed):
            if profile_id not in found:
                raise _validation_error(f"facilitators[{i}].profile_id: profile does not exist")
    return parsed


def _apply(session: Session, workshop_id: int, target: dict[int, str], *, by: str) -> list[dict]:
    existing = {
        link.profile_id: link
        for link in session.scalars(
            select(WorkshopFacilitator).where(WorkshopFacilitator.workshop_id == workshop_id)
        )
    }
    current = {pid: link.role for pid, link in existing.items()}
    if current == target:
        return _rows(session, workshop_id)
    added = [{"profile_id": p, "role": r} for p, r in target.items() if p not in current]
    removed = [p for p in current if p not in target]
    changed = [{"profile_id": p, "role": r} for p, r in target.items() if p in current and current[p] != r]
    # Removals (and demotions) first so a lead swap never trips a transient double-lead.
    for pid in removed:
        session.delete(existing[pid])
    for entry in changed:
        existing[entry["profile_id"]].role = entry["role"]
    session.flush()
    for entry in added:
        session.add(
            WorkshopFacilitator(
                workshop_id=workshop_id, profile_id=entry["profile_id"], role=entry["role"], linked_by=by
            )
        )
    session.flush()
    record_action(
        session,
        workshop_id,
        ADMIN_ACTOR,
        "workshop.facilitators",
        {"added": added, "removed": removed, "changed": changed, "by": by},
        subject_type="workshop",
        subject_id=workshop_id,
    )
    session.commit()
    return _rows(session, workshop_id)


def replace_for_workshop(session: Session, workshop_id: int, items: list, *, by: str) -> list[dict]:
    _workshop(session, workshop_id)
    parsed = _validate(session, items)
    return _apply(session, workshop_id, dict(parsed), by=by)


def add_one(session: Session, workshop_id: int, profile_id: int, role: str, *, by: str) -> list[dict]:
    _workshop(session, workshop_id)
    target = {
        link.profile_id: link.role
        for link in session.scalars(
            select(WorkshopFacilitator).where(WorkshopFacilitator.workshop_id == workshop_id)
        )
    }
    target[profile_id] = role  # adds or updates; order is irrelevant to validation
    parsed = _validate(session, [{"profile_id": p, "role": r} for p, r in target.items()])
    return _apply(session, workshop_id, dict(parsed), by=by)


def workshops_for(session: Session, profile_id: int, *, base_url: str) -> list[dict]:
    """The trainer's own workshops: no other facilitator, no email, no counts."""
    base = base_url.rstrip("/")
    stmt = (
        select(WorkshopFacilitator, Workshop)
        .join(Workshop, Workshop.id == WorkshopFacilitator.workshop_id)
        .where(WorkshopFacilitator.profile_id == profile_id)
        .order_by(WorkshopFacilitator.created_at.desc(), Workshop.id.desc())
    )
    return [
        {
            "workshop_id": workshop.id,
            "name": workshop.name,
            "status": workshop.status,
            "role": link.role,
            "facilitator_url": f"{base}/f/{workshop.admin_token}",
            "linked_at": _iso(link.created_at),
        }
        for link, workshop in session.execute(stmt).all()
    ]
