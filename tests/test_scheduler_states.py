import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, UTC
from bson import ObjectId
from app.services.task_runner import TaskScheduler

class SchedulerStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_due_tasks_resumes_cooldown(self):
        db = MagicMock()
        settings = MagicMock()
        settings.poll_interval_seconds = 15
        settings.source_collect_interval_seconds = 60
        bot = MagicMock()
        scheduler = TaskScheduler(db, settings, bot)
        now = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
        
        task_expired = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000001"),
            "name": "Expired Cooldown Task",
            "status": "cooldown",
            "cooldown_until": now - timedelta(seconds=10),
            "next_run_at": now - timedelta(seconds=10),
            "next_collect_at": now - timedelta(seconds=10),
        }

        
        task_active_cooldown = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000002"),
            "name": "Active Cooldown Task",
            "status": "cooldown",
            "cooldown_until": now + timedelta(seconds=10),
        }
        
        tasks = [task_expired, task_active_cooldown]
        
        mock_cursor = MagicMock()
        async def mock_cursor_iterator(*args, **kwargs):
            for t in tasks:
                yield t
        mock_cursor.__aiter__ = mock_cursor_iterator
        db.col.return_value.find.return_value.sort.return_value.limit.return_value = mock_cursor
        db.col.return_value.update_one = AsyncMock()
        
        with patch('app.services.task_runner.utcnow', return_value=now):
            with patch.object(scheduler, '_execute_task_bg') as mock_bg:
                await scheduler.run_due_tasks()
                
                db.col.return_value.update_one.assert_any_call(
                    {"_id": task_expired["_id"]},
                    {"$set": {"status": "active", "cooldown_until": None, "updated_at": now}}
                )
                
                for call in db.col.return_value.update_one.call_args_list:
                    self.assertNotEqual(call[0][0]["_id"], task_active_cooldown["_id"])

    async def test_run_due_tasks_skips_paused_and_draft(self):
        db = MagicMock()
        settings = MagicMock()
        settings.source_collect_interval_seconds = 60
        bot = MagicMock()
        scheduler = TaskScheduler(db, settings, bot)
        now = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

        
        task_paused = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000003"),
            "status": "paused",
        }
        task_draft = {
            "_id": ObjectId("60c72b2f9b1d8b2bad000004"),
            "status": "draft",
        }
        
        mock_cursor = MagicMock()
        async def mock_cursor_iterator(*args, **kwargs):
            yield task_paused
            yield task_draft
        mock_cursor.__aiter__ = mock_cursor_iterator
        db.col.return_value.find.return_value.sort.return_value.limit.return_value = mock_cursor
        db.col.return_value.update_one = AsyncMock()
        
        with patch('app.services.task_runner.utcnow', return_value=now):
            await scheduler.run_due_tasks()

            db.col.return_value.update_one.assert_not_called()

if __name__ == "__main__":
    unittest.main()
