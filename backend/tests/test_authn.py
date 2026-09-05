"""Step 6 validation: JWT issue, verify, expiry, revocation, tamper."""

from __future__ import annotations

import time

import pytest

from paari.authn.jwt_issuer import issue_agent_token
from paari.authn.jwt_verifier import TokenVerificationError, verify_token
from paari.authn.revocation import is_revoked, revoke
from paari.schemas.capability import Capability
from paari.schemas.identity import AgentType


def _token(**kwargs) -> str:
    return issue_agent_token(
        agent_id="buyer-agent-001",
        agent_type=AgentType.BUYER,
        capabilities=[Capability.CATALOG_READ, Capability.PAYMENT_REQUEST],
        merchant_scope=None,
        policy_version="v1",
        **kwargs,
    )


def test_issue_and_verify_round_trip() -> None:
    token = _token()
    identity = verify_token(token)
    assert identity.agent_id == "buyer-agent-001"
    assert identity.agent_type == AgentType.BUYER
    assert "catalog.read" in identity.capabilities
    assert "payment.request" in identity.capabilities
    assert identity.policy_version == "v1"


def test_wrong_issuer_rejected() -> None:
    import jwt as _jwt

    from paari.authn.jwks import get_private_key

    now = int(time.time())
    payload = {
        "sub": "buyer-agent-001",
        "agent_type": "BUYER",
        "capabilities": ["catalog.read"],
        "policy_version": "v1",
        "iat": now,
        "exp": now + 900,
        "jti": "t1",
        "iss": "evil-issuer",
    }
    token = _jwt.encode(payload, get_private_key(), algorithm="RS256")
    with pytest.raises(TokenVerificationError):
        verify_token(token)


def test_expired_token_rejected() -> None:
    token = _token(expire_seconds=-10)
    with pytest.raises(TokenVerificationError):
        verify_token(token)


def test_revoked_token_rejected() -> None:
    from paari.authn.revocation import _revoked

    token = _token()
    # Fetch jti via unverified decode to revoke it.
    import jwt as _jwt

    decoded = _jwt.decode(token, options={"verify_signature": False})
    revoke(decoded["jti"], expires_at=decoded["exp"])
    assert is_revoked(decoded["jti"])
    with pytest.raises(TokenVerificationError):
        verify_token(token)
    # Clean up so this doesn't leak into other tests.
    _revoked.pop(decoded["jti"], None)
    assert not is_revoked(decoded["jti"])


def test_tampered_signature_rejected() -> None:
    token = _token()
    # Flip a character in the signature segment.
    head, *rest = token.split(".")
    sig = rest[-1]
    tampered_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    tampered = ".".join([head, rest[0], tampered_sig])
    with pytest.raises(TokenVerificationError):
        verify_token(tampered)


def test_merchant_scope_preserved() -> None:
    from paari.authn.jwt_issuer import issue_agent_token

    token = issue_agent_token(
        agent_id="merchant-agent-001",
        agent_type=AgentType.MERCHANT,
        capabilities=[Capability.REVIEW_READ],
        merchant_scope="merchant-demo-001",
    )
    identity = verify_token(token)
    assert identity.merchant_scope == "merchant-demo-001"
