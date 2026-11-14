"""Load the checked-in demo dataset into a new or empty SQLite database."""

import json

from .db import ROOT_DIR, database_connection, initialize_database
from .market_data import _clean_rows
from .push import deduplicate_announcements
from .research import calculate_metrics


def seed_from_fixtures() -> bool:
    """Seed all fixture-backed features once when the database has no data.

    Returns True when fixture data was loaded. This path never uses the network
    and only reads the checked-in fixtures.
    """
    initialize_database()
    with database_connection() as connection:
        counts = [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("daily_prices", "announcements", "research_data")
        ]
        if any(counts):
            return False

        price_doc = json.loads((ROOT_DIR / "fixtures" / "prices.json").read_text(encoding="utf-8"))
        sources = price_doc.get("sources", {})
        for ticker, rows in price_doc.get("prices", {}).items():
            connection.executemany(
                """INSERT OR REPLACE INTO daily_prices
                   (ticker, trade_date, close, volume, source) VALUES (?, ?, ?, ?, ?)""",
                [
                    (ticker.upper(), row["date"][:10], float(row["close"]), int(row["volume"]),
                     sources.get(ticker, price_doc.get("source", "saved_sample")))
                    for row in _clean_rows(rows)
                ],
            )

        announcement_path = ROOT_DIR / "fixtures" / "announcements.json"
        announcements = deduplicate_announcements(
            json.loads(announcement_path.read_text(encoding="utf-8"))
        )
        connection.executemany(
            """INSERT OR REPLACE INTO announcements
               (id, ticker, company, time, subject, category, attachment_link, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (str(item.get("id", "")), str(item.get("ticker", "")).upper(),
                 str(item.get("company", "")), str(item.get("time", "")),
                 str(item.get("subject", "")), str(item.get("category", "unclassified")),
                 str(item.get("attachment_link", "")), str(item.get("source", "sample")))
                for item in announcements
            ],
        )

        research_dir = ROOT_DIR / "fixtures" / "research"
        for fixture_path in sorted(research_dir.glob("*.json")):
            document = json.loads(fixture_path.read_text(encoding="utf-8"))
            ticker = str(document.get("ticker", fixture_path.stem)).upper()
            document["ticker"] = ticker
            document.setdefault("metrics", calculate_metrics(document))
            connection.execute(
                """INSERT OR REPLACE INTO research_data
                   (ticker, payload, source_mode) VALUES (?, ?, ?)""",
                (ticker, json.dumps(document, ensure_ascii=False), document.get("source_mode", "consolidated")),
            )
    return True
