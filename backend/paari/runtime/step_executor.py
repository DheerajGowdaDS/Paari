"""Step executor: runs one PlanStep through the gateway."""

from __future__ import annotations

import logging
from typing import Any

from paari.schemas.tool import ToolResult
from paari.tools.gateway import GatewayContext, ToolGateway

_log = logging.getLogger("paari.executor")


class StepExecutor:
    """Executes a single plan step through the gateway pipeline."""

    def __init__(self, gateway: ToolGateway) -> None:
        self._gateway = gateway

    async def execute(
        self,
        ctx: GatewayContext,
        step,
        *,
        on_review: Any | None = None,
    ) -> ToolResult:
        """Execute one step. Returns the ToolResult.

        If the result is REVIEW_REQUIRED, the caller must pause and wait for
        merchant approval (via on_review) before resuming.
        """
        return await self._gateway.execute(ctx, step.tool_name, step.arguments)
