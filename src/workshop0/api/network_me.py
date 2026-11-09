"""`/api/me/*` — trainer self-service: CV, draft, profile, deletion (spec/api.md §Phase 11).

Router shell registered by the Phase-11 shared scaffold; slice S7 (me-api) adds the endpoints
(each guarded by `auth.deps.require_user`).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/me")
