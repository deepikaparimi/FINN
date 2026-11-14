#!/usr/bin/env python3
"""Ingest Screener's multi-year financial tables for an NSE ticker."""

import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.research import FIXTURE_DIR, TABLES, save_research_document  # noqa: E402


SCREENER_BASE = "https://www.screener.in/company/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
SECTION_IDS = {
    "profit_loss": "profit-loss",
    "balance_sheet": "balance-sheet",
    "cash_flow": "cash-flow",
    "ratios": "ratios",
}


def parse_number(value: str) -> Optional[float]:
    text = value.strip().replace(",", "")
    if not text or text in {"-", "—", "–", "NA", "N/A"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    match = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)", text.replace("(", "").replace(")", ""))
    if not match:
        return None
    number = float(match.group(0))
    return -abs(number) if negative else number


def parse_table(section: BeautifulSoup, section_id: str) -> dict:
    table = section.find("table")
    if table is None:
        return {"periods": [], "rows": {}}
    header_rows = table.select("thead tr")
    if header_rows:
        header_cells = header_rows[-1].find_all(["th", "td"], recursive=True)
    else:
        first_row = table.find("tr")
        header_cells = first_row.find_all(["th", "td"], recursive=True) if first_row else []
    headings = [cell.get_text(" ", strip=True) for cell in header_cells]
    periods = headings[1:] if len(headings) > 1 else []

    body = table.find("tbody")
    body_rows = body.find_all("tr", recursive=False) if body else table.find_all("tr", recursive=False)[1:]
    rows = {}
    for row in body_rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        label = cells[0].get_text(" ", strip=True)
        if not label:
            continue
        values = [parse_number(cell.get_text(" ", strip=True)) for cell in cells[1:]]
        if len(values) < len(periods):
            values = [None] * (len(periods) - len(values)) + values
        rows[label] = values[:len(periods)] if periods else values
    return {"periods": periods, "rows": rows}


def parse_page(html: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    company = heading.get_text(" ", strip=True) if heading else title.split("|")[0].strip()
    tables = {}
    for name, section_id in SECTION_IDS.items():
        section = soup.find(id=section_id)
        tables[name] = parse_table(section, section_id) if section else {"periods": [], "rows": {}}
    return company, tables


def complete_tables(tables: dict) -> bool:
    return all(tables.get(name, {}).get("rows") for name in TABLES)


def fetch_page(ticker: str, consolidated: bool) -> tuple[str, dict, str]:
    suffix = "/consolidated/" if consolidated else "/"
    url = SCREENER_BASE + quote(ticker, safe="") + suffix
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    company, tables = parse_page(response.text)
    return company, tables, url


def ingest(ticker: str) -> Path:
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9&._-]{1,30}", symbol):
        raise ValueError("Ticker may contain only NSE symbol characters")
    errors = []
    for consolidated, mode in ((True, "consolidated"), (False, "standalone")):
        try:
            company, tables, url = fetch_page(symbol, consolidated)
            if not complete_tables(tables):
                missing = [name for name in TABLES if not tables.get(name, {}).get("rows")]
                raise ValueError("Missing tables: " + ", ".join(missing))
            document = {
                "ticker": symbol,
                "company": company,
                "source": "Screener.in",
                "source_url": url,
                "source_mode": mode,
                "tables": tables,
            }
            saved_to = save_research_document(document)
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            fixture_path = FIXTURE_DIR / f"{symbol}.json"
            try:
                with fixture_path.open("x", encoding="utf-8") as fixture_file:
                    json.dump(document, fixture_file, ensure_ascii=False, indent=2)
                    fixture_file.write("\n")
            except FileExistsError:
                pass
            return saved_to
        except (requests.RequestException, ValueError) as error:
            errors.append(f"{mode}: {error}")
    raise RuntimeError("Could not ingest financial tables. " + " | ".join(errors))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/ingest.py TICKER")
    try:
        saved_to = ingest(sys.argv[1])
    except Exception as error:
        raise SystemExit(str(error)) from error
    print(f"Saved {sys.argv[1].upper()} financial tables to {saved_to}")


if __name__ == "__main__":
    main()
