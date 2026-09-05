"""Tool invocation router (stub for Step 1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
