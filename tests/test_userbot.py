import unittest
from unittest.mock import AsyncMock, MagicMock
from app.services.userbot import download_thumbnail_bytes, message_has_video, message_fingerprint, message_video_info

class UserbotTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_thumbnail_bytes_selects_highest_resolution(self):
        message = AsyncMock()
        
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
        message.document = None
        message.photo = None
        
        async def mock_download_media(file, thumb):
            file.write(b"default_thumb")
            return True
        message.download_media.side_effect = mock_download_media
        
        data = await download_thumbnail_bytes(message)
        self.assertEqual(data, b"default_thumb")
        message.download_media.assert_called_once_with(file=unittest.mock.ANY, thumb=0)

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
