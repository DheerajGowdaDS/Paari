"""Tests for buyer_credential governance rule.

Tests all 8 rows of the behaviour matrix:
  Under threshold, no token         → PASS / CREDENTIAL_OPTIONAL
  Under threshold, valid buyer JWT   → PASS / CREDENTIAL_VALID
  Under threshold, invalid JWT       → FAIL / CREDENTIAL_INVALID
  Over threshold, no token, deny=F  → REVIEW / CREDENTIAL_REQUIRED
  Over threshold, no token, deny=T  → FAIL / CREDENTIAL_MISSING
  Over threshold, valid buyer JWT     → PASS / CREDENTIAL_VALID
  Any, buyer token sub ≠ buyer      → FAIL / CREDENTIAL_MISMATCH
  Any, merchant token replayed       → FAIL / CREDENTIAL_INVALID
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from paari.authn.jwt_verifier import Identity
from paari.schemas.identity import AgentType


def _ctx(
    tx_id="tx-1",
    amount=500_000,
    buyer_agent_id="ba-1",
    credential_json=None,
    agent_type="BUYER",
    agent_active=True,
):
    agent = MagicMock(
        id=buyer_agent_id,
        agent_type=agent_type,
        status="ACTIVE" if agent_active else "SUSPENDED",
    )
    tx = MagicMock(
        id=tx_id,
        buyer_agent_id=buyer_agent_id,
        amount_paise=amount,
        buyer_credential_json=credential_json,
    )
    ctx = MagicMock()
    ctx.agent = agent
    ctx.transaction = tx
    return ctx


class TestUnderThresholdNoToken:
    @pytest.mark.asyncio
    async def test_under_threshold_no_token_passes(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000)
        with patch("paari.governance_engine.rules.buyer_credential.settings") as s:
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            result = check(ctx)
        assert result.status == "PASS"
        assert result.reason_code == "CREDENTIAL_OPTIONAL"


class TestUnderThresholdValidToken:
    @pytest.mark.asyncio
    async def test_under_threshold_valid_buyer_jwt_passes(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000, credential_json="valid.jwt.token")
        with (
            patch("paari.governance_engine.rules.buyer_credential.settings") as s,
            patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
        ):
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            vt.return_value = Identity(
                agent_id="ba-1",
                agent_type=AgentType.BUYER,
                merchant_scope=None,
                capabilities=[],
                policy_version="v1",
                jti="jti-1",
            )
            result = check(ctx)
        assert result.status == "PASS"
        assert result.reason_code == "CREDENTIAL_VALID"


class TestUnderThresholdInvalidToken:
    @pytest.mark.asyncio
    async def test_under_threshold_invalid_jwt_fails(self):
        from paari.governance_engine.rules.buyer_credential import check
        from paari.authn.jwt_verifier import TokenVerificationError

        ctx = _ctx(amount=500_000, credential_json="bad.jwt.token")
        with (
            patch("paari.governance_engine.rules.buyer_credential.settings") as s,
            patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
        ):
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            vt.side_effect = TokenVerificationError("expired")
            result = check(ctx)
        assert result.status == "FAIL"
        assert result.reason_code == "CREDENTIAL_INVALID"


class TestOverThresholdNoToken:
    @pytest.mark.asyncio
    async def test_over_threshold_no_token_review(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=2_000_000, credential_json=None)
        with patch("paari.governance_engine.rules.buyer_credential.settings") as s:
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            s.buyer_credential_deny_if_missing = False
            result = check(ctx)
        assert result.status == "REVIEW"
        assert result.reason_code == "CREDENTIAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_over_threshold_no_token_deny(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=2_000_000, credential_json=None)
        with patch("paari.governance_engine.rules.buyer_credential.settings") as s:
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            s.buyer_credential_deny_if_missing = True
            result = check(ctx)
        assert result.status == "FAIL"
        assert result.reason_code == "CREDENTIAL_MISSING"


class TestOverThresholdValidToken:
    @pytest.mark.asyncio
    async def test_over_threshold_valid_buyer_jwt_passes(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=2_000_000, credential_json="valid.jwt.token")
        with (
            patch("paari.governance_engine.rules.buyer_credential.settings") as s,
            patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
        ):
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            s.buyer_credential_deny_if_missing = False
            vt.return_value = Identity(
                agent_id="ba-1",
                agent_type=AgentType.BUYER,
                merchant_scope=None,
                capabilities=[],
                policy_version="v1",
                jti="jti-1",
            )
            result = check(ctx)
        assert result.status == "PASS"
        assert result.reason_code == "CREDENTIAL_VALID"


class TestCredentialMismatch:
    @pytest.mark.asyncio
    async def test_token_sub_mismatch_fails(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000, credential_json="mismatch.jwt.token", buyer_agent_id="ba-1")
        with (
            patch("paari.governance_engine.rules.buyer_credential.settings") as s,
            patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
        ):
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            vt.return_value = Identity(
                agent_id="ba-WRONG",
                agent_type=AgentType.BUYER,
                merchant_scope=None,
                capabilities=[],
                policy_version="v1",
                jti="jti-1",
            )
            result = check(ctx)
        assert result.status == "FAIL"
        assert result.reason_code == "CREDENTIAL_MISMATCH"

    @pytest.mark.asyncio
    async def test_merchant_token_replayed_as_buyer_fails(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000, credential_json="merchant.jwt.token")
        with (
            patch("paari.governance_engine.rules.buyer_credential.settings") as s,
            patch("paari.governance_engine.rules.buyer_credential.verify_token") as vt,
        ):
            s.buyer_credential_required = False
            s.buyer_credential_threshold_paise = 1_000_000
            vt.return_value = Identity(
                agent_id="ma-1",
                agent_type=AgentType.MERCHANT,
                merchant_scope="MER-001",
                capabilities=[],
                policy_version="v1",
                jti="jti-1",
            )
            result = check(ctx)
        assert result.status == "FAIL"
        assert result.reason_code == "CREDENTIAL_INVALID"


class TestCredentialRequiredFlag:
    @pytest.mark.asyncio
    async def test_flag_on_no_token_review(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000, credential_json=None)
        with patch("paari.governance_engine.rules.buyer_credential.settings") as s:
            s.buyer_credential_required = True
            s.buyer_credential_threshold_paise = 1_000_000
            s.buyer_credential_deny_if_missing = False
            result = check(ctx)
        assert result.status == "REVIEW"
        assert result.reason_code == "CREDENTIAL_REQUIRED"

    @pytest.mark.asyncio
    async def test_flag_on_no_token_deny(self):
        from paari.governance_engine.rules.buyer_credential import check

        ctx = _ctx(amount=500_000, credential_json=None)
        with patch("paari.governance_engine.rules.buyer_credential.settings") as s:
            s.buyer_credential_required = True
            s.buyer_credential_threshold_paise = 1_000_000
            s.buyer_credential_deny_if_missing = True
            result = check(ctx)
        assert result.status == "FAIL"
        assert result.reason_code == "CREDENTIAL_MISSING"
