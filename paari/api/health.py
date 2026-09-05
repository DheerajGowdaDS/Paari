"""Health check endpoint.

GET /api/v1/health — reports adapter mode, store context freshness,
webhook worker status, and DB ping.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/v1/health")
async def health_check() -> dict:
    """Comprehensive health check."""
    from paari.config import settings
    from paari.store_context import cache as ctx_cache

    # DB ping
    db_ok = False
    try:
        from sqlalchemy import text

        from paari.db.engine import get_session_maker

        maker = get_session_maker()
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    # Webhook worker status
    from paari.webhooks.worker import _worker_task

    webhook_worker_running = _worker_task is not None and not _worker_task.done()

    # Store context freshness
    cached = ctx_cache.get_cached("MER-001")
    context_fresh = cached is not None

    return {
        "status": "ok" if db_ok else "degraded",
        "adapter_mode": settings.shopify_mode,
        "db_connected": db_ok,
        "webhook_worker_running": webhook_worker_running,
        "store_context_fresh": context_fresh,
        "shopify_domain": settings.shopify_domain,
    }
