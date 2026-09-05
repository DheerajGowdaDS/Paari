"""Paari Governance Engine — transaction-level governance evaluator.

Public surface:
  - GovernanceContext  (context.py)
  - GovernanceTxState, VALID_TRANSITIONS, IllegalTransitionError, transition (state_machine.py)
  - CheckResult, GovernanceDecision, GovernanceRequest (schemas)
  - RULE_PIPELINE  (rules/__init__.py)
  - GovernanceEngine, get_governance_engine() (evaluator.py)
"""
