"""Managed partner list (spec/api.md §Phase 11b, data-model.md §Phase 11b).

`partner.internal_name` and `partner.notes` are admin-only: nothing here is ever called from
a public surface, and the structlog events carry ids only (never names or notes).

- `normalize_name` / `resolve_partner` are shared with the opportunity writer (F3) and the
  drafter (F4); `resolve_partner` flushes but never commits.
- Admin CRUD (`list_partners`, `create_partner`, `update_partner`) commits itself, appends
  the `partner.create` / `partner.update` audit row in the same transaction, and rewrites the
  `opportunity.partner_internal_name` mirror on a rename.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, StrictBool, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, iso_z
from src.workshop0.db.models import Opportunity, Partner
from src.workshop0.services.audit import record_action

log = structlog.get_logger("workshop0")

ADMIN_ACTOR = "admin"
SUBJECT = "partner"
PARTNER_EXISTS_MESSAGE: str = "A partner with this name already exists."
NOT_FOUND_MESSAGE = "No partner matches this id."
NAME_MIN, NAME_MAX = 2, 160
DISPLAY_MAX = 160
NOTES_MAX = 5000


# --------------------------------------------------------------------------- normalization


def normalize_name(name: str) -> tuple[str, str]:
    """Return `(collapsed, name_key)`: trimmed, internal whitespace collapsed to single
    spaces, and its `casefold()` (the unique, case/whitespace-insensitive key)."""
    collapsed = " ".join((name or "").split())
    return collapsed, collapsed.casefold()


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_optional(value: str | None, limit: int) -> str | None:
    value = _blank_to_none(value)
    if value is not None and len(value) > limit:
        raise ValueError(f"must be at most {limit} characters")
    return value


def _check_name(collapsed: str, label: str) -> None:
    if not NAME_MIN <= len(collapsed) <= NAME_MAX:
        raise api_error(
            "validation_error", f"{label}: must be {NAME_MIN} to {NAME_MAX} characters", 422
        )


# --------------------------------------------------------------------------- serializers


def partner_ref(partner: Partner) -> dict:
    """PartnerRef — never `notes`, never `name_key`."""
    return {
        "id": partner.id,
        "internal_name": partner.internal_name,
        "display_name": partner.display_name,
        "active": bool(partner.active),
    }


def _admin_partner(partner: Partner, opportunity_count: int) -> dict:
    return {
        **partner_ref(partner),
        "notes": partner.notes,
        "opportunity_count": opportunity_count,
        "created_at": iso_z(partner.created_at),
        "updated_at": iso_z(partner.updated_at),
    }


def _opportunity_count(session: Session, partner_id: int) -> int:
    return int(
        session.execute(
            select(func.count()).select_from(Opportunity).where(Opportunity.partner_id == partner_id)
        ).scalar_one()
    )


def active_partners(session: Session) -> list[Partner]:
    """Active partners ordered by `name_key` (the drafter's matching candidates)."""
    return list(
        session.execute(
            select(Partner).where(Partner.active.is_(True)).order_by(Partner.name_key)
        ).scalars()
    )


# --------------------------------------------------------------------------- resolve


def _audit_create(session: Session, partner: Partner, by: str) -> None:
    record_action(
        session,
        None,
        ADMIN_ACTOR,
        "partner.create",
        {"internal_name": partner.internal_name, "by": by},
        subject_type=SUBJECT,
        subject_id=partner.id,
    )


def _require_usable(partner: Partner, current_partner_id: int | None) -> Partner:
    if not partner.active and partner.id != current_partner_id:
        raise api_error("validation_error", "partner_id: partner is inactive", 422)
    return partner


def _by_id(session: Session, partner_id: int, current_partner_id: int | None) -> Partner:
    partner = session.get(Partner, partner_id) if 0 < partner_id <= 2_147_483_647 else None
    if partner is None:
        raise api_error(
            "validation_error", f"partner_id: partner {partner_id} does not exist", 422
        )
    return _require_usable(partner, current_partner_id)


def _by_key(session: Session, name_key: str) -> Partner | None:
    return session.execute(select(Partner).where(Partner.name_key == name_key)).scalar_one_or_none()


def _create_for_name(
    session: Session, collapsed: str, key: str, display_name: str | None, by: str
) -> Partner:
    partner = Partner(
        internal_name=collapsed,
        name_key=key,
        display_name=_blank_to_none(display_name),
        notes=None,
        active=True,
    )
    try:
        with session.begin_nested():  # race-safe: the unique name_key decides
            session.add(partner)
            session.flush()
    except IntegrityError:
        existing = _by_key(session, key)
        if existing is None:
            raise
        return existing
    _audit_create(session, partner, by)
    session.flush()
    log.info("partner.created", partner_id=partner.id)
    return partner


def resolve_partner(
    session: Session,
    *,
    partner_id: int | None,
    partner_id_given: bool,
    internal_name: str | None,
    internal_name_given: bool,
    display_name_hint: str | None,
    current_partner_id: int | None,
    by: str,
) -> Partner | None:
    """Resolve the partner for an opportunity write. Flushes, never commits.

    - `partner_id` given: null clears; otherwise it must exist and (if inactive) already be
      the listing's partner (`current_partner_id`).
    - else `internal_name` (legacy) given: null/blank clears; otherwise matched on `name_key`
      (inactive rule as above); no match creates a partner (`display_name` = the hint) with a
      `partner.create` audit row in the same transaction.
    - both given and resolving to different partners → `"partner_id: conflicts with
      partner_internal_name"` (a name that matches nothing never creates a partner then).
    - neither given: the current partner is kept.
    Errors raise `validation_error` (422) via `api_error`.
    """
    name_clear = internal_name_given and _blank_to_none(internal_name) is None

    if partner_id_given and internal_name_given:
        by_id = None if partner_id is None else _by_id(session, partner_id, current_partner_id)
        if name_clear:
            by_name = None
        else:
            collapsed, key = normalize_name(internal_name or "")
            existing = _by_key(session, key)
            by_name = _require_usable(existing, current_partner_id) if existing else None
            if existing is None:
                if by_id is not None:
                    raise api_error(
                        "validation_error",
                        "partner_id: conflicts with partner_internal_name",
                        422,
                    )
        if (by_id.id if by_id else None) != (by_name.id if by_name else None):
            raise api_error(
                "validation_error", "partner_id: conflicts with partner_internal_name", 422
            )
        if by_id is None and not name_clear and by_name is None:  # id null, unmatched name
            raise api_error(
                "validation_error", "partner_id: conflicts with partner_internal_name", 422
            )
        return by_id

    if partner_id_given:
        return None if partner_id is None else _by_id(session, partner_id, current_partner_id)

    if internal_name_given:
        if name_clear:
            return None
        collapsed, key = normalize_name(internal_name or "")
        _check_name(collapsed, "partner_internal_name")
        existing = _by_key(session, key)
        if existing is not None:
            return _require_usable(existing, current_partner_id)
        return _create_for_name(session, collapsed, key, display_name_hint, by)

    if current_partner_id is None:
        return None
    return session.get(Partner, current_partner_id)


# --------------------------------------------------------------------------- request models


class PartnerCreate(BaseModel):
    internal_name: str
    display_name: str | None = None
    notes: str | None = None

    @field_validator("internal_name")
    @classmethod
    def _name(cls, value: str) -> str:
        collapsed, _ = normalize_name(value)
        if not NAME_MIN <= len(collapsed) <= NAME_MAX:
            raise ValueError(f"must be {NAME_MIN} to {NAME_MAX} characters")
        return collapsed

    @field_validator("display_name")
    @classmethod
    def _display(cls, value: str | None) -> str | None:
        return _clean_optional(value, DISPLAY_MAX)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return _clean_optional(value, NOTES_MAX)


class PartnerPatch(BaseModel):
    internal_name: str | None = None
    display_name: str | None = None
    notes: str | None = None
    active: StrictBool | None = None

    @field_validator("internal_name")
    @classmethod
    def _name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("cannot be null")
        collapsed, _ = normalize_name(value)
        if not NAME_MIN <= len(collapsed) <= NAME_MAX:
            raise ValueError(f"must be {NAME_MIN} to {NAME_MAX} characters")
        return collapsed

    @field_validator("active")
    @classmethod
    def _active(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("cannot be null")
        return value

    @field_validator("display_name")
    @classmethod
    def _display(cls, value: str | None) -> str | None:
        return _clean_optional(value, DISPLAY_MAX)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return _clean_optional(value, NOTES_MAX)


# --------------------------------------------------------------------------- admin CRUD


def list_partners(session: Session) -> dict:
    counts = dict(
        session.execute(
            select(Opportunity.partner_id, func.count())
            .where(Opportunity.partner_id.is_not(None))
            .group_by(Opportunity.partner_id)
        ).all()
    )
    partners = session.execute(select(Partner).order_by(Partner.name_key, Partner.id)).scalars()
    return {"partners": [_admin_partner(p, int(counts.get(p.id, 0))) for p in partners]}


def create_partner(session: Session, body: PartnerCreate, *, by: str) -> dict:
    _, key = normalize_name(body.internal_name)
    if _by_key(session, key) is not None:
        raise api_error("partner_exists", PARTNER_EXISTS_MESSAGE, 409)
    partner = Partner(
        internal_name=body.internal_name,
        name_key=key,
        display_name=body.display_name,
        notes=body.notes,
        active=True,
    )
    try:
        session.add(partner)
        session.flush()
    except IntegrityError:
        session.rollback()
        raise api_error("partner_exists", PARTNER_EXISTS_MESSAGE, 409) from None
    _audit_create(session, partner, by)
    session.commit()
    log.info("partner.created", partner_id=partner.id)
    return {"partner": _admin_partner(partner, 0)}


def update_partner(session: Session, partner_id: int, body: PartnerPatch, *, by: str) -> dict:
    partner = session.get(Partner, partner_id) if 0 < partner_id <= 2_147_483_647 else None
    if partner is None:
        raise api_error("not_found", NOT_FOUND_MESSAGE, 404)

    changed: list[str] = []
    renamed = False
    for field in ("internal_name", "display_name", "notes", "active"):
        if field not in body.model_fields_set:
            continue
        new = getattr(body, field)
        if new == getattr(partner, field):
            continue
        if field == "internal_name":
            _, key = normalize_name(new)
            clash = _by_key(session, key)
            if clash is not None and clash.id != partner.id:
                session.rollback()
                raise api_error("partner_exists", PARTNER_EXISTS_MESSAGE, 409)
            partner.name_key = key
            renamed = True
        setattr(partner, field, new)
        changed.append(field)

    if changed:
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise api_error("partner_exists", PARTNER_EXISTS_MESSAGE, 409) from None
        if renamed:
            session.execute(
                update(Opportunity)
                .where(Opportunity.partner_id == partner.id)
                .values(
                    partner_internal_name=partner.internal_name,
                    updated_at=Opportunity.updated_at,  # a mirror refresh is not a listing edit
                )
                .execution_options(synchronize_session=False)
            )
        record_action(
            session,
            None,
            ADMIN_ACTOR,
            "partner.update",
            {"internal_name": partner.internal_name, "changed_fields": changed, "by": by},
            subject_type=SUBJECT,
            subject_id=partner.id,
        )
        session.commit()
        log.info("partner.updated", partner_id=partner.id)
    session.refresh(partner)
    return {"partner": _admin_partner(partner, _opportunity_count(session, partner.id))}
