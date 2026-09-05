"""Context builder: the data boundary between Paari and the LLM.

Strips credentials, API keys, internal IDs, payment tokens, and other
merchants' data before context assembly. Injects only the minimal policy
summary, capability descriptions, and transaction context the LLM needs to
reason about the current request.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from paari.authn.jwt_verifier import Identity
from paari.schemas.runtime import RuntimeContext


def _merchant_profile(merchant_id: str) -> dict[str, Any]:
    """Best-effort sync read of merchant display fields for the LLM prompt.

    Feeds context only — never enforcement. Falls back to demo defaults when
    the DB is unreachable or not SQLite.
    """
    default_limit = 2_000_000
    try:
        from paari.config import settings

        default_limit = settings.demo_merchant_autonomous_limit_paise
    except Exception:
        pass
    defaults: dict[str, Any] = {
        "name": "Paari Demo Store",
        "autonomous_limit_paise": default_limit,
        "active_hours_utc": list(range(9, 22)),
        "average_transaction_paise": 120_000,
    }
    try:
        from paari.config import settings

        url = settings.db_url
        if not url.startswith("sqlite"):
            return defaults
        import sqlite3

        path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        con = sqlite3.connect(path)
        try:
            row = con.execute(
                "SELECT name, active_hours_utc, avg_transaction_paise, autonomous_limit_paise "
                "FROM merchants WHERE id = ?",
                (merchant_id,),
            ).fetchone()
        finally:
            con.close()
        if not row:
            return defaults
        active = defaults["active_hours_utc"]
        if row[1]:
            try:
                active = json.loads(row[1])
            except Exception:
                pass
        return {
            "name": row[0] or defaults["name"],
            "autonomous_limit_paise": int(row[3] or defaults["autonomous_limit_paise"]),
            "active_hours_utc": active,
            "average_transaction_paise": int(row[2] or defaults["average_transaction_paise"]),
        }
    except Exception:
        return defaults


@dataclass
class ContextBuilder:
    """Builds the minimal, sanitized runtime context for an LLM call."""

    merchant_id: str = "merchant-demo-001"
    merchant_name: str = "Demo Shoes"
    autonomous_limit_paise: int = 2_000_000
    active_hours_utc: list[int] = field(default_factory=list)
    average_transaction_paise: int = 120_000
    catalog: dict[str, Any] = field(default_factory=dict)
    store_policies: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_long_term(cls) -> ContextBuilder:
        from paari.memory.long_term import load_long_term_config

        config = load_long_term_config()
        from pathlib import Path

        catalog = json.loads(
            (Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "catalog.json").read_text(encoding="utf-8")
        )
        store_policies = json.loads(
            (Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "store_policies.json").read_text(encoding="utf-8")
        )
        return cls(
            merchant_id=config.merchant_id,
            merchant_name=config.merchant_name,
            autonomous_limit_paise=config.autonomous_limit_paise,
            active_hours_utc=config.active_hours_utc,
            average_transaction_paise=config.average_transaction_paise,
            catalog=catalog,
            store_policies=store_policies,
        )

    @classmethod
    def from_merchant_registry(cls, merchant_id: str = "MER-001") -> ContextBuilder:
        """Build from merchant registry + store context (live mode)."""
        import asyncio
        from pathlib import Path

        from paari.config import settings
        from paari.store_context import cache as ctx_cache

        profile = _merchant_profile(merchant_id)

        # Try to load from store context cache
        cached = ctx_cache.get_cached(merchant_id)
        if cached is not None:
            payload = cached["payload"]
            catalog_data = payload.get("catalog", {})
            policies = payload.get("policies", {})
            return cls(
                merchant_id=merchant_id,
                merchant_name=profile["name"],
                autonomous_limit_paise=profile["autonomous_limit_paise"],
                active_hours_utc=profile["active_hours_utc"],
                average_transaction_paise=profile["average_transaction_paise"],
                catalog=catalog_data,
                store_policies=policies,
            )

        # Fallback to fixtures
        catalog = json.loads(
            (Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "catalog.json").read_text(encoding="utf-8")
        )
        store_policies = json.loads(
            (Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "store_policies.json").read_text(encoding="utf-8")
        )
        return cls(
            merchant_id=merchant_id,
            merchant_name=profile["name"],
            autonomous_limit_paise=profile["autonomous_limit_paise"],
            active_hours_utc=profile["active_hours_utc"],
            average_transaction_paise=profile["average_transaction_paise"],
            catalog=catalog,
            store_policies=store_policies,
        )

    def build(self, identity: Identity, request: dict[str, Any]) -> RuntimeContext:
        """Build the sanitized runtime context for one LLM call."""
        tx_context = self._build_tx_context(request)
        policy_summary = self._build_policy_summary(identity, request, tx_context)
        merchant_context = self._build_merchant_context(identity)
        return RuntimeContext(
            you_are={
                "agent_id": identity.agent_id,
                "agent_type": identity.agent_type.value,
            },
            your_capabilities=list(identity.capabilities),
            policy_summary=policy_summary,
            merchant_context=merchant_context,
            transaction_context=tx_context,
            data_boundary_notice=(
                "All data in this context is sanitized. You may not request or "
                "assume any data outside what is provided here. You may not "
                "invent inventory, prices, or payment facts."
            ),
        )

    def _build_tx_context(self, request: dict[str, Any]) -> dict[str, Any]:
        """Build the transaction context from the buyer request."""
        return {
            "buyer_request": request.get("buyer_request", ""),
            "amount_paise": request.get("amount_paise"),
            "currency": request.get("currency", "INR"),
            "quantity": request.get("quantity", 1),
            "discount_pct": request.get("discount_pct", 0),
            "sku": request.get("sku"),
            "international": False,
        }

    def _build_policy_summary(self, identity: Identity, request: dict[str, Any], tx_context: dict[str, Any]) -> dict[str, Any]:
        """Project only the policy rules relevant to this request, plus a hash
        of the full policy for verifiability."""
        from paari.policy_engine.compiler import compile_policy
        from paari.policy_engine.document import load_policy_documents
        from paari.schemas.policy import PolicyLayer

        docs = load_policy_documents()
        compiled = compile_policy(
            paari=docs[PolicyLayer.PAARI],
            merchant=docs[PolicyLayer.MERCHANT],
            store=docs[PolicyLayer.STORE],
        )
        # Full policy hash for verifiability (what the LLM saw vs what the
        # enforcer saw can be compared later).
        full = {layer.value: doc.model_dump_json() for layer, doc in docs.items()}
        policy_hash = hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()
        return {
            "autonomous_limit_paise": self.autonomous_limit_paise,
            "max_discount_pct": 10,
            "max_quantity": 5,
            "international_shipping": False,
            "full_policy_hash": policy_hash,
            "policy_version": compiled.version,
        }

    def _build_merchant_context(self, identity: Identity) -> dict[str, Any]:
        """Sanitized merchant context: no credentials, no internal IDs, no
        payment tokens, no other merchants' data."""
        return {
            "merchant_id": self.merchant_id,
            "merchant_name": self.merchant_name,
            "shipping_policy": self.store_policies.get("shipping_policy", ""),
            "return_policy": self.store_policies.get("return_policy", ""),
            "international_shipping": False,
            "active_hours_utc": self.active_hours_utc,
        }


# Module-level singleton.
def _build_context_builder() -> ContextBuilder:
    """Build context builder based on shopify_mode."""
    from paari.config import settings

    if settings.shopify_mode == "live":
        try:
            return ContextBuilder.from_merchant_registry("MER-001")
        except Exception:
            _log = __import__("logging", fromlist=["getLogger"]).getLogger("paari.context_builder")
            _log.warning("Failed to load from merchant registry, falling back to fixtures")
    return ContextBuilder.from_long_term()


CONTEXT_BUILDER = _build_context_builder()


def get_context_builder() -> ContextBuilder:
    return CONTEXT_BUILDER
