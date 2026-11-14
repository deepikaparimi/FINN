#!/usr/bin/env python3
"""Export saved database research to fixtures without replacing existing files."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import database_connection, initialize_database  # noqa: E402
from backend.app.research import FIXTURE_DIR  # noqa: E402


def export_research_fixtures() -> tuple[list[str], list[str]]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT ticker, payload FROM research_data ORDER BY ticker"
        ).fetchall()

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    skipped = []
    for row in rows:
        ticker = str(row["ticker"]).strip().upper()
        fixture_path = FIXTURE_DIR / f"{ticker}.json"
        document = json.loads(row["payload"])
        try:
            with fixture_path.open("x", encoding="utf-8") as fixture_file:
                json.dump(document, fixture_file, ensure_ascii=False, indent=2)
                fixture_file.write("\n")
        except FileExistsError:
            skipped.append(ticker)
        else:
            written.append(ticker)
    return written, skipped


def main() -> None:
    written, skipped = export_research_fixtures()
    print("Written: " + (", ".join(written) if written else "none"))
    print("Skipped: " + (", ".join(skipped) if skipped else "none"))


if __name__ == "__main__":
    main()
