"""Outbox drain + senders (STUBS in Phase 12 Wave A; filled by slice B3)."""

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from src.workshop0.db.models import EmailOutbox, NetworkInvite


def schedule_drain(background_tasks: BackgroundTasks) -> None:
    """Schedule `drain()` after the response. Stub no-op."""
    return None


def drain(limit: int = 20) -> int:
    """Claim and send up to `limit` queued rows; returns the number processed. Stub."""
    return 0


def enqueue_invite_email(session: Session, invite: NetworkInvite, base_url: str) -> EmailOutbox:
    """Enqueue one `network.invite` for this invite (B3 checks the 11d state). Stub."""
    raise NotImplementedError("enqueue_invite_email is filled by slice B3")
