from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.database import Database
from app.timeutils import utcnow

logger = logging.getLogger(__name__)


USER_TABLE_CANDIDATES = ("users", "user", "bot_users", "registered_users")
ID_COLUMN_CANDIDATES = ("telegram_id", "user_id", "chat_id", "id")


async def import_legacy_postgres_users(db: Database, postgres_url: str | None) -> int:
    if not postgres_url:
        return 0
    try:
        imported = await asyncio.to_thread(_read_sync, postgres_url)
    except Exception as exc:
        logger.warning("Legacy PostgreSQL user import skipped: %s", exc)
        return 0
    count = 0
    for doc in imported:
        await db.col("users").update_one(
            {"telegram_id": doc["telegram_id"]},
            {"$setOnInsert": {"first_seen_at": utcnow(), "plan": "free"}, "$set": doc},
            upsert=True,
        )
        count += 1
    if count:
        logger.info("Imported %s legacy PostgreSQL users", count)
    return count


def _read_sync(postgres_url: str) -> list[dict[str, Any]]:
    import psycopg

    imported: list[dict[str, Any]] = []
    with psycopg.connect(postgres_url) as conn:
        with conn.cursor() as cur:
            table, id_column = _find_user_table(cur)
            if not table or not id_column:
                logger.warning("No compatible legacy PostgreSQL users table found")
                return 0
            columns = _table_columns(cur, table)
            select_columns = [id_column]
            for optional in ("username", "first_name", "last_name"):
                if optional in columns:
                    select_columns.append(optional)
            quoted_cols = ", ".join(f'"{col}"' for col in select_columns)
            cur.execute(f'SELECT {quoted_cols} FROM "{table}" WHERE "{id_column}" IS NOT NULL')
            for row in cur.fetchall():
                user_id = _as_int(row[0])
                if not user_id:
                    continue
                doc = {
                    "telegram_id": user_id,
                    "legacy_postgres_imported": True,
                    "legacy_source_table": table,
                    "last_seen_at": utcnow(),
                }
                for index, column in enumerate(select_columns[1:], start=1):
                    doc[column] = row[index]
                imported.append(doc)
    return imported


def _find_user_table(cur: Any) -> tuple[str | None, str | None]:
    for table in USER_TABLE_CANDIDATES:
        columns = _table_columns(cur, table)
        if not columns:
            continue
        for column in ID_COLUMN_CANDIDATES:
            if column in columns:
                return table, column
    return None, None


def _table_columns(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
