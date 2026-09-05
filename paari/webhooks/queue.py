"""Async webhook event queue with in-process dedup.

Events are enqueued immediately after HMAC verification and DB insert.
The worker consumes from this queue. Dedup is handled by the DB unique
constraint on (source, webhook_id), not here.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("paari.webhooks.queue")


@dataclass
class WebhookEvent:
    """A verified, persisted webhook event ready for processing."""

    event_id: str
    source: str  # SHOPIFY | RAZORPAY
    merchant_id: str | None
    topic: str
    webhook_id: str
    payload: dict[str, Any]


class WebhookQueue:
    """Async queue for webhook events."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[WebhookEvent] = asyncio.Queue(maxsize=maxsize)
        self._seen: set[str] = set()  # in-process dedup

    async def put(self, event: WebhookEvent) -> bool:
        """Enqueue an event. Returns False if already seen (in-process dedup)."""
        if event.webhook_id in self._seen:
            _log.debug("Dropping duplicate webhook %s", event.webhook_id)
            return False
        self._seen.add(event.webhook_id)
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            _log.error("Webhook queue full, dropping event %s", event.event_id)
            return False

    async def get(self) -> WebhookEvent:
        """Get the next event (blocks until available)."""
        return await self._queue.get()

    def task_done(self) -> None:
        """Mark the last get() as done."""
        self._queue.task_done()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()


# Module-level singleton.
WEBHOOK_QUEUE = WebhookQueue()


def get_webhook_queue() -> WebhookQueue:
    return WEBHOOK_QUEUE
