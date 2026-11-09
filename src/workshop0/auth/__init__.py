"""Network identity (Phase 11) — the swap seam (spec/architecture.md §Network identity).

Product code may import only `auth.deps`. `oidc.py` / `sessions.py` sit behind it so a
central identity service can replace them later without touching product code.
"""
