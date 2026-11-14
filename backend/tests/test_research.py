import json
import unittest
from pathlib import Path

from backend.app.research import FIXTURE_DIR, calculate_metrics


ROOT_DIR = Path(__file__).resolve().parents[2]


class ResearchCalculationTests(unittest.TestCase):
    def setUp(self):
        self.document = {
            "tables": {
                "profit_loss": {
                    "periods": ["Mar 2022", "Mar 2023", "Mar 2024"],
                    "rows": {
                        "Sales": [100, 120, 150],
                        "Net Profit": [10, 12, 15],
                        "Operating Profit": [20, 30, 45],
                    },
                },
                "balance_sheet": {
                    "periods": ["Mar 2022", "Mar 2023", "Mar 2024"],
                    "rows": {
                        "Borrowings": [20, 24, 30],
                        "Reserves": [30, 40, 50],
                        "Equity Capital": [10, 10, 10],
                    },
                },
                "cash_flow": {
                    "periods": ["Mar 2022", "Mar 2023", "Mar 2024"],
                    "rows": {
                        "Cash from Operating Activity": [8, 14, 18],
                        "Cash from Investing Activity": [-3, -4, -5],
                    },
                },
                "ratios": {"periods": ["Mar 2024"], "rows": {"ROCE %": [24]}},
            },
        }

    def test_growth_margins_leverage_cash_conversion_and_fcf(self):
        metrics = calculate_metrics(self.document)
        snapshot = metrics["snapshot"]
        self.assertEqual(snapshot["revenue_growth_percent"], 25)
        self.assertEqual(snapshot["profit_growth_percent"], 25)
        self.assertEqual(snapshot["net_margin_percent"], 10)
        self.assertEqual(snapshot["operating_margin_percent"], 30)
        self.assertEqual(metrics["balance_sheet"]["debt_to_equity"], 0.5)
        self.assertEqual(metrics["cash_quality"]["cash_conversion"], 1.2)
        self.assertEqual(metrics["cash_quality"]["free_cash_flow"], 13)

    def test_missing_and_zero_denominators_return_unavailable_values(self):
        empty = {"tables": {"profit_loss": {"periods": ["Mar 2024"], "rows": {"Sales": [0], "Net Profit": [0]}}}}
        metrics = calculate_metrics(empty)
        self.assertIsNone(metrics["snapshot"]["revenue_growth_percent"])
        self.assertIsNone(metrics["snapshot"]["net_margin_percent"])
        self.assertIsNone(metrics["balance_sheet"]["debt_to_equity"])
        self.assertIsNone(metrics["cash_quality"]["cash_conversion"])
        self.assertIsNone(metrics["cash_quality"]["free_cash_flow"])


class ResearchFixtureCoverageTests(unittest.TestCase):
    def test_every_portfolio_ticker_has_a_research_fixture(self):
        portfolio_path = ROOT_DIR / "config" / "portfolio.json"
        portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
        missing = [
            item["ticker"].upper()
            for item in portfolio
            if not (FIXTURE_DIR / f"{item['ticker'].upper()}.json").is_file()
        ]

        self.assertEqual(missing, [], f"Missing research fixtures: {', '.join(missing)}")


if __name__ == "__main__":
    unittest.main()
