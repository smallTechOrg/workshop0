"""`/api/auth/*` — sign-in config, Google OIDC start/callback, me, sign-out (spec/api.md §Phase 11).

Router shell registered by the Phase-11 shared scaffold; slice S1 (auth) adds the endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/auth")
