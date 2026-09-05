"""Phase 2 migration: Add A2A columns and idempotency_keys table.

Revision ID: 004_agents_a2a
Create Date: 2026-09-03

Adds:
- a2a_endpoint column to agents table
- idempotency_keys table
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from paari.db.engine import get_engine


async def upgrade(connection: AsyncConnection) -> None:
    """Add a2a_endpoint column to agents and create idempotency_keys table."""
    inspector = connection.sync_connection.schema_editor().inspector
    agent_columns = [col["name"] for col in inspector.get_columns("agents")]

    if "a2a_endpoint" not in agent_columns:
        await connection.execute(
            text("ALTER TABLE agents ADD COLUMN a2a_endpoint TEXT")
        )
        print("Added a2a_endpoint column to agents table")

    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key             TEXT        NOT NULL,
                agent_id        CHAR(36)    NOT NULL,
                action          VARCHAR(64) NOT NULL,
                response_json   TEXT        NOT NULL,
                created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (key)
            )
            """
        )
    )
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_idempotency_agent ON idempotency_keys(agent_id, action)"
        )
    )
    print("Created idempotency_keys table and index")


async def downgrade(connection: AsyncConnection) -> None:
    """Remove a2a_endpoint column and idempotency_keys table."""
    await connection.execute(text("DROP TABLE IF EXISTS idempotency_keys"))
    await connection.execute(
        text("ALTER TABLE agents DROP COLUMN IF EXISTS a2a_endpoint")
    )
    print("Dropped idempotency_keys table and a2a_endpoint column")


if __name__ == "__main__":
    import asyncio

    async def run():
        engine = get_engine()
        async with engine.begin() as conn:
            await upgrade(conn)
            await conn.commit()

    asyncio.run(run())
