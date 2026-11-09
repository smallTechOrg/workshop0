"""Admin partner list surface — spec/api.md §Phase 11b. Shell; F2 fills it."""

from fastapi import APIRouter, Depends

from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])
