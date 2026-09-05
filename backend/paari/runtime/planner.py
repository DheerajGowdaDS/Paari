"""Planner: parse LLM output into a list of PlanSteps."""

from __future__ import annotations

import logging
from typing import Any

from paari.schemas.tool import ToolCall

_log = logging.getLogger("paari.planner")


class PlanStep:
    """One step in the LLM's proposed plan."""

    def __init__(self, call_id: str, tool_name: str, arguments: dict[str, Any], rationale: str | None = None) -> None:
        self.call_id = call_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.rationale = rationale


class Planner:
    """Parses an LLM response into a list of PlanSteps."""

    def parse(self, llm_response) -> list[PlanStep]:
        """Convert an LLMResponse into PlanSteps.

        Every tool_call becomes one PlanStep. Unknown tools are passed through
        so the gateway can reject them (and audit the rejection); the planner
        does not silently drop them.
        """
        steps: list[PlanStep] = []
        for call in llm_response.tool_calls:
            steps.append(
                PlanStep(
                    call_id=call.get("call_id", "call-unknown"),
                    tool_name=call.get("tool_name", ""),
                    arguments=call.get("arguments") or {},
                    rationale=None,
                )
            )
        return steps


def parse_tool_calls(tool_calls: list[dict[str, Any]]) -> list[ToolCall]:
    """Validate tool calls against the ToolCall schema (extra=forbid)."""
    out: list[ToolCall] = []
    for raw in tool_calls:
        try:
            out.append(ToolCall.model_validate(raw))
        except Exception as exc:  # noqa: BLE001 - malformed tool call
            _log.warning("dropping malformed tool call: %s", exc)
    return out
