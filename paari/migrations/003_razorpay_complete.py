"""Migration 003: Complete Razorpay payment tables.

Idempotent — checks for table/column existence before altering.
Run with: python -m paari.migrations.003_razorpay_complete
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION_SQL = """
-- Payment events table
CREATE TABLE IF NOT EXISTS payment_events (
    id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

-- Webhook events table (extended with event_id for Razorpay dedup)
CREATE TABLE IF NOT EXISTS webhook_events (
    id TEXT PRIMARY KEY,
    event_id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    merchant_id TEXT,
    topic TEXT NOT NULL,
    webhook_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    status TEXT DEFAULT 'PENDING',
    error TEXT,
    FOREIGN KEY (merchant_id) REFERENCES merchants(id),
    UNIQUE (source, webhook_id)
);

-- Add razorpay columns to transactions if not exists
ALTER TABLE transactions ADD COLUMN razorpay_order_id TEXT;
ALTER TABLE transactions ADD COLUMN razorpay_payment_id TEXT;
ALTER TABLE transactions ADD COLUMN payment_session_id TEXT;

-- Add agent_transactions_enabled to merchants if not exists
ALTER TABLE merchants ADD COLUMN agent_transactions_enabled INTEGER DEFAULT 1;
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
            col_def = " ".join(parts[4 if parts[3] == "TABLE" else 3:])
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
                print(f"Created table: {stmt.split('TABLE IF NOT EXISTS')[1].split('(')[0].strip()}")
            except sqlite3.OperationalError as e:
                print(f"Skipped (may already exist): {e}")
        else:
            try:
                cursor.execute(stmt)
            except sqlite3.OperationalError as e:
                print(f"Skipped: {e}")

    conn.commit()
    conn.close()
    print("Migration 003 complete.")


if __name__ == "__main__":
    run_migration()
