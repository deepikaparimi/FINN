import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.market_data import (
    get_alert_rules,
    list_alerts,
    list_prices,
    refresh_price_history,
    update_alert_rules,
)


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_database_path = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "test.sqlite3")
        self.fixture_path_patch = patch(
            "backend.app.market_data.FIXTURE_PATH",
            Path(self.temp_dir.name) / "prices.json",
        )
        self.fixture_path_patch.start()

    def tearDown(self):
        if self.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self.previous_database_path
        self.fixture_path_patch.stop()
        self.temp_dir.cleanup()

    def test_offline_refresh_saves_all_portfolio_history(self):
        result = refresh_price_history(allow_download=False)
        self.assertEqual(result["companies_updated"], 18)
        self.assertEqual(result["sources"], {"yfinance": 0, "saved_sample": 18})
        self.assertEqual(len(list_prices("RELIANCE")), 60)
        self.assertTrue(all(row["source"] == "saved_sample" for row in list_prices()))

    def test_alerts_use_strict_thresholds_and_twenty_day_volume_average(self):
        refresh_price_history(allow_download=False)
        result = list_alerts()
        fired = {(alert["ticker"], alert["type"]) for alert in result["alerts"]}
        self.assertIn(("RELIANCE", "volume_spike"), fired)
        self.assertIn(("HDFCBANK", "volume_spike"), fired)
        self.assertIn(("TATASTEEL", "price_move"), fired)
        self.assertNotIn(("ETERNAL", "price_move"), fired)

    def test_alert_rules_are_persisted(self):
        refresh_price_history(allow_download=False)
        rules = update_alert_rules(2.5, 4.0)
        self.assertEqual(rules["volume_multiplier"], 2.5)
        self.assertEqual(rules["price_change_percent"], 4.0)
        self.assertEqual(get_alert_rules(), rules)
        self.assertEqual(list_alerts()["alerts"], [])


if __name__ == "__main__":
    unittest.main()
