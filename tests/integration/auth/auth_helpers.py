"""Helpers for the `/api/auth/*` suite (imported as `auth_helpers`, like `me_helpers`)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select

from tests.support.fake_oidc import authorize_redirect

CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
ADMIN_EMAIL = "admin@example.test"


def reload_settings() -> None:
    import src.workshop0.config.settings as settings_module

    settings_module._settings = None


@dataclass
class SignIn:
    start: object  # httpx.Response of /api/auth/google/start (302 to the issuer)
    callback_url: str  # what the issuer redirected the browser to
    response: object  # httpx.Response of the callback (303)

    @property
    def location(self) -> str:
        return self.response.headers["location"]


def start(client, *, next: str | None = None, invite: str | None = None):  # noqa: A002
    params = {}
    if next is not None:
        params["next"] = next
    if invite is not None:
        params["invite"] = invite
    return client.get("/api/auth/google/start", params=params, follow_redirects=False)


def sign_in(client, email: str, *, next: str | None = None, invite: str | None = None) -> SignIn:  # noqa: A002
    """Browser round-trip: app start → issuer authorize (as `email`) → app callback."""
    started = start(client, next=next, invite=invite)
    assert started.status_code == 302, started.text
    callback_url = authorize_redirect(started.headers["location"], email)
    response = client.get(callback_url, follow_redirects=False)
    return SignIn(start=started, callback_url=callback_url, response=response)


def query_of(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def cookie_header(response, name: str) -> str | None:
    for header in set_cookie_headers(response):
        if header.split("=", 1)[0].strip() == name:
            return header
    return None


def count(model) -> int:
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def rows(model):
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        return list(session.scalars(select(model).order_by(model.id)))
