"""Tests for paari.webhooks.queue — async webhook event queue."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_queue_put_and_get() -> None:
    from paari.webhooks.queue import WebhookEvent, WebhookQueue

    q = WebhookQueue()
    event = WebhookEvent(
        event_id="evt-1",
        source="SHOPIFY",
        merchant_id="MER-001",
        topic="orders/create",
        webhook_id="wh-1",
        payload={"id": "order-1"},
    )
    put_result = await q.put(event)
    assert put_result is True
    assert q.qsize == 1

    got = await q.get()
    assert got.event_id == "evt-1"
    assert got.topic == "orders/create"
    q.task_done()


@pytest.mark.asyncio
async def test_queue_dedup() -> None:
    from paari.webhooks.queue import WebhookEvent, WebhookQueue

    q = WebhookQueue()
    event = WebhookEvent(
        event_id="evt-dedup",
        source="SHOPIFY",
        merchant_id=None,
        topic="orders/create",
        webhook_id="wh-dedup",
        payload={},
    )
    assert await q.put(event) is True
    assert await q.put(event) is False  # duplicate
    assert q.qsize == 1


@pytest.mark.asyncio
async def test_queue_qsize() -> None:
    from paari.webhooks.queue import WebhookEvent, WebhookQueue

    q = WebhookQueue()
    assert q.qsize == 0
    await q.put(
        WebhookEvent(
            event_id="evt-q1",
            source="SHOPIFY",
            merchant_id=None,
            topic="test",
            webhook_id="wh-q1",
            payload={},
        )
    )
    assert q.qsize == 1


def test_global_queue_singleton() -> None:
    from paari.webhooks.queue import WEBHOOK_QUEUE, get_webhook_queue

    assert get_webhook_queue() is WEBHOOK_QUEUE
