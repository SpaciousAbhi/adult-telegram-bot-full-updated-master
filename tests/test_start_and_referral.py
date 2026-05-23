import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, UTC, timedelta
from app.routers.start import send_user_entry, send_referral_details
from app.services.force_subscription import ForceSubscriptionService

class StartAndReferralTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_user_entry_filters_unjoined_channels(self):
        # Setup mocks
        message = AsyncMock()
        db = MagicMock()
        bot = AsyncMock()
        settings = MagicMock()
        
        # Mock destination_channels
        runtime = {
            "destination_channels": [
                {"chat_id": -100111111, "title": "Joined Channel", "link": "https://t.me/joined"},
                {"chat_id": -100222222, "title": "Unjoined Channel", "link": "https://t.me/unjoined"}
            ]
        }
        db.get_runtime_settings = AsyncMock(return_value=runtime)
        db.get_user = AsyncMock(return_value={})
        db.set_pending_action = AsyncMock()
        
        # Mock ForceSubscriptionService targets and membership
        with patch.object(ForceSubscriptionService, "missing_targets", return_value=[]), \
             patch.object(ForceSubscriptionService, "is_joined") as mock_is_joined:
            
            # User joined -100111111 but not -100222222
            async def side_effect(chat_id, user_id):
                return chat_id == -100111111
            mock_is_joined.side_effect = side_effect
            
            await send_user_entry(message, db, bot, settings, user_id=12345)
            
            # Since the user hasn't joined -100222222, they should get the unjoined destinations welcome text
            message.answer.assert_called_once()
            args, kwargs = message.answer.call_args
            self.assertIn("Welcome to the Premium Bot!", args[0])
            self.assertIn("Here are our free content channels you can join:", args[0])
            
            # The keyboard should only have the unjoined channel button and the referral button (no Verify Access)
            reply_markup = kwargs["reply_markup"]
            self.assertEqual(len(reply_markup.inline_keyboard), 2) # Unjoined channel, Referral Program
            unjoined_btn = reply_markup.inline_keyboard[0][0]
            self.assertEqual(unjoined_btn.text, "📢 Join: Unjoined Channel")
            self.assertEqual(unjoined_btn.url, "https://t.me/unjoined")

    async def test_send_referral_details_renders_proper_stats(self):
        message = AsyncMock()
        db = MagicMock()
        bot = AsyncMock()
        
        runtime = {
            "referral": {
                "required_joins": 5,
                "reward_limit": 50,
                "reward_days": 3
            }
        }
        db.get_runtime_settings = AsyncMock(return_value=runtime)
        db.get_user = AsyncMock(return_value={
            "referral_reward_until": datetime.now(UTC) + timedelta(days=2),
            "referral_reward_limit": 50
        })
        
        # Mock referral link and events count
        db.col.return_value.count_documents = AsyncMock(return_value=3)
        
        with patch("app.services.referrals.ReferralService.get_or_create_link", new_callable=AsyncMock) as mock_get_link:
            mock_get_link.return_value = "https://t.me/bot?start=ref_12345"
            
            await send_referral_details(message, db, bot, user_id=12345, edit_message=False)
            
            message.answer.assert_called_once()
            args, kwargs = message.answer.call_args
            self.assertIn("Invite your friends using your personal link", args[0])
            self.assertIn("• <b>Total Referrals:</b> <code>3</code> / <code>5</code>", args[0])
            self.assertIn("✅ Active (Reward limit: 50 daily", args[0])
            self.assertIn("https://t.me/bot?start=ref_12345", args[0])
            
            reply_markup = kwargs["reply_markup"]
            self.assertEqual(len(reply_markup.inline_keyboard), 2) # Share Link, Back
            share_btn = reply_markup.inline_keyboard[0][0]
            self.assertEqual(share_btn.text, "📲 Share Link")
            self.assertTrue(share_btn.url.startswith("https://t.me/share/url"))

if __name__ == "__main__":
    unittest.main()
