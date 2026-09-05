"""Database engine and session helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from paari.config import settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.db_url, echo=False, future=True)
        # SQLite write-concurrency: WAL lets readers run while a writer is
        # active, and busy_timeout makes writers wait for the lock instead of
        # failing fast with "database is locked" (server + webhook worker +
        # dashboard approvals + demo scripts can all touch paari.db at once).
        if _engine.dialect.name == "sqlite":
            from sqlalchemy import event

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
                cur = dbapi_connection.cursor()
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()
                cur = dbapi_connection.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.fetchone()  # PRAGMA journal_mode returns the resulting mode
                cur.close()
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _session_maker


async def init_db() -> None:
    """Create all tables from init.sql if they do not exist."""
    from pathlib import Path

    engine = get_engine()
    sql_path = Path(__file__).resolve().parent / "init.sql"
    sql = sql_path.read_text(encoding="utf-8")
    # SQLite executes one statement per call. Our schema has no '--' inside string
    # literals, so: strip line comments first, then split on ';'. (The header
    # comment contains a literal ';' which must not become a statement boundary.)
    cleaned_lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    cleaned_sql = "\n".join(cleaned_lines)
    pieces = [p.strip() for p in cleaned_sql.split(";") if p.strip()]
    async with engine.begin() as conn:
        for stmt in pieces:
            await conn.exec_driver_sql(stmt)


async def get_session() -> AsyncSession:
    """FastAPI dependency yielding a session per request."""
    maker = get_session_maker()
    async with maker() as session:
        yield session
