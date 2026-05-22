from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.config import Settings
from app.database import Database
from app.services.task_runner import TaskScheduler


class AppContextMiddleware(BaseMiddleware):
    def __init__(self, db: Database, settings: Settings, scheduler: TaskScheduler | None = None) -> None:
        self.db = db
        self.settings = settings
        self.scheduler = scheduler

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["settings"] = self.settings
        data["scheduler"] = self.scheduler
        return await handler(event, data)

