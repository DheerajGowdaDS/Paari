"""Convert the tool registry to OpenAI chat/completions tool format."""

from __future__ import annotations

from paari.tools.registry import ToolRegistry


def to_openai_tools(registry: ToolRegistry, capabilities: list[str] | None = None) -> list[dict]:
    """Return the OpenAI tool schema list for the agent's capabilities."""
    return registry.to_openai_tools(capabilities)


def to_openai_tools_for_agent(registry: ToolRegistry, identity_capabilities: list[str]) -> list[dict]:
    """Convenience: convert identity capabilities to OpenAI tools."""
    return registry.to_openai_tools(identity_capabilities)
