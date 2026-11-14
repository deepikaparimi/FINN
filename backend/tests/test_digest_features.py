import unittest
from datetime import date, timedelta
from backend.app.push import _filing_summary, build_digest_response, lookup_market_context, results_verdict
from scripts.make_sample_announcements import filing_metrics


class DigestFeatureTests(unittest.TestCase):
    def test_top_three_uses_scores_excludes_level_three_and_deduplicates_ticker(self):
        items = [
            {"id": "r1", "ticker": "INFY", "category": "results", "level": 1,
             "time": "2026-11-14T10:00:00", "verdict": "Strong"},
            {"id": "r2", "ticker": "RELIANCE", "category": "results", "level": 1,
             "time": "2026-11-14T11:00:00", "verdict": "Mixed"},
            {"id": "r3", "ticker": "INFY", "category": "results", "level": 1,
             "time": "2026-11-14T12:00:00", "verdict": "Strong"},
            {"id": "d1", "ticker": "TCS", "category": "dividend", "level": 2,
             "time": "2026-11-14T13:00:00"},
            {"id": "d2", "ticker": "HDFC", "category": "M&A", "level": 1,
             "time": "2026-11-14T09:00:00"},
            {"id": "routine", "ticker": "ABC", "category": "routine", "level": 3,
             "time": "2026-11-14T14:00:00"},
        ]
        prices = [
            {"ticker": "RELIANCE", "date": "2026-11-13", "close": 100, "volume": 1000},
            {"ticker": "RELIANCE", "date": "2026-11-14", "close": 105, "volume": 1000},
        ]
        rules = {"price_change_percent": 3, "volume_multiplier": 2, "volume_lookback_days": 20}
        ranked = build_digest_response(items, prices, rules)["top_items"]
        self.assertEqual([item["ticker"] for item in ranked], ["RELIANCE", "INFY", "HDFC"])
        self.assertEqual(ranked[0]["id"], "r2")  # Alert bonus outranks the Strong verdict bonus.
        self.assertEqual(ranked[1]["id"], "r3")  # One item per ticker; newest filing wins.

    def test_results_verdict_strong(self):
        self.assertEqual(results_verdict(self.metrics(4, 6, 8, 9))[0], "Strong")

    def test_results_verdict_weak(self):
        self.assertEqual(results_verdict(self.metrics(-4, -6, -8, -9))[0], "Weak")

    def test_results_verdict_mixed(self):
        verdict, _ = results_verdict(self.metrics(4, -6, -8, 9))
        self.assertEqual(verdict, "Mixed")

    def test_results_verdict_unclear_for_missing_or_low_confidence(self):
        missing = self.metrics(4, 6, 8, 9)
        missing[1]["qoq_percent"] = None
        self.assertEqual(results_verdict(missing)[0], "Unclear")
        low = self.metrics(4, 6, 8, 9)
        low[0]["confidence"] = "low"
        self.assertEqual(results_verdict(low)[0], "Unclear")

    def test_sample_result_filings_produce_all_four_verdicts(self):
        expected = ["Strong", "Weak", "Mixed", "Unclear"]
        for index, verdict in enumerate(expected):
            with self.subTest(verdict=verdict):
                filing = filing_metrics("SAMPLE", "Q2 FY27", index)
                summary = _filing_summary({"category": "results", "subject": filing})
                self.assertEqual(results_verdict(summary["results_metrics"])[0], verdict)

    def test_market_context_matches_ticker_and_same_day(self):
        item = {"ticker": "INFY", "time": "2026-11-14T10:00:00"}
        prices = []
        first_day = date(2026, 10, 25)
        for offset in range(21):
            day = first_day + timedelta(days=offset)
            prices.append({"ticker": "INFY", "date": day.isoformat(), "close": 104 if offset == 20 else 100,
                           "volume": 3000 if offset == 20 else 1000})
        rules = {"price_change_percent": 3, "volume_multiplier": 2, "volume_lookback_days": 20}
        self.assertEqual(lookup_market_context(item, prices, rules), {"volume_ratio": 3.0, "price_change_pct": 4.0})
        self.assertIsNone(lookup_market_context({**item, "ticker": "ABC"}, prices, rules))
        self.assertIsNone(lookup_market_context({**item, "time": "2026-11-15T10:00:00"}, prices, rules))

    @staticmethod
    def metrics(revenue_qoq, revenue_yoy, pat_qoq, pat_yoy):
        return [
            {"label": "Revenue", "value": 100, "qoq_percent": revenue_qoq, "yoy_percent": revenue_yoy, "confidence": "high"},
            {"label": "EBITDA", "value": 30, "qoq_percent": revenue_qoq, "yoy_percent": revenue_yoy, "confidence": "high"},
            {"label": "PBT", "value": 20, "qoq_percent": pat_qoq, "yoy_percent": pat_yoy, "confidence": "high"},
            {"label": "PAT", "value": 10, "qoq_percent": pat_qoq, "yoy_percent": pat_yoy, "confidence": "high"},
        ]


if __name__ == "__main__":
    unittest.main()
