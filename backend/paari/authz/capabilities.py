"""Capability hierarchy rules.

Capabilities are additive and least-privilege. Some capabilities imply
others (e.g. a merchant agent that can respond to quotes can also read
orders). This module defines that implication graph.
"""

from __future__ import annotations

from paari.schemas.capability import Capability

# implication: capability -> set of capabilities it grants
_IMPLICATIONS: dict[Capability, set[Capability]] = {
    Capability.QUOTE_RESPOND: {Capability.QUOTE_CREATE},
    Capability.ORDER_READ: {Capability.CATALOG_READ, Capability.INVENTORY_READ},
    Capability.REVIEW_READ: set(),
    Capability.AUDIT_READ: set(),
}


def implied_capabilities(capability: Capability) -> set[Capability]:
    """Return the set of capabilities granted by `capability` (including itself)."""
    granted = {capability}
    for implied in _IMPLICATIONS.get(capability, set()):
        granted.add(implied)
        granted |= implied_capabilities(implied)
    return granted


def expand_capabilities(capabilities: list[Capability]) -> set[Capability]:
    """Expand a grant list to its transitive closure."""
    expanded: set[Capability] = set()
    for cap in capabilities:
        expanded |= implied_capabilities(cap)
    return expanded
