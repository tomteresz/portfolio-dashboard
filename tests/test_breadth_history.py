"""Regression checks for persistent, comparable market breadth readings."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from portfolio_app.breadth_history import load_breadth_history


class BreadthHistoryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=scratch, suffix=".sqlite3", delete=False) as file:
            self.path = Path(file.name)
        self.path.unlink()
        self.addCleanup(self.path.unlink, missing_ok=True)
        self.close = datetime(2026, 11, 27, 18, tzinfo=timezone.utc)
        self.session = {"start": (self.close - timedelta(hours=3, minutes=30)).timestamp(),
                        "end": self.close.timestamp()}

    def sample(self, minutes_before_close, up, down, *, now=None, session=None):
        fetched = self.close - timedelta(minutes=minutes_before_close)
        return load_breadth_history({"fetched_at": fetched, "advancing": up, "declining": down},
                                    self.session if session is None else session,
                                    now=now or fetched, path=self.path)

    def test_only_latest_near_close_sample_is_saved_on_short_session(self):
        self.assertEqual(self.sample(31, 3000, 2000), [])
        self.assertEqual(self.sample(20, 3000, 2000, session={}), [])
        self.assertFalse(self.path.exists())
        self.sample(30, 3000, 2000)
        expected = [{"day": "2026-11-27", "advancing": 2300, "declining": 2700, "net": -400}]
        self.assertEqual(self.sample(1, 2300, 2700), expected)
        self.assertEqual(self.sample(10, 3000, 2000, now=self.close), expected)
        self.assertEqual(self.sample(0, 3000, 2000), expected)

    def test_saved_sample_is_available_offline_for_fourteen_calendar_days(self):
        sample = self.sample(1, 2500, 2500)
        self.assertEqual(sample[0]["net"], 0)
        last_visible = self.close + timedelta(days=13)
        self.assertEqual(load_breadth_history(None, None, now=last_visible, path=self.path), sample)
        self.assertEqual(load_breadth_history(None, None, now=last_visible + timedelta(days=1), path=self.path), [])
