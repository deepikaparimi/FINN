#!/usr/bin/env python3
"""Generate clearly labeled offline sample announcements for the demo portfolio."""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import database_connection, initialize_database  # noqa: E402
from backend.app.push import ANNOUNCEMENT_FIXTURE, save_announcements  # noqa: E402


AGE_HOURS = (
    # 10 in the last 6 hours, 34 more between 6 and 24, 10 in 1-3 days,
    # and 6 in 3-7 days. Thus most records remain in the default 24h view.
    [0.35, 0.8, 1.4, 2.2, 3.1, 3.8, 4.4, 5.0, 5.5, 5.8]
    + [6.3 + i * 0.49 for i in range(34)]
    + [26.0 + i * 4.2 for i in range(10)]
    + [78.0 + i * 16.5 for i in range(6)]
)


def filing_metrics(ticker: str, quarter: str, index: int) -> str:
    """Return intentionally fictional figures, varying plausibly by company."""
    base = 1800 + (sum(map(ord, ticker)) % 11) * 730 + index * 115
    q_revenue = base
    q_ebitda = round(base * (0.13 + (index % 4) * 0.012))
    q_pbt = round(base * (0.105 + (index % 3) * 0.01))
    q_pat = round(base * (0.078 + (index % 3) * 0.008))
    prev = (round(q_revenue * 0.96), round(q_ebitda * 0.94), round(q_pbt * 0.93), round(q_pat * 0.92))
    year = (round(q_revenue * 0.88), round(q_ebitda * 0.84), round(q_pbt * 0.82), round(q_pat * 0.80))

    # Keep the four result examples useful for demonstrating each verdict.
    if index == 1:  # Weak: every metric is down against both periods.
        prev = tuple(round(value * 1.04) for value in (q_revenue, q_ebitda, q_pbt, q_pat))
        year = tuple(round(value * 1.12) for value in (q_revenue, q_ebitda, q_pbt, q_pat))
    elif index == 2:  # Mixed: PAT is up QoQ but down YoY; revenue is up on both.
        year = (year[0], year[1], year[2], round(q_pat * 1.20))

    def line(label: str, values: tuple[int, int, int, int], *, omit_pat: bool = False) -> str:
        text = f"{label}: Revenue ₹{values[0]} cr; EBITDA ₹{values[1]} cr; PBT ₹{values[2]} cr"
        return text if omit_pat else f"{text}; PAT ₹{values[3]} cr"

    current = (q_revenue, q_ebitda, q_pbt, q_pat)
    return (
        f"SAMPLE ONLY — illustrative {quarter} consolidated results (fictional figures, not an exchange filing). "
        f"{line(quarter, current)}. {line('Last quarter', prev)}. "
        f"{line('Same quarter last year', year, omit_pat=index == 3)}."
    )


def make_subjects(portfolio: list[dict]) -> list[tuple[str, str, str]]:
    """Return (ticker, category, subject) for 14 material and 46 routine items."""
    tickers = [row["ticker"] for row in portfolio]
    special: list[tuple[str, str, str]] = []

    results = ["RELIANCE", "HDFCBANK", "INFY", "TATASTEEL"]
    for index, ticker in enumerate(results):
        special.append((ticker, "results", filing_metrics(ticker, "Q2 FY27", index)))

    special.extend([
        ("SUNPHARMA", "management_change", "SAMPLE ONLY — Board appoints an incoming Chief Financial Officer, effective 1 December 2026; profile and terms are illustrative."),
        ("ITC", "management_change", "SAMPLE ONLY — Independent director submits resignation, effective 14 November 2026; reason and details are illustrative."),
        ("LT", "dividend", "SAMPLE ONLY — Board recommends an interim dividend of ₹18 per share; illustrative record date 27 November 2026."),
        ("BHARTIARTL", "dividend", "SAMPLE ONLY — Board declares an interim dividend of ₹9 per share; illustrative record date 30 November 2026."),
        ("MARUTI", "dividend", "SAMPLE ONLY — Board recommends a final dividend of ₹42 per share, subject to shareholder approval; dates are illustrative."),
        ("POWERGRID", "credit_rating", "SAMPLE ONLY — Rating agency downgrades long-term bank facilities to AA+ from AAA; outlook stable. Illustrative event."),
        ("ETERNAL", "litigation", "SAMPLE ONLY — Company receives an illustrative regulatory order imposing a ₹12 crore penalty; appeal options under review."),
        ("CDSL", "press_release", "SAMPLE ONLY — Receives illustrative ₹185 crore technology services order, to be executed over 24 months."),
        ("TRENT", "press_release", "SAMPLE ONLY — Wins illustrative multi-year supply order valued at ₹96 crore; execution begins this quarter."),
        ("POLYCAB", "pledging", "SAMPLE ONLY — Promoter group reports release of 1.2 lakh pledged shares; illustrative disclosure."),
    ])

    routine_types = [
        "ESOP allotment", "Compliance certificate", "Newspaper advertisement", "Trading window closure",
    ]
    routine: list[tuple[str, str, str]] = []
    for index in range(46):
        ticker = tickers[(index * 7 + 3) % len(tickers)]
        kind = routine_types[index % len(routine_types)]
        if kind == "ESOP allotment":
            subject = f"SAMPLE ONLY — Allotment of {1250 + 37 * index:,} equity shares under the employee stock option plan; illustrative notice."
        elif kind == "Compliance certificate":
            subject = "SAMPLE ONLY — Quarterly compliance certificate under SEBI listing regulations; illustrative routine filing."
        elif kind == "Newspaper advertisement":
            subject = "SAMPLE ONLY — Newspaper advertisement confirming dispatch/publication of shareholder notice; illustrative filing."
        else:
            subject = "SAMPLE ONLY — Trading window closure for designated persons ahead of the results period; illustrative notice."
        routine.append((ticker, "unclassified", subject))

    assert len(special) == 14 and len(routine) == 46
    return special + routine


def load_portfolio() -> list[dict]:
    return json.loads((ROOT / "config" / "portfolio.json").read_text(encoding="utf-8"))


def main() -> None:
    now = datetime.now().replace(microsecond=0)
    portfolio = load_portfolio()
    names = {row["ticker"]: row["company_name"] for row in portfolio}
    subjects = make_subjects(portfolio)
    ages = list(AGE_HOURS)
    # Keep at least one routine filing in even the narrowest digest window.
    ages[14] = 5.9
    items = []
    for index, (ticker, category, subject) in enumerate(subjects):
        timestamp = (now - timedelta(hours=ages[index])).replace(microsecond=0)
        slug = re.sub(r"[^a-z0-9]+", "-", subject.casefold()).strip("-")[:36]
        items.append({
            "id": f"sample-{index + 1:03d}-{slug}",
            "ticker": ticker,
            "company": names[ticker],
            "time": timestamp.isoformat(timespec="seconds"),
            "subject": subject,
            "category": category,
            "attachment_link": "",
            "source": "sample",
        })

    ANNOUNCEMENT_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    ANNOUNCEMENT_FIXTURE.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Replace only prior sample rows, preserving any genuinely fetched records.
    initialize_database()
    with database_connection() as connection:
        connection.execute("DELETE FROM announcements WHERE source = 'sample'")
    saved = save_announcements(items)
    print(f"Wrote {len(items)} clearly labeled sample announcements to {ANNOUNCEMENT_FIXTURE}")
    print(f"Saved {saved} sample rows to the local database; no network access was used.")


if __name__ == "__main__":
    main()
