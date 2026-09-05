"""LLM API client (OpenAI-compatible HTTPS endpoint).

No GPU required: the model runs on the provider's infrastructure. The API key
is read from env at startup, held in memory, and never logged, never sent to
merchants or buyer agents.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from paari.config import settings

_log = logging.getLogger("paari.llm")


class LLMError(Exception):
    """Raised when the LLM API cannot be reached or returns invalid output."""


@dataclass
class LLMResponse:
    """A parsed response from the chat/completions endpoint."""

    content: str | None
    tool_calls: list[dict[str, Any]]  # each: {call_id, tool_name, arguments}
    raw: dict[str, Any]


class LLMClient:
    """Async client for an OpenAI-compatible chat/completions endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self._base_url = (base_url or settings.llm_base_url).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._model = model or settings.llm_model
        self._timeout = timeout_s if timeout_s is not None else settings.llm_timeout_s
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        constitution: str,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
        user_input: str,
        max_retries: int = 1,
    ) -> LLMResponse:
        """Send a chat/completions request and return a parsed response.

        Retries once on transient failures. Raises LLMError on hard failures.
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": constitution},
                {"role": "system", "content": json.dumps(context, separators=(",", ":"))},
                {"role": "user", "content": user_input},
            ],
            "tools": tools,
            "tool_choice": "auto",
        }
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self._post(payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                _log.warning("llm attempt %d failed: %s", attempt, exc)
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise LLMError(f"llm unavailable after {max_retries + 1} attempts: {last_exc}")

    async def _post(self, payload: dict[str, Any]) -> LLMResponse:
        try:
            r = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"llm request failed: {exc}") from exc
        if r.status_code != 200:
            # Never log the API key; the response body may contain it in error messages.
            _log.error("llm returned status %s", r.status_code)
            raise LLMError(f"llm returned status {r.status_code}")
        try:
            data = r.json()
        except ValueError as exc:
            raise LLMError("llm returned non-JSON response") from exc
        return self._parse(data)

    @staticmethod
    def _parse(data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("llm returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        tool_calls: list[dict[str, Any]] = []
        for raw_call in message.get("tool_calls") or []:
            try:
                args = json.loads(raw_call.get("function", {}).get("arguments", "{}"))
            except (ValueError, TypeError):
                args = {}
            tool_calls.append(
                {
                    "call_id": raw_call.get("id", "call-unknown"),
                    "tool_name": raw_call.get("function", {}).get("name", ""),
                    "arguments": args if isinstance(args, dict) else {},
                }
            )
        return LLMResponse(content=content, tool_calls=tool_calls, raw=data)


# Module-level singleton.
LLM = LLMClient()


def get_llm() -> LLMClient:
    return LLM
