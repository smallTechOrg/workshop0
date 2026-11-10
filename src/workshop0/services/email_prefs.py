"""Phase 13: per-user alert/digest switches. A missing `email_pref` row means both on."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.db.models import EmailPref, utcnow


@dataclass(frozen=True)
class EmailPrefs:
    alerts: bool = True
    digest: bool = True


def get(session: Session, user_id: int) -> EmailPrefs:
    row = session.get(EmailPref, user_id)
    return EmailPrefs(row.alerts, row.digest) if row else EmailPrefs()


def prefs_for(session: Session, user_ids) -> dict[int, EmailPrefs]:
    ids = list(dict.fromkeys(user_ids))
    out = {uid: EmailPrefs() for uid in ids}
    if not ids:
        return out
    for row in session.scalars(select(EmailPref).where(EmailPref.user_id.in_(ids))):
        out[row.user_id] = EmailPrefs(row.alerts, row.digest)
    return out


def set_prefs(
    session: Session, user_id: int, *, alerts: bool | None = None, digest: bool | None = None
) -> EmailPrefs:
    """Upsert; never commits."""
    row = session.get(EmailPref, user_id)
    if row is None:
        row = EmailPref(user_id=user_id, alerts=True, digest=True, updated_at=utcnow())
        session.add(row)
    if alerts is not None:
        row.alerts = alerts
    if digest is not None:
        row.digest = digest
    row.updated_at = utcnow()
    session.flush()
    return EmailPrefs(row.alerts, row.digest)
