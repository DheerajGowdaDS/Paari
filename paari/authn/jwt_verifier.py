"""Verify RS256 agent JWTs and check revocation."""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from jwt import PyJWK
from jwt.exceptions import InvalidTokenError

from paari.authn.jwks import jwks
from paari.authn.revocation import is_revoked
from paari.config import settings
from paari.schemas.identity import AgentType, JwtClaims


@dataclass(frozen=True)
class Identity:
    """The verified identity of an agent."""

    agent_id: str
    agent_type: AgentType
    merchant_scope: str | None
    capabilities: list[str]
    policy_version: str
    jti: str


class TokenVerificationError(Exception):
    """Raised when a JWT cannot be verified."""


def _jwks_dict() -> dict:
    return jwks()


def verify_token(token: str) -> Identity:
    """Verify an RS256 JWT and return the agent's Identity.

    Checks: signature (RS256 via JWKS), expiry, issuer, and revocation.
    Raises TokenVerificationError on any failure.
    """
    jwks_doc = _jwks_dict()
    if not jwks_doc.get("keys"):
        raise TokenVerificationError("no signing keys available")

    try:
        # Build a PyJWK from our JWKS and verify.
        jwk = PyJWK(jwks_doc["keys"][0])
        decoded = jwt.decode(
            token,
            key=jwk.key,
            algorithms=["RS256"],
            issuer=settings.jwt_issuer,
            options={"verify_exp": True, "verify_aud": False},
        )
    except InvalidTokenError as exc:
        raise TokenVerificationError(f"token verification failed: {exc}") from exc

    jti = decoded.get("jti")
    if jti and is_revoked(jti):
        raise TokenVerificationError("token has been revoked")

    try:
        claims = JwtClaims.model_validate(decoded)
    except Exception as exc:  # noqa: BLE001 - pydantic ValidationError
        raise TokenVerificationError(f"invalid claims shape: {exc}") from exc

    return Identity(
        agent_id=claims.sub,
        agent_type=claims.agent_type,
        merchant_scope=claims.merchant_scope,
        capabilities=list(claims.capabilities),
        policy_version=claims.policy_version,
        jti=claims.jti,
    )


def token_expired(token: str) -> bool:
    """Return True if the token's exp has passed (unverified decode)."""
    try:
        decoded = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return decoded.get("exp", 0) < int(time.time())
    except InvalidTokenError:
        return True
