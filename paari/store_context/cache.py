"""In-process store context cache with TTL.

The cache is a dict keyed by merchant_id. Each entry stores the full
payload_json + fetched_at + source. TTL is configurable via
PAARI_STORE_CONTEXT_TTL_SECONDS (default 900 = 15 min).
"""

from __future__ import annotations

import time
from typing import Any

from paari.config import settings

_cache: dict[str, dict[str, Any]] = {}


def get_cached(merchant_id: str) -> dict[str, Any] | None:
    """Return cached context if fresh, else None."""
    entry = _cache.get(merchant_id)
    if entry is None:
        return None
    age = time.time() - entry["fetched_at_ts"]
    if age > settings.store_context_ttl_seconds:
        _cache.pop(merchant_id, None)
        return None
    return entry


def set_cached(merchant_id: str, payload: dict[str, Any], source: str) -> None:
    """Store context in the in-process cache."""
    _cache[merchant_id] = {
        "payload": payload,
        "source": source,
        "fetched_at_ts": time.time(),
    }


def invalidate(merchant_id: str | None = None) -> None:
    """Invalidate one or all cached entries."""
    if merchant_id is None:
        _cache.clear()
    else:
        _cache.pop(merchant_id, None)


async def persist_to_db(merchant_id: str, payload: dict[str, Any], source: str) -> None:
    """Persist context to the store_contexts table."""
    import json

    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        await session.execute(
            text(
                "INSERT OR REPLACE INTO store_contexts (merchant_id, payload_json, fetched_at, source) "
                "VALUES (:mid, :payload, CURRENT_TIMESTAMP, :source)"
            ),
            {"mid": merchant_id, "payload": json.dumps(payload), "source": source},
        )
        await session.commit()


async def load_from_db(merchant_id: str) -> dict[str, Any] | None:
    """Load context from the store_contexts table."""
    import json

    from sqlalchemy import text

    from paari.db.engine import get_session_maker

    maker = get_session_maker()
    async with maker() as session:
        row = (
            await session.execute(
                text(
                    "SELECT payload_json, fetched_at, source FROM store_contexts WHERE merchant_id = :mid"
                ),
                {"mid": merchant_id},
            )
        ).first()
        if row is None:
            return None
        return {
            "payload": json.loads(row.payload_json),
            "fetched_at": row.fetched_at,
            "source": row.source,
        }
