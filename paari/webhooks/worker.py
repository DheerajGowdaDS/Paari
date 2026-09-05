"""Background webhook worker.

Consumes events from the queue and dispatches to topic-specific handlers.
Updates webhook_events status in the DB after processing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from paari.webhooks.handlers import handle_inventory_update, handle_order_event
from paari.webhooks.queue import WebhookEvent, WebhookQueue

_log = logging.getLogger("paari.webhooks.worker")

# Topic -> handler mapping
_HANDLERS: dict[str, Callable[[WebhookEvent], Coroutine[Any, Any, None]]] = {
    "orders/create": handle_order_event,
    "orders/updated": handle_order_event,
    "orders/delete": handle_order_event,
    "inventory_levels/update": handle_inventory_update,
}


async def _update_event_status(event_id: str, status: str, error: str | None = None) -> None:
    """Update webhook_events status in the DB."""
    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        await session.execute(
            text(
                "UPDATE webhook_events SET status = :status, error = :error, "
                "processed_at = CURRENT_TIMESTAMP WHERE id = :id"
            ),
            {"id": event_id, "status": status, "error": error},
        )
        await session.commit()


async def process_event(event: WebhookEvent) -> None:
    """Process a single webhook event."""
    handler = _HANDLERS.get(event.topic)
    if handler is None:
        _log.warning("No handler for topic: %s", event.topic)
        await _update_event_status(event.event_id, "SKIPPED")
        return

    try:
        await handler(event)
        await _update_event_status(event.event_id, "PROCESSED")
        _log.info("Processed webhook %s (topic=%s)", event.event_id, event.topic)
    except Exception as e:
        _log.error("Failed to process webhook %s: %s", event.event_id, e)
        await _update_event_status(event.event_id, "FAILED", str(e))


async def run_worker(queue: WebhookQueue) -> None:
    """Main worker loop: consume events and process them."""
    _log.info("Webhook worker started")
    while True:
        event = await queue.get()
        try:
            await process_event(event)
        finally:
            queue.task_done()


_worker_task: asyncio.Task | None = None


def start_worker(queue: WebhookQueue | None = None) -> asyncio.Task:
    """Start the background webhook worker."""
    global _worker_task
    if queue is None:
        from paari.webhooks.queue import WEBHOOK_QUEUE

        queue = WEBHOOK_QUEUE
    _worker_task = asyncio.create_task(run_worker(queue))
    return _worker_task


def stop_worker() -> None:
    """Stop the background webhook worker."""
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        _worker_task = None
