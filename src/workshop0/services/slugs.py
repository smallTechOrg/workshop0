"""Opportunity slug rule (spec/data-model.md §Phase 11e → Slug rule).

This is the ONE implementation used by the app. Migration `0010` carries a frozen copy
(no app imports). A slug is `f"{base}-{suffix}"`: it always contains a `-` and a
non-digit, so it can never collide with a legacy numeric id (`^\\d{1,12}$`).
"""

import re
import secrets
import unicodedata
from collections.abc import Callable

BASE_MAX = 60
FALLBACK_BASE = "opportunity"
SUFFIX_BYTES = 2  # 4 hex characters
LONG_SUFFIX_BYTES = 3  # 6 hex characters, after MAX_SHORT_COLLISIONS collisions
MAX_SHORT_COLLISIONS = 5

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slug_base(title: str, first_city: str | None) -> str:
    """NFKD → drop non-ASCII → lower → runs of non-[a-z0-9] → '-' → trim → cut at 60
    on a word boundary → trim. Empty → 'opportunity'."""
    raw = f"{title} {first_city}" if first_city else title
    ascii_only = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    base = _NON_ALNUM.sub("-", ascii_only.lower()).strip("-")
    if len(base) > BASE_MAX:
        cut = base[:BASE_MAX]
        if base[BASE_MAX] != "-" and "-" in cut:  # the cut fell inside a word
            cut = cut[: cut.rindex("-")]
        base = cut.strip("-")
    return base or FALLBACK_BASE


def new_suffix(nbytes: int = SUFFIX_BYTES) -> str:
    """Lower-case hex from a cryptographically secure source."""
    return secrets.token_hex(nbytes)


def split_suffix(slug: str) -> tuple[str, str]:
    """`genai-workshop-a3f9` → (`genai-workshop`, `a3f9`)."""
    base, _, suffix = slug.rpartition("-")
    return base, suffix


def make_unique_slug(
    base: str,
    exists: Callable[[str], bool],
    *,
    suffix_source: Callable[[int], str] | None = None,
) -> str:
    """Draw suffixes until `exists(slug)` is False; after 5 collisions use 6 hex chars."""
    draw = suffix_source or new_suffix
    collisions = 0
    while True:
        nbytes = SUFFIX_BYTES if collisions < MAX_SHORT_COLLISIONS else LONG_SUFFIX_BYTES
        candidate = f"{base}-{draw(nbytes)}"
        if not exists(candidate):
            return candidate
        collisions += 1
