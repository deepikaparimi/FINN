import unittest
from datetime import datetime, timedelta

from backend.app.push import (
    announcement_level,
    build_digest,
    classify_announcement,
    deduplicate_announcements,
)


class PushRuleTests(unittest.TestCase):
    def test_keyword_categories_and_levels(self):
        self.assertEqual(classify_announcement("Quarterly financial results"), "results")
        self.assertEqual(classify_announcement("Acquisition of a subsidiary"), "M&A")
        self.assertEqual(classify_announcement("Appointment of Chief Financial Officer"), "management_change")
        self.assertEqual(classify_announcement("Declaration of interim dividend"), "dividend")
        self.assertEqual(classify_announcement("Routine compliance certificate"), "unclassified")
        self.assertEqual(announcement_level("results"), 1)
        self.assertEqual(announcement_level("dividend"), 2)
        self.assertEqual(announcement_level("unclassified"), 3)

    def test_digest_filters_duplicates_and_sorts_priority_then_recency(self):
        now = datetime(2026, 11, 14, 12, 0)
        items = [
            {"id": "routine", "ticker": "INFY", "time": (now - timedelta(hours=1)).isoformat(),
             "subject": "Compliance certificate", "category": "unclassified"},
            {"id": "dividend", "ticker": "INFY", "time": (now - timedelta(hours=2)).isoformat(),
             "subject": "Interim dividend", "category": "dividend"},
            {"id": "results", "ticker": "INFY", "time": (now - timedelta(hours=3)).isoformat(),
             "subject": "Quarterly financial results", "category": "results"},
            {"id": "old", "ticker": "INFY", "time": (now - timedelta(hours=30)).isoformat(),
             "subject": "Annual results", "category": "results"},
        ]
        result = build_digest(items + [dict(items[2])], hours=24, now=now)
        self.assertEqual([item["id"] for item in result], ["results", "dividend", "routine"])
        self.assertEqual([item["level"] for item in result], [1, 2, 3])
        self.assertEqual(len(deduplicate_announcements(items + [dict(items[2])])), 4)


if __name__ == "__main__":
    unittest.main()
