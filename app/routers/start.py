from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatJoinRequest, ChatMemberUpdated, Message

from app.callbacks import FORCE_VERIFY
from app.config import Settings
from app.database import Database
from app.services.delivery import DeliveryService
from app.services.force_subscription import JOINED_STATUSES, ForceSubscriptionService, member_status_value
from app.services.referrals import ReferralService
from app.ui import keyboards, text


router = Router(name="start")


@router.message(CommandStart())
async def start_command(
    message: Message,
    command: CommandObject,
    db: Database,
    bot: Bot,
    settings: Settings,
) -> None:
    args = command.args or ""
    referred_by = None
    token = None
    if args.startswith("get_"):
        token = args.removeprefix("get_")
    elif args.startswith("ref_"):
        try:
            referred_by = int(args.removeprefix("ref_"))
        except ValueError:
            referred_by = None
    user = await db.upsert_user(message.from_user, referred_by=referred_by)
    if token:
        await db.set_pending_action(message.from_user.id, {"type": "deliver", "token": token})
    await send_user_entry(message, db, bot, settings, user_id=message.from_user.id)


async def send_user_entry(
    message: Message,
    db: Database,
    bot: Bot,
    settings: Settings,
    user_id: int,
) -> None:
    missing = await ForceSubscriptionService(db, bot).missing_targets(user_id)
    if missing:
        await message.answer(text.force_required(missing), reply_markup=keyboards.force_user_keyboard(missing))
        return

    user = await db.get_user(user_id) or {}
    pending = user.get("pending_action") or {}
    if pending.get("type") == "deliver" and pending.get("token"):
        await db.set_pending_action(user_id, None)
        await DeliveryService(db, bot, settings).deliver(pending["token"], user_id, message.chat.id)
        return

    runtime = await db.get_runtime_settings()
    await message.answer(text.user_home(runtime.get("destination_channels") or []))


@router.callback_query(F.data == FORCE_VERIFY)
async def verify_force_subscription(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    await query.answer("Checking access...")
    missing = await ForceSubscriptionService(db, bot).missing_targets(query.from_user.id)
    if missing:
        await query.message.edit_text(
            text.force_required(missing),
            reply_markup=keyboards.force_user_keyboard(missing),
        )
        return

    user = await db.get_user(query.from_user.id) or {}
    pending = user.get("pending_action") or {}
    await db.set_pending_action(query.from_user.id, None)
    if pending.get("type") == "deliver" and pending.get("token"):
        await DeliveryService(db, bot, settings).deliver(pending["token"], query.from_user.id, query.message.chat.id)
        return
    runtime = await db.get_runtime_settings()
    await query.message.edit_text(text.user_home(runtime.get("destination_channels") or []))


@router.chat_join_request()
async def chat_join_request(update: ChatJoinRequest, db: Database, bot: Bot) -> None:
    invite = update.invite_link.invite_link if update.invite_link else None
    await ForceSubscriptionService(db, bot).record_join_request(update.chat.id, update.from_user.id, invite)
    await ReferralService(db, bot).record_join(invite, update.from_user.id)


@router.chat_member()
async def chat_member_update(update: ChatMemberUpdated, db: Database, bot: Bot) -> None:
    if member_status_value(update.new_chat_member) not in JOINED_STATUSES:
        return
    invite = update.invite_link.invite_link if update.invite_link else None
    await ReferralService(db, bot).record_join(invite, update.from_user.id)
