from __future__ import annotations

from aiogram import Dispatcher

from app.routers import admin, start


def register_routers(dp: Dispatcher) -> None:
    dp.include_router(admin.router)
    dp.include_router(start.router)

