"""`/api/admin/outbox` - shell registered in Phase 12 Wave A; routes filled by slice B3."""

from fastapi import APIRouter, Depends

from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin/outbox", dependencies=[Depends(require_admin_key)])
