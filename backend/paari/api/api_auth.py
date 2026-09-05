"""Thin /api shims for frontend — prose-safe, no logic changes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from paari.authn.jwt_verifier import TokenVerificationError, verify_token

router = APIRouter(prefix="/api/auth", tags=["api-auth"])


class ApiTokenRequest(BaseModel):
    agent_type: str = Field(..., description="buyer | merchant")
    agent_id: str = Field(..., description="BA-001 | MA-001 etc")
    credentials: dict | None = None


def _seeded_to_jwt_agent(agent_type: str, agent_id: str) -> tuple[str, str]:
    t = agent_type.lower()
    if t == "buyer":
        return "buyer-agent-001", "buyer"
    if t == "merchant":
        return "merchant-agent-001", "merchant"
    if agent_id in ("BA-001", "buyer-agent-001"):
        return "buyer-agent-001", "buyer"
    if agent_id in ("MA-001", "merchant-agent-001"):
        return "merchant-agent-001", "merchant"
    return agent_id, t


@router.post("/agent-token")
async def api_agent_token(req: ApiTokenRequest) -> dict:
    from paari.api.auth import _SEEDED_AGENTS
    from paari.authn.jwt_issuer import issue_agent_token
    from paari.authn.jwt_verifier import verify_token as vt
    from paari.config import settings

    jwt_id, role = _seeded_to_jwt_agent(req.agent_type, req.agent_id)
    seeded = _SEEDED_AGENTS.get(jwt_id)
    if seeded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_agent_id")
    token = issue_agent_token(
        agent_id=jwt_id,
        agent_type=seeded["agent_type"],
        capabilities=seeded["capabilities"],
        merchant_scope=seeded.get("merchant_scope"),
        policy_version="v1",
    )
    ident = vt(token)
    mapped_role = (
        "buyer"
        if ident.agent_type.value == "BUYER"
        else "merchant"
        if ident.agent_type.value == "MERCHANT"
        else ident.agent_type.value.lower()
    )
    if mapped_role == "merchant" and jwt_id.startswith("buyer"):
        mapped_role = "buyer"
    label = (
        "Buyer AI"
        if mapped_role == "buyer"
        else "Merchant AI"
        if mapped_role == "merchant"
        else ident.agent_id
    )
    if role == "operator":
        mapped_role = "operator"
        label = "Operator"
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_seconds,
        "agent": {"agent_id": req.agent_id, "role": mapped_role, "label": label},
    }


@router.get("/me")
async def api_me(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        ident = verify_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    raw_role = ident.agent_type.value.lower()
    role = "buyer" if raw_role == "buyer" else "merchant" if raw_role == "merchant" else raw_role
    label = (
        "Buyer AI" if role == "buyer" else "Merchant AI" if role == "merchant" else ident.agent_id
    )
    return {"agent": {"agent_id": ident.agent_id, "role": role, "label": label}}
