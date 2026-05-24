import asyncio
import logging
import re
from pymongo import ASCENDING
from dotenv import load_dotenv
load_dotenv()
from app.config import get_settings
from app.database import Database
from app.services.userbot import UserbotService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    settings = get_settings()
    db = Database(settings)
    await db.connect()
    logger.info("Database connected.")

    runtime = await db.get_runtime_settings()
    diskwala = runtime.get("diskwala", {})
    bot_username = diskwala.get("bot_username", "DiskWalaFileUploaderBot")
    if not diskwala.get("enabled"):
        logger.warning("Diskwala is not enabled in settings. Exiting.")
        return

    userbot = UserbotService(db, settings)
    client = await userbot.client()
    if not client:
        logger.error("Userbot is not logged in or configured.")
        return
    logger.info("Userbot connected.")

    query = {
        "storage_status": "stored",
        "storage_message_id": {"$ne": None},
        "storage_chat_id": {"$ne": None},
        "diskwala_link": {"$exists": False}
    }
    total = await db.col("media").count_documents(query)
    logger.info(f"Found {total} media items needing a Diskwala link.")

    cursor = db.col("media").find(query).sort("created_at", ASCENDING)
    
    success = 0
    failed = 0
    
    async for media in cursor:
        token = media["token"]
        storage_chat_id = media["storage_chat_id"]
        storage_message_id = media["storage_message_id"]
        
        try:
            # We need to resolve the storage chat. It's stored as int or str.
            chat_ref = storage_chat_id
            if isinstance(chat_ref, str) and chat_ref.lstrip("-").isdigit():
                chat_ref = int(chat_ref)
                
            msg = await client.get_messages(chat_ref, ids=storage_message_id)
            if not msg:
                logger.warning(f"Message {storage_message_id} in {storage_chat_id} not found for token {token}.")
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
                            match = re.search(r'(https?://[^\s]+diskwala\.com[^\s]+)', reply.text)
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
                    logger.info(f"[{success + failed}/{total}] Saved link {diskwala_link} for token {token}")
                else:
                    logger.warning(f"[{success + failed}/{total}] Failed to get link for token {token}")
                    failed += 1
        except Exception as e:
            logger.error(f"[{success + failed}/{total}] Error processing token {token}: {e}")
            failed += 1
            
        await asyncio.sleep(2) # Avoid hitting spam limits with the uploader bot
        
    logger.info(f"Finished backfilling. Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    asyncio.run(main())
