"""Governance rule registry — RULE_PIPELINE list.

Import order matters: checks run in list order. Each entry is a callable
``check(context: GovernanceContext) -> CheckResult``.
"""

from __future__ import annotations

from paari.governance_engine.rules.agent_identity import check as agent_identity_check
from paari.governance_engine.rules.agent_authorization import check as agent_authorization_check
from paari.governance_engine.rules.autonomous_payment import check as autonomous_payment_check
from paari.governance_engine.rules.amount_policy import check as amount_policy_check
from paari.governance_engine.rules.buyer_credential import check as buyer_credential_check
from paari.governance_engine.rules.mandate import check as mandate_check
from paari.governance_engine.rules.merchant_authorization import (
    check as merchant_authorization_check,
)
from paari.governance_engine.rules.quote_validation import check as quote_validation_check
from paari.governance_engine.rules.risk_check import check as risk_check_check
from paari.governance_engine.rules.user_spending import check as user_spending_check

RULE_PIPELINE: list = [
    agent_identity_check,
    agent_authorization_check,
    merchant_authorization_check,
    quote_validation_check,
    amount_policy_check,
    user_spending_check,
    mandate_check,
    autonomous_payment_check,
    risk_check_check,
    buyer_credential_check,
]
