from __future__ import annotations

from typing import Any

from app.database import Database
from app.timeutils import utcnow


class AdminStateStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def set(self, admin_id: int, name: str, payload: dict[str, Any] | None = None) -> None:
        await self.db.col("admin_states").update_one(
            {"admin_id": int(admin_id)},
            {
                "$set": {
                    "admin_id": int(admin_id),
                    "name": name,
                    "payload": payload or {},
                    "updated_at": utcnow(),
                }
            },
            upsert=True,
        )

    async def get(self, admin_id: int) -> dict[str, Any] | None:
        return await self.db.col("admin_states").find_one({"admin_id": int(admin_id)})

    async def clear(self, admin_id: int) -> None:
        await self.db.col("admin_states").delete_one({"admin_id": int(admin_id)})

