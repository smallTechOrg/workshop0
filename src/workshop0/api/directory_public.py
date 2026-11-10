"""Phase 13: public trainer directory API (shell; slice R1 fills it)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/public/trainers", tags=["directory"])
