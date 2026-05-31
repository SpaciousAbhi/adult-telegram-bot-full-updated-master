from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from app.config import Settings


def is_admin_id(user_id: int | None, settings: Settings) -> bool:
    return user_id is not None and int(user_id) in settings.manager_ids


async def reject_message_if_not_admin(message: Message, settings: Settings) -> bool:
    if is_admin_id(message.from_user.id if message.from_user else None, settings):
        return False
    await message.answer("🔒 <b>Admin Area</b>\nYou do not have access to this panel.")
    return True


async def reject_callback_if_not_admin(query: CallbackQuery, settings: Settings) -> bool:
    if is_admin_id(query.from_user.id if query.from_user else None, settings):
        return False
    await query.answer("Admin access only.", show_alert=True)
    return True
