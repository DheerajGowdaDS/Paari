"""Authorization engine: capability checks with least-privilege semantics."""

from __future__ import annotations

from paari.authz.capabilities import expand_capabilities
from paari.schemas.capability import Capability, CapabilitySet


class AuthorizationError(Exception):
    """Raised when an agent lacks a required capability."""


class AuthorizationEngine:
    """Decides whether an agent may perform an action.

    Least-privilege: an agent's granted capabilities are expanded to their
    transitive closure, then matched against the required capability.
    """

    def __init__(self, grants: dict[str, CapabilitySet]) -> None:
        self._grants = {
            agent_id: CapabilitySet(
                agent_id=agent_id,
                capabilities=sorted(expand_capabilities(list(cs.capabilities)), key=lambda c: c.value),
            )
            for agent_id, cs in grants.items()
        }

    def has_capability(self, agent_id: str, capability: Capability | str) -> bool:
        """Return True if the agent's expanded grant set includes `capability`."""
        target = Capability(capability) if isinstance(capability, str) else capability
        cs = self._grants.get(agent_id)
        if cs is None:
            return False
        return target in cs.capabilities

    def require_capability(self, agent_id: str, capability: Capability | str) -> None:
        """Raise AuthorizationError if the agent lacks the capability."""
        if not self.has_capability(agent_id, capability):
            target = Capability(capability) if isinstance(capability, str) else capability
            raise AuthorizationError(f"agent {agent_id} lacks capability {target.value}")

    def capabilities_for(self, agent_id: str) -> list[Capability]:
        return list(self._grants.get(agent_id, CapabilitySet(agent_id=agent_id, capabilities=[])).capabilities)

    def grant_for(self, agent_id: str) -> CapabilitySet | None:
        return self._grants.get(agent_id)


def build_grants_from_long_term() -> dict[str, CapabilitySet]:
    """Build the in-memory grant table from the long-term config (demo)."""
    from paari.memory.long_term import load_long_term_config

    config = load_long_term_config()
    grants: dict[str, CapabilitySet] = {}
    if config.buyer_grant is not None:
        grants[config.buyer_grant.agent_id] = CapabilitySet(
            agent_id=config.buyer_grant.agent_id,
            capabilities=list(config.buyer_grant.capabilities),
        )
    if config.merchant_grant is not None:
        grants[config.merchant_grant.agent_id] = CapabilitySet(
            agent_id=config.merchant_grant.agent_id,
            capabilities=list(config.merchant_grant.capabilities),
        )
    return grants


# Module-level engine so the gateway can import it without re-building.
GRANTS: dict[str, CapabilitySet] = build_grants_from_long_term()
AUTHZ = AuthorizationEngine(GRANTS)


def reload_authz() -> AuthorizationEngine:
    """Rebuild the grant table and engine (used after seed or policy changes)."""
    global GRANTS, AUTHZ
    GRANTS = build_grants_from_long_term()
    AUTHZ = AuthorizationEngine(GRANTS)
    return AUTHZ
