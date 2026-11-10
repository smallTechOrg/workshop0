"""Phase 13: signed unsubscribe tokens (itsdangerous, no expiry, salt `workshop0.unsubscribe`)."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from itsdangerous import BadData, URLSafeSerializer

from src.workshop0.config.settings import get_settings

SALT = "workshop0.unsubscribe"
KINDS = ("alerts", "digest")


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().workshop0_session_secret, salt=SALT)


def make_token(user_id: int, kind: Literal["alerts", "digest"]) -> str:
    if kind not in KINDS:
        raise ValueError("unknown unsubscribe kind")
    return _serializer().dumps([int(user_id), kind])


def read_token(token: str) -> tuple[int, str]:
    """Raises ValueError on a malformed, tampered or wrong-secret token."""
    if not get_settings().workshop0_session_secret.strip():
        raise ValueError("no session secret configured")
    try:
        payload = _serializer().loads(token)
    except (BadData, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("invalid unsubscribe token") from exc
    if (
        not isinstance(payload, list)
        or len(payload) != 2
        or isinstance(payload[0], bool)
        or not isinstance(payload[0], int)
        or payload[1] not in KINDS
    ):
        raise ValueError("invalid unsubscribe token")
    return payload[0], payload[1]


def url(base_url: str, user_id: int, kind: str) -> str:
    return f"{base_url.rstrip('/')}/api/email/unsubscribe?t={quote(make_token(user_id, kind), safe='')}"  # type: ignore[arg-type]
