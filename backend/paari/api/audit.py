"""Audit read router (stub for Step 1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
