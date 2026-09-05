"""Grant loader: reads agent capability sets from the database."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from paari.authz.engine import AuthorizationEngine, build_grants_from_long_term
from paari.schemas.capability import Capability, CapabilitySet


async def load_grants_from_db(session: AsyncSession) -> dict[str, CapabilitySet]:
    """Load every agent's capability set from the agents table."""
    result = await session.execute(text("SELECT id, agent_type, capabilities_json FROM agents"))
    grants: dict[str, CapabilitySet] = {}
    for row in result:
        caps = [Capability(c) for c in json.loads(row.capabilities_json or "[]")]
        grants[row.id] = CapabilitySet(agent_id=row.id, capabilities=caps)
    return grants


async def reload_authz_from_db(session: AsyncSession) -> AuthorizationEngine:
    """Rebuild the authorization engine from the database."""
    grants = await load_grants_from_db(session)
    return AuthorizationEngine(grants)


def default_authz() -> AuthorizationEngine:
    """Return the engine built from the long-term config (demo fallback)."""
    return AuthorizationEngine(build_grants_from_long_term())
