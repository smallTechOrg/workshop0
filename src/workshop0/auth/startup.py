"""Startup validation of the Phase-11 identity settings.

Rules (spec/architecture.md §Network identity / §Environment variables):
- `WORKSHOP0_OIDC_ISSUER` must be an absolute `https://` URL; `http://` is allowed **only**
  for `localhost` / `127.0.0.1` (the local test issuer). Checked whether or not sign-in is
  enabled, so a typo surfaces before anyone configures the Google client.
- Sign-in is enabled when both `WORKSHOP0_GOOGLE_CLIENT_ID` and
  `WORKSHOP0_GOOGLE_CLIENT_SECRET` are set; then `WORKSHOP0_SESSION_SECRET` is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from src.workshop0.config.settings import Settings

LOCAL_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1"})


def signin_enabled(settings: Settings) -> bool:
    return bool(
        settings.workshop0_google_client_id.strip()
        and settings.workshop0_google_client_secret.strip()
    )


def _validate_issuer(issuer: str) -> None:
    parts = urlsplit(issuer.strip())
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise RuntimeError(
            f"WORKSHOP0_OIDC_ISSUER must be an absolute https:// URL (got {issuer!r}); "
            "the default is https://accounts.google.com."
        )
    if parts.query or parts.fragment:
        raise RuntimeError("WORKSHOP0_OIDC_ISSUER must not carry a query string or fragment.")
    if parts.scheme == "http" and parts.hostname not in LOCAL_HTTP_HOSTS:
        raise RuntimeError(
            f"WORKSHOP0_OIDC_ISSUER {issuer!r} uses http://, which is allowed only for "
            "localhost/127.0.0.1 (the local test issuer). Use an https:// issuer."
        )


def validate_settings(settings: Settings) -> None:
    """Raise RuntimeError on an invalid identity configuration."""
    _validate_issuer(settings.workshop0_oidc_issuer)
    if signin_enabled(settings) and not settings.workshop0_session_secret.strip():
        raise RuntimeError(
            "WORKSHOP0_SESSION_SECRET is required when Google sign-in is enabled "
            "(WORKSHOP0_GOOGLE_CLIENT_ID and _SECRET are set). Generate one with "
            "`openssl rand -hex 32` and add it to .env."
        )
