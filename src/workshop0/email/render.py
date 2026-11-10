"""Template rendering: `templates/<name>.txt` (subject = first line) + `.html`, one footer."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEMPLATES = (
    "network.welcome",
    "network.invite",
    "opportunity.invite",
    "application.received",
    "application.status_changed",
    "network.alert",
    "network.digest",
)
FOOTER = "You received this email because of your activity on Workshop0."
_DIR = Path(__file__).parent / "templates"
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_SECTION = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
_STATUS_LABELS = {
    "applied": "Applied",
    "shortlisted": "Shortlisted",
    "selected": "Selected",
    "not_selected": "Not selected",
    "withdrawn": "Withdrawn",
}


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str


def _value(context: dict[str, Any], key: str) -> str:
    if key == "status_label" and "status_label" not in context:
        status = str(context.get("status", ""))
        return _STATUS_LABELS.get(status, status.replace("_", " ").capitalize())
    val = context.get(key)
    if key == "name" and not val:
        return "there"
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return ", ".join(str(v) for v in val)
    return str(val)


def _expand(markup: str, context: dict[str, Any], escape: bool) -> str:
    """Expand `{{#key}}..{{/key}}` then `{{var}}`.

    A list value repeats the body once per item (items are flat dicts; inner variables
    resolve from the item first, then the outer context). A truthy scalar renders the
    body once, a falsy or missing value renders nothing. Nested sections are not supported.
    """

    def fmt(ctx: dict[str, Any]):
        def sub(m: re.Match[str]) -> str:
            v = _value(ctx, m.group(1))
            return html.escape(v, quote=True) if escape else v

        return sub

    def section(m: re.Match[str]) -> str:
        val = context.get(m.group(1))
        body = m.group(2)
        if isinstance(val, (list, tuple)):
            out = []
            for item in val:
                if not isinstance(item, dict):
                    continue
                merged = {**context, **item}
                out.append(_VAR.sub(fmt(merged), body))
            return "".join(out)
        return _VAR.sub(fmt(context), body) if val else ""

    return _VAR.sub(fmt(context), _SECTION.sub(section, markup))


def render(template: str, context: dict[str, Any]) -> Rendered:
    if template not in TEMPLATES:
        raise ValueError(f"unknown email template: {template}")
    txt = (_DIR / f"{template}.txt").read_text(encoding="utf-8")
    markup = (_DIR / f"{template}.html").read_text(encoding="utf-8")
    plain = _expand(txt, context, escape=False)
    subject, _, body = plain.partition("\n")
    subject = " ".join(subject.split())[:200]
    html_body = _expand(markup, context, escape=True)
    text = f"{body.strip()}\n\n--\n{FOOTER}\n"
    page = (
        "<!doctype html><html><body>"
        f"{html_body.strip()}\n<hr><p><small>{html.escape(FOOTER)}</small></p></body></html>"
    )
    return Rendered(subject=subject, text=text, html=page)
