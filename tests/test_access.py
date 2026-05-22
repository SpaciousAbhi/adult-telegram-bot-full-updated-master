import unittest
from datetime import UTC, datetime, timedelta

from app.services.access import decide_access, effective_daily_limit


class AccessTests(unittest.TestCase):
    def test_free_user_limit(self):
        runtime = {"access": {"free_daily_limit": 5}}
        self.assertEqual(effective_daily_limit({}, runtime), 5)
        self.assertTrue(decide_access({}, runtime, 4).allowed)
        self.assertFalse(decide_access({}, runtime, 5).allowed)

    def test_referral_reward_lifts_limit(self):
        now = datetime(2026, 5, 22, tzinfo=UTC)
        runtime = {"access": {"free_daily_limit": 5}}
        user = {
            "referral_reward_until": now + timedelta(days=1),
            "referral_reward_limit": 100,
        }
        self.assertEqual(effective_daily_limit(user, runtime, now), 100)

    def test_premium_has_high_limit(self):
        now = datetime(2026, 5, 22, tzinfo=UTC)
        runtime = {"access": {"free_daily_limit": 5, "premium_daily_limit": 500}}
        user = {"plan": "premium", "premium_until": now + timedelta(days=30)}
        self.assertEqual(effective_daily_limit(user, runtime, now), 500)


if __name__ == "__main__":
    unittest.main()

