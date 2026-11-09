"""Audit-trail writes into facilitator_action (audit + undo + AI log share one table)."""

import json

from sqlalchemy.orm import Session

from src.workshop0.db.models import FacilitatorAction


def record_action(
    session: Session,
    workshop_id: int | None,
    actor: str,
    action: str,
    detail: dict,
    *,
    subject_type: str | None = None,
    subject_id: int | None = None,
) -> FacilitatorAction:
    """Append one audit row. `subject_type`/`subject_id` (Phase 10) name the row an
    admin-console action acted on (`opportunity`, `topic`, ...); workshop-scoped
    callers leave them unset."""
    row = FacilitatorAction(
        workshop_id=workshop_id,
        actor=actor,
        action=action,
        detail_json=json.dumps(detail, ensure_ascii=False),
        subject_type=subject_type,
        subject_id=subject_id,
    )
    session.add(row)
    return row
