from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Any

from app.config import ConfigError, Settings
from app.database import Database
from app.timeutils import utcnow

try:
    from telethon import TelegramClient
    from telethon.errors import RPCError, SessionPasswordNeededError
    from telethon.sessions import StringSession
    from telethon.tl.custom.message import Message as TelethonMessage
except ImportError:  # pragma: no cover - dependency is installed in production
    TelegramClient = None
    RPCError = Exception
    SessionPasswordNeededError = Exception
    StringSession = None
    TelethonMessage = Any


class UserbotService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._client: Any | None = None

    async def session_doc(self) -> dict[str, Any]:
        return await self.db.col("userbot").find_one({"_id": "default"}) or {}

    async def is_logged_in(self) -> bool:
        doc = await self.session_doc()
        return bool(doc.get("session_string"))

    async def credentials(self) -> tuple[int | None, str | None]:
        doc = await self.session_doc()
        api_id = doc.get("api_id") or self.settings.api_id
        api_hash = doc.get("api_hash") or self.settings.api_hash
        return int(api_id) if api_id else None, api_hash

    async def has_credentials(self) -> bool:
        api_id, api_hash = await self.credentials()
        return api_id is not None and bool(api_hash)

    async def require_credentials(self) -> tuple[int, str]:
        api_id, api_hash = await self.credentials()
        if api_id is None or not api_hash:
            raise ConfigError("API ID and API Hash are required. Use Userbot Management to add them step by step.")
        return api_id, api_hash

    async def save_credentials(self, api_id: int, api_hash: str) -> None:
        await self.db.col("userbot").update_one(
            {"_id": "default"},
            {
                "$set": {
                    "api_id": int(api_id),
                    "api_hash": api_hash.strip(),
                    "updated_at": utcnow(),
                    "last_error": None,
                }
            },
            upsert=True,
        )

    async def save_session_string(self, session_string: str, phone: str | None = None) -> None:
        await self.db.col("userbot").update_one(
            {"_id": "default"},
            {
                "$set": {
                    "session_string": session_string.strip(),
                    "phone": phone,
                    "updated_at": utcnow(),
                    "last_error": None,
                }
            },
            upsert=True,
        )

    async def start_phone_login(self, phone: str) -> dict[str, str]:
        if TelegramClient is None or StringSession is None:
            raise ConfigError("Telethon is not installed")
        api_id, api_hash = await self.require_credentials()
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
            return {
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "session_string": client.session.save(),
            }
        finally:
            await client.disconnect()

    async def complete_phone_code(self, phone: str, code: str, phone_code_hash: str, session_string: str) -> bool:
        if TelegramClient is None or StringSession is None:
            raise ConfigError("Telethon is not installed")
        api_id, api_hash = await self.require_credentials()
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        try:
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            except SessionPasswordNeededError:
                await self.db.col("userbot").update_one(
                    {"_id": "default"},
                    {
                        "$set": {
                            "login_temp": {
                                "phone": phone,
                                "phone_code_hash": phone_code_hash,
                                "session_string": client.session.save(),
                            },
                            "updated_at": utcnow(),
                        }
                    },
                    upsert=True,
                )
                return False
            await self.save_session_string(client.session.save(), phone=phone)
            await self.db.col("userbot").update_one({"_id": "default"}, {"$unset": {"login_temp": ""}})
            return True
        finally:
            await client.disconnect()

    async def complete_password(self, password: str) -> None:
        if TelegramClient is None or StringSession is None:
            raise ConfigError("Telethon is not installed")
        api_id, api_hash = await self.require_credentials()
        doc = await self.session_doc()
        temp = doc.get("login_temp") or {}
        session_string = temp.get("session_string")
        if not session_string:
            raise ConfigError("No pending 2FA login is saved")
        client = TelegramClient(StringSession(session_string), api_id, api_hash)
        await client.connect()
        try:
            await client.sign_in(password=password)
            await self.save_session_string(client.session.save(), phone=temp.get("phone"))
            await self.db.col("userbot").update_one({"_id": "default"}, {"$unset": {"login_temp": ""}})
        finally:
            await client.disconnect()

    async def logout(self) -> None:
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        await self.db.col("userbot").update_one(
            {"_id": "default"},
            {"$set": {"session_string": None, "phone": None, "updated_at": utcnow()}},
            upsert=True,
        )

    async def client(self) -> Any | None:
        if TelegramClient is None or StringSession is None:
            await self._set_error("Telethon is not installed")
            return None
        try:
            api_id, api_hash = await self.require_credentials()
        except ConfigError as exc:
            await self._set_error(str(exc))
            return None
        doc = await self.session_doc()
        session_string = doc.get("session_string")
        if not session_string:
            await self._set_error("Userbot session is not logged in")
            return None
        if self._client and self._client.is_connected():
            return self._client
        try:
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                await self._set_error("Saved userbot session is not authorized")
                return None
            self._client = client
            await self._set_error(None)
            return client
        except (ConfigError, RPCError, OSError) as exc:
            await self._set_error(str(exc))
            return None

    async def _set_error(self, message: str | None) -> None:
        await self.db.col("userbot").update_one(
            {"_id": "default"},
            {"$set": {"last_error": message, "updated_at": utcnow()}},
            upsert=True,
        )


def message_has_video(message: Any) -> bool:
    if getattr(message, "video", None):
        return True
    document = getattr(message, "document", None)
    mime = getattr(document, "mime_type", "") if document else ""
    return bool(mime and mime.startswith("video/"))


def message_fingerprint(message: Any) -> str:
    document = getattr(message, "document", None)
    if document and getattr(document, "id", None):
        size = getattr(document, "size", 0) or 0
        unique_id = getattr(document, "file_unique_id", None) or getattr(document, "id", None)
        return f"tgdoc:{unique_id}:{size}"
    chat_id = getattr(getattr(message, "peer_id", None), "channel_id", None) or getattr(message, "chat_id", "")
    return f"msg:{chat_id}:{message.id}"


def message_video_info(message: Any) -> dict[str, Any]:
    document = getattr(message, "document", None)
    size = getattr(document, "size", None)
    duration = None
    if document:
        for attr in getattr(document, "attributes", []) or []:
            if hasattr(attr, "duration"):
                duration = int(getattr(attr, "duration") or 0)
                break
    return {"size": size, "duration": duration}


# Try to import cv2 gracefully
try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger(__name__)


def get_frame_quality(frame: Any) -> float:
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = gray.mean()
        # Ensure average brightness is in a reasonable range (not black, not white)
        if mean_brightness < 40 or mean_brightness > 220:
            return 0.0
        
        # Blurriness: variance of the Laplacian (higher is sharper)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Contrast: standard deviation (higher is more contrasty/detailed)
        std_dev = gray.std()
        if std_dev < 15:
            return 0.0
            
        return laplacian_var * std_dev
    except Exception:
        return 0.0


async def download_thumbnail_bytes(message: Any) -> bytes | None:
    # 1. Try to generate a high quality frame from the video using OpenCV
    if cv2 is not None and message_has_video(message):
        try:
            client = getattr(message, "_client", None)
            if client:
                # Determine how much to download.
                # If the video size is < 25MB, download it completely.
                # Otherwise, download the first 15MB.
                max_bytes = 15 * 1024 * 1024
                doc_size = getattr(getattr(message, "document", None), "size", 0) or 0
                if isinstance(doc_size, int) and doc_size > 0 and doc_size < 25 * 1024 * 1024:
                    max_bytes = doc_size
                
                fd, temp_path = tempfile.mkstemp(suffix=".mp4")
                try:
                    downloaded_bytes = 0
                    with os.fdopen(fd, "wb") as f:
                        async for chunk in client.iter_download(message.media, chunk_size=256 * 1024):
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            if downloaded_bytes >= max_bytes:
                                break
                    
                    if downloaded_bytes > 0:
                        cap = cv2.VideoCapture(temp_path)
                        if cap.isOpened():
                            best_frame = None
                            best_score = -1.0
                            fallback_frame = None
                            frame_idx = 0
                            success, frame = cap.read()
                            
                            # Read up to 150 frames to find the best quality one
                            while success and frame_idx < 150:
                                if fallback_frame is None:
                                    fallback_frame = frame.copy()
                                
                                # Skip first 10 frames to avoid initial black screens or logo transitions
                                if frame_idx >= 10:
                                    score = get_frame_quality(frame)
                                    if score > best_score:
                                        best_score = score
                                        best_frame = frame.copy()
                                
                                success, frame = cap.read()
                                frame_idx += 1
                                
                            cap.release()
                            
                            final_frame = best_frame if best_frame is not None else fallback_frame
                            if final_frame is not None:
                                # Encode to JPEG with high quality (95)
                                success, encoded_image = cv2.imencode(
                                    ".jpg", 
                                    final_frame, 
                                    [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                                )
                                if success:
                                    logger.info(
                                        "Successfully extracted high-quality frame from video. Quality score: %s", 
                                        best_score
                                    )
                                    return encoded_image.tobytes()
                finally:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("Failed to extract frame using OpenCV: %s. Falling back to Telegram thumbs.", exc)

    # 2. Fallback: Download the highest quality thumbnail provided by Telegram (excluding stripped/empty sizes)
    try:
        document = getattr(message, "document", None)
        thumbs = getattr(document, "thumbs", None) if document else None
        if not thumbs:
            photo = getattr(message, "photo", None)
            thumbs = getattr(photo, "sizes", None) if photo else None

        thumb_to_download: Any = 0
        if thumbs:
            # Filter out non-downloadable stripped thumbnails
            downloadable_thumbs = [
                t for t in thumbs 
                if t and type(t).__name__ not in ("PhotoStrippedSize", "PhotoSizeEmpty")
            ]
            if downloadable_thumbs:
                # Choose the one with the largest resolution area
                def get_thumb_score(t: Any) -> int:
                    w = getattr(t, "w", 0) or 0
                    h = getattr(t, "h", 0) or 0
                    return w * h

                thumb_to_download = max(downloadable_thumbs, key=get_thumb_score)

        buffer = io.BytesIO()
        result = await message.download_media(file=buffer, thumb=thumb_to_download)
        if result is not None:
            logger.info("Successfully downloaded Telegram fallback thumbnail")
            return buffer.getvalue() or None
    except Exception as exc:
        logger.exception("Failed to download fallback Telegram thumbnail: %s", exc)

    return None




