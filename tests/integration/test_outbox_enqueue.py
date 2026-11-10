"""email.outbox.enqueue: insert-only in the caller's transaction, dedupe by key."""

import json

from sqlalchemy import func, select

from src.workshop0.db.models import EmailOutbox
from src.workshop0.db.session import create_db_session
from src.workshop0.email.outbox import enqueue


def test_enqueue_inserts_queued_row_and_dedupes():
    with create_db_session() as session:
        first = enqueue(session, to="a@example.test", template="network.welcome", context={"n": 1}, dedupe_key="k1")
        again = enqueue(session, to="a@example.test", template="network.welcome", context={"n": 2}, dedupe_key="k1")
        none1 = enqueue(session, to="b@example.test", template="network.welcome", context={})
        none2 = enqueue(session, to="b@example.test", template="network.welcome", context={})
        assert again.id == first.id
        assert none1.id != none2.id  # no key => never deduped
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(EmailOutbox)) == 3
        row = session.scalar(select(EmailOutbox).where(EmailOutbox.dedupe_key == "k1"))
        assert (row.status, row.attempts, json.loads(row.context_json)) == ("queued", 0, {"n": 1})


def test_enqueue_rolls_back_with_the_callers_transaction():
    try:
        with create_db_session() as session:
            enqueue(session, to="a@example.test", template="t", context={}, dedupe_key="k2")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(EmailOutbox)) == 0
