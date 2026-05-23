from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
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


def format_welcome_message(missing_dests: list[dict[str, Any]]) -> str:
    if missing_dests:
        return (
            "Welcome to the Premium Bot! 👋\n\n"
            "Enjoy access to all the free channels where premium videos and files are being uploaded daily.\n\n"
            "Here are our free content channels you can join:"
        )
    return (
        "Welcome to the Premium Bot! 👋\n\n"
        "Enjoy access to all the free channels where premium videos and files are being uploaded daily.\n\n"
        "You have joined all our free content channels! Keep enjoying the daily uploads."
    )


async def send_user_entry(
    message: Message,
    db: Database,
    bot: Bot,
    settings: Settings,
    user_id: int,
) -> None:
    force_service = ForceSubscriptionService(db, bot)
    missing_force = await force_service.missing_targets(user_id)
    
    if missing_force:
        welcome_text = (
            "Complete required access first.\n\n"
            "Only unfinished channels are shown below. Join or send the request, then press Verify Access."
        )
        await message.answer(
            welcome_text,
            reply_markup=keyboards.force_user_keyboard(missing_force)
        )
        return

    user = await db.get_user(user_id) or {}
    pending = user.get("pending_action") or {}
    if pending.get("type") == "deliver" and pending.get("token"):
        await db.set_pending_action(user_id, None)
        await DeliveryService(db, bot, settings).deliver(pending["token"], user_id, message.chat.id)
        return

    runtime = await db.get_runtime_settings()
    destinations = runtime.get("destination_channels") or []
    missing_dests = await force_service.missing_destinations(user_id, destinations)

    welcome_joined = format_welcome_message(missing_dests)
    await message.answer(
        welcome_joined,
        reply_markup=keyboards.user_unjoined_destinations_keyboard(missing_dests)
    )


@router.callback_query(F.data == FORCE_VERIFY)
async def verify_force_subscription(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    await query.answer("Checking access...")
    user_id = query.from_user.id
    force_service = ForceSubscriptionService(db, bot)
    missing_force = await force_service.missing_targets(user_id)
    
    if missing_force:
        welcome_text = (
            "Complete required access first.\n\n"
            "Only unfinished channels are shown below. Join or send the request, then press Verify Access."
        )
        try:
            await query.message.edit_text(
                welcome_text,
                reply_markup=keyboards.force_user_keyboard(missing_force),
            )
        except Exception:
            pass
        return

    user = await db.get_user(user_id) or {}
    pending = user.get("pending_action") or {}
    await db.set_pending_action(user_id, None)
    if pending.get("type") == "deliver" and pending.get("token"):
        await DeliveryService(db, bot, settings).deliver(pending["token"], user_id, query.message.chat.id)
        return
        
    runtime = await db.get_runtime_settings()
    destinations = runtime.get("destination_channels") or []
    missing_dests = await force_service.missing_destinations(user_id, destinations)
    
    welcome_joined = format_welcome_message(missing_dests)
    try:
        await query.message.edit_text(
            welcome_joined, 
            reply_markup=keyboards.user_unjoined_destinations_keyboard(missing_dests)
        )
    except Exception:
        pass


@router.callback_query(F.data == "user_home")
async def user_home_callback(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    await query.answer()
    user_id = query.from_user.id
    force_service = ForceSubscriptionService(db, bot)
    missing_force = await force_service.missing_targets(user_id)
    
    if missing_force:
        welcome_text = (
            "Complete required access first.\n\n"
            "Only unfinished channels are shown below. Join or send the request, then press Verify Access."
        )
        try:
            await query.message.edit_text(
                welcome_text,
                reply_markup=keyboards.force_user_keyboard(missing_force),
            )
        except Exception:
            pass
        return
        
    runtime = await db.get_runtime_settings()
    destinations = runtime.get("destination_channels") or []
    missing_dests = await force_service.missing_destinations(user_id, destinations)
    
    welcome_joined = format_welcome_message(missing_dests)
    try:
        await query.message.edit_text(
            welcome_joined, 
            reply_markup=keyboards.user_unjoined_destinations_keyboard(missing_dests)
        )
    except Exception:
        pass


@router.message(Command("referral"))
@router.message(Command("ref"))
async def referral_command(message: Message, db: Database, bot: Bot, settings: Settings) -> None:
    await send_referral_details(message, db, bot, message.from_user.id)


@router.callback_query(F.data == "user_referral")
async def referral_callback(query: CallbackQuery, db: Database, bot: Bot, settings: Settings) -> None:
    await query.answer()
    await send_referral_details(query.message, db, bot, query.from_user.id, edit_message=True)


async def send_referral_details(
    message: Message,
    db: Database,
    bot: Bot,
    user_id: int,
    edit_message: bool = False,
) -> None:
    runtime = await db.get_runtime_settings()
    referral = runtime.get("referral") or {}
    
    referral_link = await ReferralService(db, bot).get_or_create_link(user_id)
    referrals_count = await db.col("referral_events").count_documents({"referrer_id": int(user_id)})
    
    required_joins = int(referral.get("required_joins") or 10)
    reward_limit = int(referral.get("reward_limit") or 100)
    reward_days = int(referral.get("reward_days") or 5)
    
    user = await db.get_user(user_id) or {}
    
    from app.services.access import is_until_active
    from app.timeutils import utcnow
    now = utcnow()
    
    if user.get("referral_reward_until") and is_until_active(user.get("referral_reward_until"), now):
        expires_at = user.get("referral_reward_until")
        date_str = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        status_text = f"✅ Active (Reward limit: {reward_limit} daily until {date_str})"
    else:
        status_text = "❌ Inactive (Standard limit applies)"

    if not referral_link:
        msg_text = (
            "👥 *Referral Program*\n\n"
            "⚠️ The referral program is currently disabled by the administrator (no referral channel is set)."
        )
        markup = keyboards.mk([[keyboards.btn("◀️ Back", "user_home")]])
    else:
        import urllib.parse
        share_text = "Join this amazing bot to get premium videos for free! 🔥"
        share_url = f"https://t.me/share/url?url={urllib.parse.quote(referral_link)}&text={urllib.parse.quote(share_text)}"
        
        msg_text = (
            "👥 *Bot Referral Program*\n\n"
            "Invite your friends using your personal link and unlock **Premium access**!\n\n"
            "*How it works:*\n"
            "1. Share your invite link with your friends.\n"
            "2. When they join our channel through your link, it counts as a referral.\n"
            "3. Once you reach **{required} referrals**, your account is automatically upgraded to **{limit} daily downloads** for **{days} days**!\n\n"
            "📈 *Your Statistics:*\n"
            "• **Total Referrals:** `{count}` / `{required}`\n"
            "• **Status:** {status}\n\n"
            "🔗 *Your Invite Link:*\n"
            "`{link}`"
        ).format(
            required=required_joins,
            limit=reward_limit,
            days=reward_days,
            count=referrals_count,
            status=status_text,
            link=referral_link,
        )
        
        markup = keyboards.mk([
            [keyboards.url_btn("📲 Share Link", share_url)],
            [keyboards.btn("◀️ Back", "user_home")]
        ])

    if edit_message:
        try:
            await message.edit_text(msg_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            await message.answer(msg_text, reply_markup=markup, parse_mode="Markdown")
    else:
        await message.answer(msg_text, reply_markup=markup, parse_mode="Markdown")


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
