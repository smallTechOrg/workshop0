"""Outbox enqueue: insert-only, in the caller's transaction (architecture.md Email)."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.db.models import EmailOutbox


def enqueue(
    session: Session,
    *,
    to: str,
    template: str,
    context: dict[str, Any],
    dedupe_key: str | None = None,
) -> EmailOutbox:
    """Insert one `queued` row and flush (never commits). A repeated `dedupe_key` returns the
    existing row and inserts nothing."""
    if dedupe_key is not None:
        existing = session.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == dedupe_key))
        if existing is not None:
            return existing
    row = EmailOutbox(
        to_email=to.strip(),
        template=template,
        context_json=json.dumps(context, default=str, sort_keys=True),
        status="queued",
        attempts=0,
        dedupe_key=dedupe_key,
    )
    # SAVEPOINT so a concurrent duplicate never poisons the caller's transaction.
    from sqlalchemy.exc import IntegrityError

    try:
        with session.begin_nested():
            session.add(row)
    except IntegrityError:
        existing = session.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == dedupe_key))
        if existing is None:
            raise
        return existing
    return row
