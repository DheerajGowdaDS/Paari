import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    db_path = Path("tests/_test_gov_debug.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False, future=True)
    sql = Path("paari/db/init.sql").read_text(encoding="utf-8")
    cleaned = "\n".join(l.split("--", 1)[0] for l in sql.splitlines())
    pieces = [p.strip() for p in cleaned.split(";") if p.strip()]
    async with engine.begin() as conn:
        for stmt in pieces:
            await conn.exec_driver_sql(stmt)
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
        print("tables:", [r[0] for r in rows])
    db_path.unlink()

asyncio.run(main())
