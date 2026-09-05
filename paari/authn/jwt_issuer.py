"""Issue short-lived RS256 agent JWTs."""

from __future__ import annotations

import time
import uuid

import jwt

from paari.authn.jwks import get_private_key
from paari.config import settings
from paari.schemas.capability import Capability
from paari.schemas.identity import AgentType


def issue_agent_token(
    *,
    agent_id: str,
    agent_type: AgentType,
    capabilities: list[Capability | str],
    merchant_scope: str | None = None,
    policy_version: str = "v1",
    expire_seconds: int | None = None,
) -> str:
    """Issue a short-lived RS256 JWT for an agent.

    The token carries the agent's capabilities and policy version. Revocation
    is via short expiry + a revocation list checked on every request.
    """
    now = int(time.time())
    expiry = expire_seconds if expire_seconds is not None else settings.jwt_expire_seconds
    caps = [c.value if isinstance(c, Capability) else c for c in capabilities]
    payload = {
        "sub": agent_id,
        "agent_type": agent_type.value,
        "merchant_scope": merchant_scope,
        "capabilities": caps,
        "policy_version": policy_version,
        "iat": now,
        "exp": now + expiry,
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
    }
    token = jwt.encode(payload, get_private_key(), algorithm="RS256", headers={"kid": "paari-key-1"})
    return token if isinstance(token, str) else token.decode("ascii")


def decode_token_unverified(token: str) -> dict:
    """Decode a JWT without verifying (used only for diagnostics)."""
    return jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
