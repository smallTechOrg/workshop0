"""`/api/admin/opportunities/{id}/applications...` - shell (Wave A); routes filled by slice B1."""

from fastapi import APIRouter, Depends

from src.workshop0.security import require_admin_key

router = APIRouter(prefix="/api/admin/opportunities", dependencies=[Depends(require_admin_key)])
