#!/usr/bin/env python3
"""Fetch 60 days of portfolio prices and volumes, updating DB and fixture."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.market_data import refresh_price_history  # noqa: E402


def main() -> None:
    result = refresh_price_history(allow_download=True)
    print(
        "Updated {companies_updated} companies through {as_of}: {sources}".format(
            **result
        )
    )


if __name__ == "__main__":
    main()
