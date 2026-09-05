"""Demo token endpoint: issues a JWT for the seeded buyer or merchant agent."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from paari.authn.jwt_issuer import issue_agent_token
from paari.authn.jwt_verifier import verify_token
from paari.authn.revocation import revoke
from paari.config import settings
from paari.schemas.capability import Capability
from paari.schemas.identity import AgentType

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    agent_id: str = Field(..., description="Seeded agent id, e.g. buyer-agent-001")
    merchant_scope: str | None = None
    policy_version: str = "v1"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


# Seeded agent -> capabilities mapping (demo only; production loads from DB).
_SEEDED_AGENTS: dict[str, dict] = {
    "buyer-agent-001": {
        "agent_type": AgentType.BUYER,
        "capabilities": [
            Capability.CATALOG_READ,
            Capability.INVENTORY_READ,
            Capability.PRODUCT_READ,
            Capability.QUOTE_CREATE,
            Capability.DEAL_NEGOTIATE,
            Capability.PAYMENT_REQUEST,
        ],
        "merchant_scope": None,
    },
    "merchant-agent-001": {
        "agent_type": AgentType.MERCHANT,
        "capabilities": [
            Capability.QUOTE_RESPOND,
            Capability.ORDER_READ,
            Capability.REVIEW_READ,
        ],
        "merchant_scope": "merchant-demo-001",
    },
}


@router.post("/agent-token", response_model=TokenResponse)
async def issue_token(request: TokenRequest) -> TokenResponse:
    """Issue a short-lived agent JWT (demo helper)."""
    seeded = _SEEDED_AGENTS.get(request.agent_id)
    if seeded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_agent_id")
    if request.merchant_scope is not None and seeded.get("merchant_scope") != request.merchant_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="merchant_scope_mismatch")
    token = issue_agent_token(
        agent_id=request.agent_id,
        agent_type=seeded["agent_type"],
        capabilities=seeded["capabilities"],
        merchant_scope=request.merchant_scope,
        policy_version=request.policy_version,
    )
    identity = verify_token(token)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_seconds)


@router.post("/revoke")
async def revoke_token(authorization: str | None = None) -> dict:
    """Revoke the presented token (demo helper)."""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_authorization")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="malformed_authorization")
    # Decode without verifying to fetch jti (revocation endpoint is unauthenticated).
    import jwt as _jwt

    decoded = _jwt.decode(parts[1].strip(), options={"verify_signature": False, "verify_exp": False})
    jti = decoded.get("jti")
    if not jti:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no_jti")
    revoke(jti, expires_at=decoded.get("exp"))
    return {"revoked": True, "jti": jti}
