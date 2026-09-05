"""A2A Agent Registration and Discovery API.

Phase 2 endpoints for agent-to-agent communication:
- POST /api/agents/register - Register a new agent
- GET /api/agents/discover - List active merchant agents
- GET /api/agents/{agent_id} - Get agent details
- GET /api/agents/{agent_id}/card - Get agent card for A2A

These extend the existing Paari agent system for A2A communication.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from paari.db.engine import get_session_maker
from paari.schemas.identity import AgentType

router = APIRouter(prefix="/api/agents", tags=["a2a_agents"])


class RegisterAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier (UUID)")
    display_id: str | None = Field(
        default=None,
        description="Human-readable agent ID (e.g. BA-001)",
    )
    agent_type: str = Field(..., description="BUYER | MERCHANT | SYSTEM")
    capabilities: list[str] = Field(
        default_factory=list,
        description="List of capability names",
    )
    merchant_id: str | None = Field(
        default=None,
        description="Associated merchant ID for merchant agents",
    )
    a2a_endpoint: str | None = Field(
        default=None,
        description="URL this agent listens on for A2A messages",
    )
    owner_id: str | None = Field(
        default=None,
        description="Owner user ID",
    )


class RegisterAgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_id: str
    status: str
    registered_at: str


class AgentCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    display_id: str | None = None
    agent_type: str
    capabilities: list[str]
    merchant_id: str | None = None
    a2a_endpoint: str | None = None
    status: str
    registered_at: str | None = None


class DiscoverAgentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentCardResponse]
    total: int


@router.post("/register", response_model=RegisterAgentResponse)
async def register_agent(req: RegisterAgentRequest) -> RegisterAgentResponse:
    """Register a new agent for A2A communication.

    POST /api/agents/register

    Body:
      {
        "agent_id": "550e8400-e29b-41d4-a716-446655440000",
        "display_id": "BA-002",
        "agent_type": "BUYER",
        "capabilities": ["catalog.read", "quote.request", "payment.execute"],
        "a2a_endpoint": "http://localhost:8001/a2a"
      }
    """
    maker = get_session_maker()

    agent_id = req.agent_id
    if not req.display_id:
        display_id = f"{req.agent_type[:1]}-{uuid.uuid4().hex[:6].upper()}"
    else:
        display_id = req.display_id

    async with maker() as session:
        from sqlalchemy import text

        # Check if agent already exists
        existing = (
            await session.execute(
                text("SELECT id FROM agents WHERE id = :id OR display_id = :did"),
                {"id": agent_id, "did": display_id},
            )
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Agent already exists: {existing.id}",
            )

        # Add a2a_endpoint column if not exists
        try:
            await session.execute(
                text("ALTER TABLE agents ADD COLUMN a2a_endpoint TEXT")
            )
        except Exception:
            pass  # Column may already exist

        now = datetime.now(UTC).isoformat()
        await session.execute(
            text(
                "INSERT INTO agents (id, display_id, agent_type, capabilities_json, "
                " merchant_id, a2a_endpoint, owner_id, status, created_at) "
                "VALUES (:id, :display_id, :type, :caps, :merchant_id, :endpoint, :owner, 'ACTIVE', :created)"
            ),
            {
                "id": agent_id,
                "display_id": display_id,
                "type": req.agent_type.upper(),
                "caps": json.dumps(req.capabilities),
                "merchant_id": req.merchant_id,
                "endpoint": req.a2a_endpoint,
                "owner": req.owner_id,
                "created": now,
            },
        )
        await session.commit()

    return RegisterAgentResponse(
        agent_id=agent_id,
        display_id=display_id,
        status="ACTIVE",
        registered_at=now,
    )


@router.get("/discover", response_model=DiscoverAgentsResponse)
async def discover_agents(
    agent_type: str | None = None,
    capabilities: str | None = None,
    merchant_id: str | None = None,
) -> DiscoverAgentsResponse:
    """Discover active agents for A2A communication.

    GET /api/agents/discover
    GET /api/agents/discover?agent_type=MERCHANT
    GET /api/agents/discover?capabilities=catalog.read,quote.create

    Query params:
    - agent_type: Filter by agent type (BUYER, MERCHANT)
    - capabilities: Comma-separated list of required capabilities
    - merchant_id: Filter by merchant (for merchant agents)
    """
    maker = get_session_maker()

    async with maker() as session:
        from sqlalchemy import text

        query = "SELECT id, display_id, agent_type, capabilities_json, merchant_id, a2a_endpoint, status, created_at FROM agents WHERE status = 'ACTIVE' AND display_id IS NOT NULL"
        params: dict = {}

        if agent_type:
            query += " AND agent_type = :agent_type"
            params["agent_type"] = agent_type.upper()

        if merchant_id:
            query += " AND merchant_id = :merchant_id"
            params["merchant_id"] = merchant_id

        query += " ORDER BY created_at DESC"

        rows = (
            await session.execute(text(query), params)
        ).fetchall()

        # Filter by capabilities if specified
        required_caps: set[str] = set()
        if capabilities:
            required_caps = {c.strip().lower() for c in capabilities.split(",")}

        agents = []
        for row in rows:
            agent_caps: set[str] = set()
            try:
                agent_caps = {c.lower() for c in json.loads(row.capabilities_json or "[]")}
            except Exception:
                pass

            # Skip if doesn't have all required capabilities
            if required_caps and not required_caps.issubset(agent_caps):
                continue

            agents.append(
                AgentCardResponse(
                    agent_id=row.id,
                    display_id=row.display_id,
                    agent_type=row.agent_type,
                    capabilities=list(agent_caps),
                    merchant_id=row.merchant_id,
                    a2a_endpoint=row.a2a_endpoint,
                    status=row.status,
                    registered_at=_iso(row.created_at),
                )
            )

    return DiscoverAgentsResponse(agents=agents, total=len(agents))


def _iso(value) -> str | None:
    """Convert a DB timestamp (datetime or ISO string) to an ISO string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


@router.get("/{agent_id}", response_model=AgentCardResponse)
async def get_agent(agent_id: str) -> AgentCardResponse:
    """Get agent details by ID.

    GET /api/agents/{agent_id}

    Supports both UUID and display_id (e.g. BA-001).
    """
    maker = get_session_maker()

    async with maker() as session:
        from sqlalchemy import text

        row = (
            await session.execute(
                text(
                    "SELECT id, display_id, agent_type, capabilities_json, merchant_id, "
                    "a2a_endpoint, status, created_at FROM agents "
                    "WHERE id = :id OR display_id = :id"
                ),
                {"id": agent_id},
            )
        ).first()

        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")

        try:
            caps = [c.lower() for c in json.loads(row.capabilities_json or "[]")]
        except Exception:
            caps = []

    return AgentCardResponse(
        agent_id=row.id,
        display_id=row.display_id,
        agent_type=row.agent_type,
        capabilities=caps,
        merchant_id=row.merchant_id,
        a2a_endpoint=row.a2a_endpoint,
        status=row.status,
        registered_at=_iso(row.created_at),
    )


@router.get("/{agent_id}/card", response_model=AgentCardResponse)
async def get_agent_card(agent_id: str) -> AgentCardResponse:
    """Get agent card for A2A communication.

    GET /api/agents/{agent_id}/card

    This is the same as GET /api/agents/{agent_id} but explicitly returns
    an agent card format suitable for A2A discovery.
    """
    return await get_agent(agent_id)
