"""Review queue API: list pending reviews and decide on them."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from paari.authn.dependencies import get_identity
from paari.review.service import REVIEW, ReviewRecord

_log = logging.getLogger("paari.api.reviews")

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVE | DENY")
    note: str | None = None


class ReviewResponse(BaseModel):
    id: str
    merchant_id: str
    transaction_id: str
    triggered_by: str
    reason: str
    decision: str | None
    decided_by: str | None
    note: str | None
    created_at: str | None = None
    sla_expires_at: str | None = None


def _to_response(record: ReviewRecord) -> ReviewResponse:
    return ReviewResponse(
        id=record.id,
        merchant_id=record.merchant_id,
        transaction_id=record.transaction_id,
        triggered_by=record.triggered_by,
        reason=record.reason,
        decision=record.decision,
        decided_by=record.decided_by,
        note=record.note,
        created_at=record.created_at.isoformat() if record.created_at else None,
        sla_expires_at=record.sla_expires_at.isoformat() if record.sla_expires_at else None,
    )


@router.get("", response_model=list[ReviewResponse])
async def list_reviews(
    merchant_id: str | None = None,
    identity=Depends(get_identity),
) -> list[ReviewResponse]:
    """List pending reviews for the authenticated agent's merchant scope."""
    scope = merchant_id or identity.merchant_scope
    records = await REVIEW.list_pending(merchant_id=scope)
    return [_to_response(r) for r in records]


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(review_id: str, identity=Depends(get_identity)) -> ReviewResponse:
    record = await REVIEW.get(review_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review_not_found")
    return _to_response(record)


@router.post("/{review_id}/decision", response_model=ReviewResponse)
async def decide_review(
    review_id: str,
    body: ReviewDecisionRequest,
    identity=Depends(get_identity),
) -> ReviewResponse:
    """Approve or deny a review (merchant operator action)."""
    if body.decision not in ("APPROVE", "DENY"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_decision")
    record = await REVIEW.decide(
        review_id=review_id,
        decision=body.decision,
        decided_by=identity.agent_id,
        note=body.note,
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review_not_found")
    return _to_response(record)
