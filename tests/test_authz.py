"""Step 7 validation: authorization engine and capability hierarchy."""

from __future__ import annotations

import pytest

from paari.authz import AuthorizationEngine, AuthorizationError, Capability, CapabilitySet
from paari.authz.capabilities import expand_capabilities, implied_capabilities


def _engine(grants: dict[str, list[Capability]]) -> AuthorizationEngine:
    return AuthorizationEngine(
        {agent_id: CapabilitySet(agent_id=agent_id, capabilities=caps) for agent_id, caps in grants.items()}
    )


def test_granted_capability() -> None:
    engine = _engine({"a": [Capability.CATALOG_READ]})
    assert engine.has_capability("a", "catalog.read")
    assert not engine.has_capability("a", "inventory.read")


def test_ungranted_capability() -> None:
    engine = _engine({"a": [Capability.CATALOG_READ]})
    assert not engine.has_capability("a", "payment.request")


def test_unknown_agent() -> None:
    engine = _engine({"a": [Capability.CATALOG_READ]})
    assert not engine.has_capability("ghost", "catalog.read")


def test_require_capability_raises() -> None:
    engine = _engine({"a": [Capability.CATALOG_READ]})
    with pytest.raises(AuthorizationError):
        engine.require_capability("a", "payment.request")


def test_require_capability_passes() -> None:
    engine = _engine({"a": [Capability.CATALOG_READ]})
    engine.require_capability("a", "catalog.read")  # no raise


def test_capability_hierarchy() -> None:
    """quote.respond implies quote.create (transitive closure)."""
    engine = _engine({"m": [Capability.QUOTE_RESPOND]})
    assert engine.has_capability("m", "quote.respond")
    assert engine.has_capability("m", "quote.create")


def test_expand_capabilities_transitive() -> None:
    expanded = expand_capabilities([Capability.ORDER_READ])
    assert Capability.CATALOG_READ in expanded
    assert Capability.INVENTORY_READ in expanded
    assert Capability.ORDER_READ in expanded


def test_implied_capabilities_self_included() -> None:
    implied = implied_capabilities(Capability.CATALOG_READ)
    assert Capability.CATALOG_READ in implied
