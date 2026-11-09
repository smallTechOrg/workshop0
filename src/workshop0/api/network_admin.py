"""`/api/admin/network/*` — the admin trainer pool (spec/api.md §Phase 11).

Router shell registered by the Phase-11 shared scaffold; slice S8 (pool-api) adds the endpoints.
"""

from fastapi import APIRouter, Depends

from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin/network", dependencies=[Depends(require_admin_key)])
