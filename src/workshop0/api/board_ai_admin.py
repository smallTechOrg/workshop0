"""Admin opportunity paste-to-fill drafting — spec/api.md §Phase 11b. Shell; F4 fills it."""

from fastapi import APIRouter, Depends

from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])
