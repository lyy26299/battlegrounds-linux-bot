import unittest
from datetime import datetime, timezone
from schedule_window import inside_window, running_window, parse_deadline
class ScheduleTest(unittest.TestCase):
    def test_beijing_boundaries(self):
        for stamp, expected in [('2026-10-24T16:59:59+00:00',False),('2026-10-24T17:00:00+00:00',True),('2026-10-25T03:59:59+00:00',True),('2026-10-25T04:00:00+00:00',False)]:
            self.assertEqual(inside_window(datetime.fromisoformat(stamp)),expected)

    def test_extra_window_expires_and_joins_daily_window(self):
        end=parse_deadline('2026-10-26T01:00:00+08:00')
        for stamp, expected in [('2026-10-25T18:40:00+08:00',True),('2026-10-26T00:59:59+08:00',True),('2026-10-26T01:00:00+08:00',True),('2026-10-26T11:59:59+08:00',True),('2026-10-26T12:00:00+08:00',False),('2026-10-27T00:59:59+08:00',False)]:
            self.assertEqual(running_window(parse_deadline(stamp),end),expected)
        self.assertFalse(running_window(parse_deadline('2026-10-25T18:40:00+08:00')))

    def test_deadline_requires_timezone(self):
        with self.assertRaises(ValueError): parse_deadline('2026-10-26T01:00:00')
