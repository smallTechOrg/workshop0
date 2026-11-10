"""Phase 13: `/api/email/unsubscribe` and `/api/cron/weekly-digest` (shell; slice D1 fills it)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["network-public"])
