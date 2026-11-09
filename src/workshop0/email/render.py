"""Template rendering (STUB in Phase 12 Wave A; filled by slice B3)."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


def render(template: str, context: dict[str, Any]) -> Rendered:
    raise NotImplementedError("email.render.render is filled by slice B3")
