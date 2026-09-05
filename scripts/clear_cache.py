"""Clear the store context cache and DB so the next probe fetches fresh live data."""
from __future__ import annotations
import asyncio
from paari.store_context import cache as ctx_cache
from paari.db.engine import get_session_maker
from sqlalchemy import text

async def purge() -> None:
    ctx_cache.invalidate()
    maker = get_session_maker()
    async with maker() as s:
        await s.execute(text('DELETE FROM store_contexts'))
        await s.commit()
    print("cache and store_contexts table cleared")

asyncio.run(purge())
