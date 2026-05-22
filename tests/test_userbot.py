import unittest
from unittest.mock import AsyncMock, MagicMock
from app.services.userbot import download_thumbnail_bytes, message_has_video, message_fingerprint, message_video_info


class MockAsyncIterator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


class UserbotTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_thumbnail_bytes_selects_highest_resolution(self):
        message = AsyncMock()
        message.video = None
        
        thumb1 = MagicMock()
        thumb1.w = 100
        thumb1.h = 100
        thumb1.size = 1000
        
        thumb2 = MagicMock()
        thumb2.w = 800
        thumb2.h = 600
        thumb2.size = 50000
        
        thumb3 = MagicMock()
        thumb3.w = 320
        thumb3.h = 240
        thumb3.size = 8000
        
        message.document = MagicMock()
        message.document.mime_type = "image/jpeg"
        message.document.thumbs = [thumb1, thumb2, thumb3]
        
        async def mock_download_media(file, thumb):
            file.write(b"fake_thumbnail_data")
            return True
        message.download_media.side_effect = mock_download_media
        
        data = await download_thumbnail_bytes(message)
        self.assertEqual(data, b"fake_thumbnail_data")
        message.download_media.assert_called_once_with(file=unittest.mock.ANY, thumb=thumb2)

    async def test_download_thumbnail_bytes_fallback_to_photo_sizes(self):
        message = AsyncMock()
        message.video = None
        message.document = None
        
        size1 = MagicMock()
        size1.w = 50
        size1.h = 50
        size1.size = 500
        
        size2 = MagicMock()
        size2.w = 1920
        size2.h = 1080
        size2.size = 200000
        
        message.photo = MagicMock()
        message.photo.sizes = [size1, size2]
        
        async def mock_download_media(file, thumb):
            file.write(b"high_res_photo")
            return True
        message.download_media.side_effect = mock_download_media
        
        data = await download_thumbnail_bytes(message)
        self.assertEqual(data, b"high_res_photo")
        message.download_media.assert_called_once_with(file=unittest.mock.ANY, thumb=size2)
        
    async def test_download_thumbnail_bytes_no_thumbs(self):
        message = AsyncMock()
        message.video = None
        message.document = None
        message.photo = None
        
        async def mock_download_media(file, thumb):
            file.write(b"default_thumb")
            return True
        message.download_media.side_effect = mock_download_media
        
        data = await download_thumbnail_bytes(message)
        self.assertEqual(data, b"default_thumb")
        message.download_media.assert_called_once_with(file=unittest.mock.ANY, thumb=0)

    async def test_download_thumbnail_bytes_with_cv2_success(self):
        import app.services.userbot
        
        orig_cv2 = app.services.userbot.cv2
        try:
            mock_cv2 = MagicMock()
            app.services.userbot.cv2 = mock_cv2
            
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.side_effect = [(True, MagicMock()), (False, None)]
            mock_cv2.VideoCapture.return_value = mock_cap
            
            mock_gray = MagicMock()
            mock_gray.mean.return_value = 20
            mock_cv2.cvtColor.return_value = mock_gray
            mock_cv2.imencode.return_value = (True, MagicMock(tobytes=lambda: b"opencv_extracted_thumbnail"))
            
            message = AsyncMock()
            message.video = MagicMock()
            message.media = MagicMock()
            
            mock_client = MagicMock()
            mock_client.iter_download.return_value = MockAsyncIterator([b"chunk_data"])
            message._client = mock_client
            
            data = await download_thumbnail_bytes(message)
            self.assertEqual(data, b"opencv_extracted_thumbnail")
            mock_cv2.VideoCapture.assert_called_once()
            mock_cv2.imencode.assert_called_once()
        finally:
            app.services.userbot.cv2 = orig_cv2

    async def test_download_thumbnail_bytes_with_cv2_failure_falls_back(self):
        import app.services.userbot
        orig_cv2 = app.services.userbot.cv2
        try:
            mock_cv2 = MagicMock()
            app.services.userbot.cv2 = mock_cv2
            
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cv2.VideoCapture.return_value = mock_cap
            
            message = AsyncMock()
            message.video = MagicMock()
            message.media = MagicMock()
            
            thumb = MagicMock()
            thumb.w = 400
            thumb.h = 300
            thumb.size = 20000
            message.document = MagicMock()
            message.document.thumbs = [thumb]
            
            mock_client = MagicMock()
            mock_client.iter_download.return_value = MockAsyncIterator([b"chunk_data"])
            message._client = mock_client
            
            async def mock_download_media(file, thumb):
                file.write(b"fallback_telegram_thumbnail")
                return True
            message.download_media.side_effect = mock_download_media
            
            data = await download_thumbnail_bytes(message)
            self.assertEqual(data, b"fallback_telegram_thumbnail")
            message.download_media.assert_called_once_with(file=unittest.mock.ANY, thumb=thumb)
        finally:
            app.services.userbot.cv2 = orig_cv2

    def test_message_has_video(self):
        msg_video = MagicMock()
        msg_video.video = MagicMock()
        self.assertTrue(message_has_video(msg_video))

        msg_doc = MagicMock()
        msg_doc.video = None
        msg_doc.document = MagicMock()
        msg_doc.document.mime_type = "video/mp4"
        self.assertTrue(message_has_video(msg_doc))

        msg_other = MagicMock()
        msg_other.video = None
        msg_other.document = MagicMock()
        msg_other.document.mime_type = "image/jpeg"
        self.assertFalse(message_has_video(msg_other))


if __name__ == "__main__":
    unittest.main()
