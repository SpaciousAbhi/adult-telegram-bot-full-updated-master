import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from app.services.task_runner import TaskScheduler

class PostingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_destination_posting_uses_thumbnail_bytes(self):
        db = MagicMock()
        settings = MagicMock()
        bot = AsyncMock()
        
        scheduler = TaskScheduler(db, settings, bot)
        
        fake_thumbnail_bytes = b"fake_jpeg_image_bytes"
        media_doc = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000005"),
            "token": "testtoken123",
            "fingerprint": "testfingerprint",
            "storage_message_id": 12345,
            "thumbnail_bytes": fake_thumbnail_bytes,
            "posted_destination_chat_ids": []
        }
        
        mock_cursor = MagicMock()
        async def mock_cursor_iterator(*args, **kwargs):
            yield media_doc
        mock_cursor.__aiter__ = mock_cursor_iterator
        db.col.return_value.find.return_value.sort.return_value.limit.return_value = mock_cursor
        
        db.col.return_value.find_one = AsyncMock(return_value=None)
        db.col.return_value.update_one = AsyncMock()
        db.col.return_value.count_documents = AsyncMock(return_value=1)
        
        scheduler._bot_username = "test_bot"
        
        task = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000006"),
            "name": "Test Task"
        }
        destinations = [{"chat_id": -100987654321, "status": "active"}]
        runtime = {}
        
        posted, errors = await scheduler.post_stored_to_destinations(task, destinations, runtime, limit=1)
        
        self.assertEqual(posted, 1)
        self.assertEqual(len(errors), 0)
        
        bot.send_photo.assert_called_once()
        call_kwargs = bot.send_photo.call_args[1]
        
        self.assertEqual(call_kwargs["chat_id"], -100987654321)
        self.assertEqual(call_kwargs["has_spoiler"], True)
        
        photo_file = call_kwargs["photo"]
        self.assertEqual(photo_file.data, fake_thumbnail_bytes)
        self.assertEqual(photo_file.filename, "thumbnail.jpg")

if __name__ == "__main__":
    unittest.main()
