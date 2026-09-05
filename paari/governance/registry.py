"""Paari global governance registry.

Loads and validates paari_governance.json. This is the single source of truth
for BOTH the LLM constitution (rendered from these rules) and the platform
policy layer of the policy engine. The two cannot drift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from paari.schemas.governance import GovernanceDocument

_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class PlatformLimits:
    max_autonomous_transaction_paise: int
    payment_session_ttl_seconds: int
    max_payment_retries: int


@dataclass(frozen=True)
class GovernanceRegistry:
    """Validated Paari platform governance."""

    version: str
    must: list[str]
    must_not: list[str]
    mandatory_rules: dict[str, str]
    limits: PlatformLimits
    document: GovernanceDocument

    def must_render(self) -> str:
        """Render the MUST list for the constitution."""
        return "\n".join(f"- {rule}" for rule in self.must)

    def must_not_render(self) -> str:
        """Render the MUST NOT list for the constitution."""
        return "\n".join(f"- {rule}" for rule in self.must_not)

    def mandatory_rules_render(self) -> str:
        """Render the P-01..P-10 list for the constitution."""
        return "\n".join(f"- {pid}: {desc}" for pid, desc in self.mandatory_rules.items())


def load_governance_registry() -> GovernanceRegistry:
    """Load and validate the platform governance document."""
    raw = json.loads((_DATA_DIR / "paari_governance.json").read_text(encoding="utf-8"))
    document = GovernanceDocument.model_validate(raw)
    limits_raw = raw.get("platform_limits", {})
    return GovernanceRegistry(
        version=raw["version"],
        must=list(raw["must"]),
        must_not=list(raw["must_not"]),
        mandatory_rules=dict(raw["mandatory_rules"]),
        limits=PlatformLimits(
            max_autonomous_transaction_paise=int(limits_raw.get("max_autonomous_transaction_paise", 5_000_000)),
            payment_session_ttl_seconds=int(limits_raw.get("payment_session_ttl_seconds", 600)),
            max_payment_retries=int(limits_raw.get("max_payment_retries", 3)),
        ),
        document=document,
    )


# Module-level singleton so the constitution and policy engine always agree.
GOVERNANCE: GovernanceRegistry = load_governance_registry()


def validate_governance() -> None:
    """Raise if the governance document is invalid (used at startup)."""
    try:
        load_governance_registry()
    except (ValidationError, KeyError, TypeError) as exc:  # pragma: no cover - startup guard
        raise RuntimeError(f"invalid paari_governance.json: {exc}") from exc
