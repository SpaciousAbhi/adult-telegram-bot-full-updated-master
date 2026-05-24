import asyncio
import logging
import re
from pymongo import ASCENDING
from app.database import Database
from app.services.userbot import UserbotService
from app.config import Settings
from aiogram import Bot

logger = logging.getLogger(__name__)

async def run_diskwala_backfill(db: Database, settings: Settings, bot: Bot, admin_id: int):
    try:
        await bot.send_message(admin_id, "🔄 Starting Diskwala backfill in the background. This may take a while depending on how many old videos you have.")
        
        runtime = await db.get_runtime_settings()
        diskwala = runtime.get("diskwala", {})
        bot_username = diskwala.get("bot_username", "DiskWalaFileUploaderBot")
        if not diskwala.get("enabled"):
            await bot.send_message(admin_id, "⚠️ Diskwala is not enabled. Please enable it in the admin panel first.")
            return

        userbot = UserbotService(db, settings)
        client = await userbot.client()
        if not client:
            await bot.send_message(admin_id, "⚠️ Userbot is not logged in. Cannot run backfill.")
            return

        query = {
            "storage_status": "stored",
            "storage_message_id": {"$ne": None},
            "storage_chat_id": {"$ne": None},
            "diskwala_link": {"$exists": False}
        }
        total = await db.col("media").count_documents(query)
        if total == 0:
            await bot.send_message(admin_id, "✅ All old videos already have Diskwala links!")
            return

        await bot.send_message(admin_id, f"Found {total} videos missing Diskwala links. Processing...")

        # Pre-fetch all IDs to avoid CursorNotFound timeout on long runs
        cursor = db.col("media").find(query, {"_id": 1}).sort("created_at", ASCENDING)
        media_ids = [doc["_id"] async for doc in cursor]
        
        success = 0
        failed = 0
        
        for media_id in media_ids:
            media = await db.col("media").find_one({"_id": media_id})
            if not media:
                continue
                
            token = media["token"]
            storage_chat_id = media["storage_chat_id"]
            storage_message_id = media["storage_message_id"]
            
            try:
                chat_ref = storage_chat_id
                if isinstance(chat_ref, str) and chat_ref.lstrip("-").isdigit():
                    chat_ref = int(chat_ref)
                    
                msg = await client.get_messages(chat_ref, ids=storage_message_id)
                if not msg:
                    failed += 1
                    continue
                    
                async with client.conversation(bot_username, timeout=15) as conv:
                    await conv.send_message(msg)
                    end_time = asyncio.get_event_loop().time() + 12
                    diskwala_link = None
                    while asyncio.get_event_loop().time() < end_time:
                        try:
                            reply = await conv.get_response(timeout=3)
                            if reply and reply.text and "diskwala.com" in reply.text:
                                match = re.search(r'(https?://[^\s]*diskwala\.com[^\s]+)', reply.text)
                                if match:
                                    diskwala_link = match.group(1)
                                    break
                        except asyncio.TimeoutError:
                            continue
                    
                    if diskwala_link:
                        await db.col("media").update_one(
                            {"_id": media["_id"]},
                            {"$set": {"diskwala_link": diskwala_link}}
                        )
                        success += 1
                    else:
                        failed += 1
            except Exception as e:
                logger.error(f"Error backfilling token {token}: {e}")
                failed += 1
                
            await asyncio.sleep(2)
            
        await bot.send_message(admin_id, f"✅ Backfill finished!\n\nSuccessfully linked: {success}\nFailed: {failed}")

    except Exception as e:
        logger.exception("Backfill task error")
        await bot.send_message(admin_id, f"❌ Backfill task crashed: {e}")
