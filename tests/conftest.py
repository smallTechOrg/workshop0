"""Shared fixtures: every test runs against a real PostgreSQL database (harness Rule 5).

`TEST_DATABASE_URL` is REQUIRED (see README "Postgres test setup") and its database
name must end in `_test` — the suite drops/recreates schema `public` there. There is
no SQLite fallback. Schema is built once per session by `alembic upgrade head`; every
test starts from empty tables (TRUNCATE ... RESTART IDENTITY CASCADE) — except the
migration-seeded reference table `topic` (spec/data-model.md §Test-harness consequence):
its rows are captured right after the upgrade and re-inserted (explicit ids, sequence
reset to max(id)) after every TRUNCATE, so each test sees exactly the 40-topic seed.

TEST_ADMIN_KEY is a fixture value owned by this suite (set via env for each test) —
never the operator's real WORKSHOP0_ADMIN_KEY from .env.
"""

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_ADMIN_KEY = "test-admin-key-0123456789"


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL is not set. The suite runs on PostgreSQL only (no SQLite "
            "fallback). See README.md 'Postgres test setup': createdb workshop0_test && "
            'export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"',
            returncode=4,
        )
    parsed = make_url(url)
    if not parsed.drivername.startswith("postgresql"):
        pytest.exit(
            f"TEST_DATABASE_URL must be a PostgreSQL URL (got driver {parsed.drivername!r}). "
            "See README.md 'Postgres test setup'.",
            returncode=4,
        )
    if not (parsed.database or "").endswith("_test"):
        pytest.exit(
            f"Refusing to run: TEST_DATABASE_URL database {parsed.database!r} does not end "
            "in '_test' (the suite drops schema public). See README.md 'Postgres test setup'.",
            returncode=4,
        )
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _require_test_database_url()


def _reset_singletons() -> None:
    import src.workshop0.config.settings as settings_module
    from src.workshop0.db.session import reset_db_state

    settings_module._settings = None
    reset_db_state()


def alembic_upgrade(url: str, revision: str = "head") -> None:
    """Run alembic against `url` (env.py reads DATABASE_URL via settings)."""
    _alembic_run("upgrade", url, revision)


def alembic_downgrade(url: str, revision: str = "base") -> None:
    _alembic_run("downgrade", url, revision)


def _alembic_run(action: str, url: str, revision: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import src.workshop0.config.settings as settings_module

    root = Path(__file__).resolve().parents[1]
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    settings_module._settings = None
    try:
        getattr(command, action)(Config(str(root / "alembic.ini")), revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        settings_module._settings = None


@pytest.fixture(scope="session", autouse=True)
def _schema(test_database_url):
    """Drop + recreate schema public, then `alembic upgrade head` — once per session."""
    engine = create_engine(test_database_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    alembic_upgrade(test_database_url)
    yield


@pytest.fixture(scope="session")
def _truncate_engine(test_database_url):
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


REFERENCE_TABLES = ("topic",)  # migration-seeded; restored after every TRUNCATE


@pytest.fixture(scope="session")
def _reference_rows(_schema, _truncate_engine) -> dict[str, list[dict]]:
    """Captured once, right after `alembic upgrade head` (before any test writes)."""
    from src.workshop0.db.models import Base

    captured: dict[str, list[dict]] = {}
    with _truncate_engine.connect() as connection:
        for name in REFERENCE_TABLES:
            table = Base.metadata.tables[name]
            captured[name] = [
                dict(row._mapping)
                for row in connection.execute(table.select().order_by(table.c.id))
            ]
    return captured


def restore_reference_rows(connection, reference_rows: dict[str, list[dict]]) -> None:
    from src.workshop0.db.models import Base

    for name, rows in reference_rows.items():
        table = Base.metadata.tables[name]
        if rows:
            connection.execute(table.insert(), rows)
        connection.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('\"{name}\"', 'id'), "
                f'COALESCE(max(id), 1), max(id) IS NOT NULL) FROM "{name}"'
            )
        )


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, test_database_url, _schema, _truncate_engine, _reference_rows):
    from src.workshop0.db.models import Base

    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with _truncate_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        restore_reference_rows(connection, _reference_rows)
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("WORKSHOP0_ADMIN_KEY", TEST_ADMIN_KEY)
    monkeypatch.setenv("WORKSHOP0_BASE_URL", "")
    monkeypatch.setenv("WORKSHOP0_LOG_LEVEL", "WARNING")
    _reset_singletons()
    yield
    _reset_singletons()


@pytest.fixture
def scratch_database(test_database_url):
    """Factory: create an empty `<name>_mig_<uuid>` database on the same server; dropped at teardown."""
    created: list[str] = []
    base = make_url(test_database_url)
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")

    def _create() -> str:
        name = f"{base.database}_mig_{uuid.uuid4().hex[:8]}"
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created.append(name)
        return base.set(database=name).render_as_string(hide_password=False)

    yield _create
    import src.workshop0.config.settings as settings_module
    from src.workshop0.db.session import reset_db_state

    settings_module._settings = None
    reset_db_state()
    with admin.connect() as connection:
        for name in created:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def make_app():
    """Build a fresh app over the CURRENT env (schema comes from alembic, once per session)."""

    def _make():
        from src.workshop0.api import create_app
        return create_app()

    return _make


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def make_client(app):
    """Fresh cookie jars over the same app — one per simulated browser/device."""

    def _make():
        return TestClient(app)

    return _make


@pytest.fixture
def admin_headers():
    return {"X-Admin-Key": TEST_ADMIN_KEY}


WORKSHOP_BODY = {
    "name": "LangGraph Lab — July",
    "description_md": "Welcome! Bring a laptop.",
    "milestones": [
        {"title": "Set up your environment", "content_md": "```bash\nuv sync\n```", "minutes": 30},
        {"title": "Configure the API key", "content_md": "Put it in `.env`.", "minutes": 15},
        {"title": "Run the first graph", "content_md": "Now run it.", "minutes": None},
    ],
}


@pytest.fixture
def workshop(client, admin_headers):
    response = client.post("/api/admin/workshops", json=WORKSHOP_BODY, headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["workshop"]


@pytest.fixture
def join_participant():
    def _join(client_, join_slug: str, name: str) -> dict:
        response = client_.post(f"/api/join/{join_slug}", json={"name": name})
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return _join


# --------------------------------------------------------------------------- Phase 10 board

INTERNAL_PARTNER_SENTINEL = "ZZ-INTERNAL-PARTNER-7f3a"
INTERNAL_NOTE_SENTINEL = "ZZ-INTERNAL-NOTE-9c1d"
BOARD_TYPES = ("workshop", "engagement", "role", "cofacilitation")
BOARD_TOPICS = ("python", "generative-ai", "kubernetes", "react", "aws", "ux-design")


def iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def opportunity_body(topic_ids: list[int], /, **overrides) -> dict:
    """A valid POST /api/admin/opportunities body (draft, remote, deadline +10 days)."""
    body = {
        "title": "GenAI for product teams — 2-day workshop",
        "type": "workshop",
        "summary": "Hands-on LLM workshop for 30 PMs in Bengaluru.",
        "description_md": "## Agenda\n\n- Prompting\n- Evals\n\n```python\nprint('hi')\n```",
        "topic_ids": topic_ids,
        "location_mode": "remote",
        "deadline": iso(datetime.now(timezone.utc) + timedelta(days=10)),
        "partner_display_name": "A Bengaluru fintech",
        "partner_internal_name": "Acme Payments Pvt Ltd",
        "internal_notes": "Contact: R. Rao",
        "status": "draft",
    }
    body.update(overrides)
    return body


@pytest.fixture
def topic_ids(client, admin_headers) -> dict[str, int]:
    """slug -> id for every topic (seeded + any added so far)."""
    response = client.get("/api/admin/topics", headers=admin_headers)
    assert response.status_code == 200, response.text
    return {t["slug"]: t["id"] for t in response.json()["data"]["topics"]}


@pytest.fixture
def create_opportunity(client, admin_headers, topic_ids):
    """Factory: POST a listing through the real admin API; returns the AdminOpportunity."""

    def _create(slugs: tuple[str, ...] | list[str] = ("generative-ai",), **overrides) -> dict:
        body = opportunity_body([topic_ids[s] for s in slugs], **overrides)
        response = client.post("/api/admin/opportunities", json=body, headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]["opportunity"]

    return _create


def db_execute(sql: str, **params) -> None:
    """Direct DB write for states the API refuses to create (e.g. a deadline in the past)."""
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        session.execute(text(sql), params)


@pytest.fixture
def board(create_opportunity, client, admin_headers):
    """30 open listings (all 4 types, 6 topics, distinct published_at and deadlines)
    + 3 drafts + 3 closed + 3 expired; every listing carries both internal sentinels.

    Returns the id sets the board tests assert against."""
    now = datetime.now(timezone.utc)
    secret = {
        "partner_internal_name": INTERNAL_PARTNER_SENTINEL,
        "internal_notes": INTERNAL_NOTE_SENTINEL,
    }
    open_ids: list[int] = []
    by_type: dict[str, set[int]] = {t: set() for t in BOARD_TYPES}
    by_topic: dict[str, set[int]] = {t: set() for t in BOARD_TOPICS}
    for i in range(30):
        slugs = [BOARD_TOPICS[i % 6]]
        if i % 3 == 0:
            slugs.append(BOARD_TOPICS[(i + 1) % 6])
        kind = BOARD_TYPES[i % 4]
        location = {"location_mode": "onsite", "city": "Pune"} if i % 5 == 0 else {}
        opp = create_opportunity(
            slugs,
            title=f"Open listing {i:02d}",
            type=kind,
            status="open",
            deadline=iso(now + timedelta(days=i + 1)),
            **location,
            **secret,
        )
        open_ids.append(opp["id"])
        by_type[kind].add(opp["id"])
        for slug in slugs:
            by_topic[slug].add(opp["id"])
        # distinct, deliberately not id-ordered publish times: (i*7) mod 30 hours ago
        db_execute(
            "UPDATE opportunity SET published_at = :p WHERE id = :id",
            p=now - timedelta(hours=(i * 7) % 30, minutes=1),
            id=opp["id"],
        )
    draft_ids = [
        create_opportunity(["python"], title=f"Draft {i}", type="role", **secret)["id"]
        for i in range(3)
    ]
    closed_ids = []
    for i in range(3):
        opp = create_opportunity(["python"], title=f"Closed {i}", type="workshop", status="open", **secret)
        response = client.patch(
            f"/api/admin/opportunities/{opp['id']}", json={"status": "closed"}, headers=admin_headers
        )
        assert response.status_code == 200, response.text
        closed_ids.append(opp["id"])
    expired_ids = []
    for i in range(3):
        opp = create_opportunity(["python"], title=f"Expired {i}", type="engagement", status="open", **secret)
        db_execute(
            "UPDATE opportunity SET deadline = :d WHERE id = :id",
            d=now - timedelta(hours=i + 1),
            id=opp["id"],
        )
        expired_ids.append(opp["id"])
    return {
        "open_ids": open_ids,
        "draft_ids": draft_ids,
        "closed_ids": closed_ids,
        "expired_ids": expired_ids,
        "by_type": by_type,
        "by_topic": by_topic,
    }


# --------------------------------------------------------------------------- Phase 11 network

SESSION_COOKIE = "workshop0_session"  # spec/architecture.md §Network identity → Cookies
NETWORK_HEADERS = {"X-Requested-With": "workshop0"}  # CSRF header for cookie-auth mutations
SESSION_LIFETIME = timedelta(days=30)


@dataclass(frozen=True)
class NetworkUser:
    """What `make_user` returns (a plain value — no live ORM session attached)."""

    id: int
    email: str
    display_name: str
    is_admin: bool


@pytest.fixture
def make_user(monkeypatch):
    """Factory `make_user(email, admin=False) -> NetworkUser`: inserts a verified,
    OIDC-linked `app_user` row. `admin=True` adds the email to WORKSHOP0_ADMIN_EMAILS
    for this test (admin-ness is derived from the setting, never stored)."""

    def _make(email: str, admin: bool = False) -> NetworkUser:
        from src.workshop0.db.models import AppUser
        from src.workshop0.db.session import create_db_session

        email = email.strip().lower()
        display_name = email.split("@", 1)[0]
        with create_db_session() as session:
            user = AppUser(
                email=email,
                email_verified=True,
                display_name=display_name,
                oidc_issuer="https://accounts.google.com",
                oidc_subject=f"sub-{uuid.uuid4().hex}",
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            session.flush()
            user_id = user.id
        if admin:
            import src.workshop0.config.settings as settings_module

            current = [e for e in os.environ.get("WORKSHOP0_ADMIN_EMAILS", "").split(",") if e.strip()]
            if email not in current:
                current.append(email)
            monkeypatch.setenv("WORKSHOP0_ADMIN_EMAILS", ",".join(current))
            settings_module._settings = None
        return NetworkUser(id=user_id, email=email, display_name=display_name, is_admin=admin)

    return _make


def create_session_token(user_id: int, *, expires_at: datetime | None = None) -> str:
    """Insert an `auth_session` row (SHA-256 hex of the raw token stored, never the token)
    and return the raw cookie value."""
    from src.workshop0.db.models import AuthSession
    from src.workshop0.db.session import create_db_session

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with create_db_session() as session:
        session.add(
            AuthSession(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user_id,
                created_at=now,
                expires_at=expires_at or now + SESSION_LIFETIME,
                last_seen_at=now,
                user_agent="pytest",
            )
        )
    return token


@pytest.fixture
def signed_in_client(app):
    """Factory `signed_in_client(user, *, csrf=True) -> TestClient`: a fresh cookie jar
    over the test app with a real `auth_session` row and the `workshop0_session` cookie —
    the sign-in shortcut for non-auth tests. `csrf=True` also sends
    `X-Requested-With: workshop0` on every request; pass `csrf=False` to test the CSRF guard."""

    def _make(user, *, csrf: bool = True) -> TestClient:
        user_id = user.id if hasattr(user, "id") else int(user["id"])
        client_ = TestClient(app)
        client_.cookies.set(SESSION_COOKIE, create_session_token(user_id))
        if csrf:
            client_.headers.update(NETWORK_HEADERS)
        return client_

    return _make


@pytest.fixture
def network_ai_disabled(monkeypatch):
    """Factory `network_ai_disabled(which="key"|"workspace")`: blanks ANTHROPIC_API_KEY
    or ANTHROPIC_WORKSPACE_ID for this test and drops the cached Anthropic client. The ONLY
    sanctioned keyless switch — `.env` holds real keys."""

    def _disable(which: str = "key") -> None:
        fields = {"key": "anthropic_api_key", "workspace": "anthropic_workspace_id"}
        if which not in fields:
            raise ValueError(f"which must be 'key' or 'workspace', got {which!r}")
        field = fields[which]
        from src.workshop0.ai import anthropic_client
        from src.workshop0.config.settings import get_settings

        # env wins over .env if settings are rebuilt mid-test; setattr covers the live instance
        monkeypatch.setenv(field.upper(), "")
        monkeypatch.setattr(get_settings(), field, "")
        anthropic_client.reset_client()

    yield _disable
    from src.workshop0.ai import anthropic_client

    anthropic_client.reset_client()
