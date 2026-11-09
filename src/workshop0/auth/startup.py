"""Startup validation of the Phase-11 identity settings (filled by slice S1).

Rules (spec/architecture.md §Network identity): an `http://` issuer is allowed only for
localhost/127.0.0.1, and `WORKSHOP0_SESSION_SECRET` is required when sign-in is enabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.workshop0.config.settings import Settings


def validate_settings(settings: Settings) -> None:
    """Raise RuntimeError on an invalid identity configuration. Scaffold stub: no-op."""
    return None
