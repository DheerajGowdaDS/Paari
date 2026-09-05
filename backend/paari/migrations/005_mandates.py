"""Migration 005: mandate-based autonomous charging tables.

Idempotent — checks for table/column existence before altering.
Run with: python -m paari.migrations.005_mandates
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS mandates (
    id                      CHAR(36)     NOT NULL,
    display_id              VARCHAR(32)  UNIQUE,
    user_id                 CHAR(36)     NOT NULL,
    provider                VARCHAR(32)  NOT NULL DEFAULT 'RAZORPAY',
    instrument_reference    VARCHAR(128) NOT NULL,
    status                  VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    max_per_transaction     BIGINT       NOT NULL,
    daily_limit             BIGINT       NOT NULL,
    allowed_merchants_json  TEXT         NOT NULL DEFAULT '[]',
    allowed_categories_json TEXT         NOT NULL DEFAULT '[]',
    autonomous_enabled      INTEGER      NOT NULL DEFAULT 1,
    requires_review_above   BIGINT       NOT NULL DEFAULT 0,
    expires_at              TIMESTAMP,
    created_at              TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_mandates_user_status ON mandates(user_id, status);

CREATE TABLE IF NOT EXISTS mandate_daily_usage (
    mandate_id  CHAR(36) NOT NULL,
    day         CHAR(10) NOT NULL,
    used_paise  BIGINT   NOT NULL DEFAULT 0,
    PRIMARY KEY (mandate_id, day),
    FOREIGN KEY (mandate_id) REFERENCES mandates(id)
);

ALTER TABLE transactions ADD COLUMN mandate_id CHAR(36);
"""


def get_db_path() -> Path:
    from paari.config import settings

    db_url = settings.db_url
    if db_url.startswith("sqlite"):
        return Path(db_url.replace("sqlite+aiosqlite:///", ""))
    return Path("paari.db")


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def run_migration() -> None:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    statements = [s.strip() for s in MIGRATION_SQL.split(";") if s.strip()]

    for stmt in statements:
        if not stmt or stmt.startswith("--"):
            continue
        if stmt.startswith("ALTER TABLE"):
            parts = stmt.split()
            table = parts[2]
            col_def = " ".join(parts[4 if parts[3] == "TABLE" else 3 :])
            if "ADD COLUMN" in stmt:
                col_name = col_def.split()[2] if "ADD COLUMN" in stmt else ""
                if col_name and not column_exists(cursor, table, col_name):
                    try:
                        cursor.execute(stmt)
                        print(f"Migrated: {stmt[:60]}...")
                    except sqlite3.OperationalError as e:
                        print(f"Skipped (may already exist): {e}")
        elif stmt.startswith("CREATE TABLE"):
            try:
                cursor.execute(stmt)
                print(
                    f"Created table: {stmt.split('TABLE IF NOT EXISTS')[1].split('(')[0].strip()}"
                )
            except sqlite3.OperationalError as e:
                print(f"Skipped (may already exist): {e}")
        else:
            try:
                cursor.execute(stmt)
            except sqlite3.OperationalError as e:
                print(f"Skipped: {e}")

    conn.commit()
    conn.close()
    print("Migration 005 complete.")


if __name__ == "__main__":
    run_migration()
