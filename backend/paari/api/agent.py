"""Agent runtime router: POST /agent/run drives the full Paari pipeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from paari.authn.dependencies import get_identity
from paari.authn.jwt_verifier import Identity
from paari.runtime.loop import get_runtime

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    buyer_request: str = Field(..., description="Natural-language buyer intent")
    amount_paise: int | None = None
    currency: str = "INR"
    quantity: int = 1
    discount_pct: int = 0
    sku: str | None = None


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: str
    message: str
    tool_results: list[dict] = Field(default_factory=list)
    review_id: str | None = None
    transaction_id: str | None = None


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    body: AgentRunRequest,
    identity: Identity = Depends(get_identity),
) -> AgentRunResponse:
    """Run the Paari agent loop for one buyer request."""
    runtime = get_runtime()
    response = await runtime.run(
        identity,
        body.buyer_request,
        amount_paise=body.amount_paise,
        currency=body.currency,
        quantity=body.quantity,
        discount_pct=body.discount_pct,
        sku=body.sku,
    )
    return AgentRunResponse(**response.model_dump())
