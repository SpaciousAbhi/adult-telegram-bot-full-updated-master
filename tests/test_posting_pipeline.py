import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from app.services.task_runner import TaskScheduler

class PostingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_destination_caption_is_premium_and_scannable(self):
        scheduler = TaskScheduler(MagicMock(), MagicMock(), AsyncMock())

        caption = scheduler.destination_caption({"duration": 120, "size": 25 * 1024 * 1024})

        self.assertIn("Premium Video Drop", caption)
        self.assertIn("Duration: <code>2m</code>", caption)
        self.assertIn("Size: <code>25.00 MB</code>", caption)
        self.assertLess(len(caption), 1024)

    async def test_destination_posting_downloads_thumbnail_on_the_fly(self):
        db = MagicMock()
        settings = MagicMock()
        bot = AsyncMock()
        
        scheduler = TaskScheduler(db, settings, bot)
        
        media_doc = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000005"),
            "token": "testtoken123",
            "fingerprint": "testfingerprint",
            "storage_chat_id": -100123456789,
            "storage_message_id": 12345,
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
        
        client = AsyncMock()
        fake_msg = MagicMock()
        client.get_messages = AsyncMock(return_value=fake_msg)
        
        with patch("app.services.task_runner.download_thumbnail_bytes", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"fake_jpeg_image_bytes"
            
            posted, errors = await scheduler.post_stored_to_destinations(task, destinations, runtime, limit=1, client=client)
            
            self.assertEqual(posted, 1)
            self.assertEqual(len(errors), 0)
            
            client.get_messages.assert_called_once_with(-100123456789, ids=12345)
            mock_download.assert_called_once_with(fake_msg)
            
            bot.send_photo.assert_called_once()
            call_kwargs = bot.send_photo.call_args[1]
            self.assertEqual(call_kwargs["chat_id"], -100987654321)
            self.assertEqual(call_kwargs["has_spoiler"], True)
            self.assertEqual(call_kwargs["photo"].data, b"fake_jpeg_image_bytes")
            self.assertEqual(call_kwargs["photo"].filename, "thumbnail.jpg")


if __name__ == "__main__":
    unittest.main()
