"""Mandate API router.

Endpoints:
- POST /mandates/enroll — Register a pre-authorized payment mandate
- GET /mandates/{mandate_id} — Get mandate details with today's usage
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from paari.audit.logger import AUDIT
from paari.db.engine import get_session_maker
from paari.schemas.audit import AuditDecision

_log = logging.getLogger("paari.mandates")
router = APIRouter(prefix="/mandates", tags=["mandates"])


class EnrollMandateRequest(BaseModel):
    """Register a pre-authorized payment mandate (human-consent step).

    Only an opaque instrument reference is stored — never raw credentials.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="User UUID or display_id")
    provider: str = Field(default="RAZORPAY", description="Payment provider")
    instrument_reference: str = Field(..., description="Opaque provider reference, max 128 chars")
    max_per_transaction: int = Field(..., gt=0, description="Per-transaction cap in paise")
    daily_limit: int = Field(..., gt=0, description="Daily cap in paise")
    allowed_merchants: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(default_factory=list)
    requires_review_above: int = Field(default=0, ge=0)
    expires_at: str | None = Field(default=None)


class EnrollMandateResponse(BaseModel):
    """Response with the created mandate."""

    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    display_id: str
    status: str


class MandateDetailResponse(BaseModel):
    """Mandate details with today's usage."""

    model_config = ConfigDict(extra="forbid")

    mandate_id: str
    display_id: str
    user_id: str
    provider: str
    status: str
    max_per_transaction: int
    daily_limit: int
    allowed_merchants: list[str]
    autonomous_enabled: bool
    requires_review_above: int
    used_today_paise: int
    expires_at: str | None = None


@router.post("/enroll", response_model=EnrollMandateResponse)
async def enroll_mandate(req: EnrollMandateRequest) -> EnrollMandateResponse:
    """Register a mandate after human consent + provider enrollment."""
    from datetime import UTC, datetime

    if req.max_per_transaction > req.daily_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="max_exceeds_daily_limit"
        )
    if len(req.instrument_reference) > 128 or not req.instrument_reference.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_instrument_reference"
        )
    if req.expires_at:
        try:
            expiry = datetime.fromisoformat(req.expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if expiry <= datetime.now(UTC):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="expiry_in_past"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_expiry"
            ) from None

    maker = get_session_maker()
    async with maker() as session:
        user = (
            await session.execute(
                text("SELECT id FROM users WHERE id=:x OR display_id=:x"), {"x": req.user_id}
            )
        ).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
        mandate_id = uuid.uuid4().hex
        display_id = f"MAND-{uuid.uuid4().hex[:6].upper()}"
        await session.execute(
            text(
                "INSERT INTO mandates (id, display_id, user_id, provider, instrument_reference, status, "
                " max_per_transaction, daily_limit, allowed_merchants_json, allowed_categories_json, "
                " autonomous_enabled, requires_review_above, expires_at) "
                "VALUES (:id, :d, :u, :p, :ref, 'ACTIVE', :max_tx, :daily, :merchants, :categories, 1,"
                " :review, :exp)"
            ),
            {
                "id": mandate_id,
                "d": display_id,
                "u": user.id,
                "p": req.provider,
                "ref": req.instrument_reference.strip(),
                "max_tx": req.max_per_transaction,
                "daily": req.daily_limit,
                "merchants": json.dumps(req.allowed_merchants),
                "categories": json.dumps(req.allowed_categories),
                "review": req.requires_review_above,
                "exp": req.expires_at,
            },
        )
        await session.commit()
        # Blueprint Phase 13: the mandate itself is audited. The row is
        # inserted directly ACTIVE, so MANDATE_CREATED also records the
        # activation (no separate MANDATE_ACTIVATED step exists yet).
        await AUDIT.log(
            request_id=str(uuid.uuid4()),
            action="MANDATE_CREATED",
            decision=AuditDecision.ALLOW,
            payload={
                "mandate_id": display_id,
                "user_id": req.user_id,
                "provider": req.provider,
                "status": "ACTIVE",
                "max_per_transaction_paise": req.max_per_transaction,
                "daily_limit_paise": req.daily_limit,
                "requires_review_above_paise": req.requires_review_above,
                "allowed_merchants": req.allowed_merchants,
                "allowed_categories": req.allowed_categories,
            },
        )
        _log.info("Mandate enrolled: %s for user %s", display_id, req.user_id)
        return EnrollMandateResponse(mandate_id=mandate_id, display_id=display_id, status="ACTIVE")


@router.get("/{mandate_id}", response_model=MandateDetailResponse)
async def get_mandate(mandate_id: str) -> MandateDetailResponse:
    """Get mandate details with today's usage."""
    from datetime import UTC, datetime

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, display_id, user_id, provider, status, max_per_transaction, daily_limit, "
                    " allowed_merchants_json, autonomous_enabled, requires_review_above, expires_at "
                    "FROM mandates WHERE id=:x OR display_id=:x"
                ),
                {"x": mandate_id},
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mandate_not_found")
        usage = (
            await session.execute(
                text("SELECT used_paise FROM mandate_daily_usage WHERE mandate_id=:m AND day=:d"),
                {"m": row.id, "d": datetime.now(UTC).strftime("%Y-%m-%d")},
            )
        ).first()
        return MandateDetailResponse(
            mandate_id=row.id,
            display_id=row.display_id or row.id,
            user_id=row.user_id,
            provider=row.provider,
            status=row.status,
            max_per_transaction=int(row.max_per_transaction),
            daily_limit=int(row.daily_limit),
            allowed_merchants=json.loads(row.allowed_merchants_json or "[]"),
            autonomous_enabled=bool(row.autonomous_enabled),
            requires_review_above=int(row.requires_review_above or 0),
            used_today_paise=int(usage.used_paise) if usage else 0,
            expires_at=row.expires_at,
        )
