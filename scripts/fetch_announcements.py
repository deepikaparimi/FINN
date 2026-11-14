#!/usr/bin/env python3
"""Fetch the last 14 days of NSE announcements, with BSE fallback."""

import hashlib
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import initialize_database  # noqa: E402
from backend.app.push import (  # noqa: E402
    ANNOUNCEMENT_FIXTURE,
    classify_announcement,
    deduplicate_announcements,
    parse_announcement_time,
    save_announcements,
)


NSE_HOME = "https://www.nseindia.com"
NSE_ANNOUNCEMENTS = "https://www.nseindia.com/api/corporate-announcements"
BSE_ANNOUNCEMENTS = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}
RETRIES = 3


def request_with_retries(session: requests.Session, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    last_error = None
    for attempt in range(RETRIES):
        try:
            response = session.get(url, params=params, headers=HEADERS, timeout=25)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt + 1 < RETRIES:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed after {RETRIES} attempts: {url}") from last_error


def records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "Table", "table", "announcements"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError("The exchange response did not contain an announcement list")


def fetch_nse(start: datetime, end: datetime) -> list[dict[str, Any]]:
    with requests.Session() as session:
        # Establish the cookies NSE expects before requesting its JSON endpoint.
        last_error = None
        for attempt in range(RETRIES):
            try:
                response = session.get(NSE_HOME, headers=HEADERS, timeout=25)
                response.raise_for_status()
                break
            except requests.RequestException as error:
                last_error = error
                if attempt + 1 < RETRIES:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError("NSE homepage failed after retries") from last_error
        payload = request_with_retries(
            session,
            NSE_ANNOUNCEMENTS,
            {
                "index": "equities",
                "from_date": start.strftime("%d-%m-%Y"),
                "to_date": end.strftime("%d-%m-%Y"),
            },
        )
    return records_from_payload(payload)


def fetch_bse(start: datetime, end: datetime) -> list[dict[str, Any]]:
    with requests.Session() as session:
        payload = request_with_retries(
            session,
            BSE_ANNOUNCEMENTS,
            {
                "strCat": "-1",
                "strPrevDate": start.strftime("%Y%m%d"),
                "strToDate": end.strftime("%Y%m%d"),
                "strScrip": "",
                "strSearch": "P",
                "strType": "C",
            },
        )
    return records_from_payload(payload)


def first(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalized_company_name(value: str) -> str:
    normalized = " ".join(value.casefold().replace("&", "and").split())
    return normalized.replace(" limited", "").replace(" ltd", "").replace(" private", "").replace(" pvt", "")


def normalize_record(
    record: dict[str, Any], companies: dict[str, str], source: str
) -> Optional[dict[str, Any]]:
    ticker = first(record, "symbol", "ticker", "security", "SCRIP_CD", "scrip_cd")
    ticker = ticker.upper().strip()
    if ticker not in companies:
        company_label = first(
            record, "sm_name", "SCRIP_NAME", "scrip_name", "company", "companyName", "SLONGNAME"
        )
        label = normalized_company_name(company_label)
        ticker = next(
            (symbol for symbol, company in companies.items()
             if normalized_company_name(company) == label),
            "",
        )
    if ticker not in companies:
        return None
    subject = first(record, "desc", "HEADLINE", "headline", "subject", "NEWS_SUB", "NEWSSUB")
    raw_time = first(record, "an_dt", "NEWS_DT", "news_dt", "time", "date", "announcementDate")
    parsed_time = parse_announcement_time(raw_time)
    if not subject or parsed_time is None:
        return None
    attachment = first(
        record, "attchmntFile", "ATTACHMENTNAME", "attachment_link", "attachment", "pdf_url", "ATTACHMENT"
    )
    if attachment and not attachment.startswith(("https://", "http://")):
        base = "https://www.bseindia.com/" if source == "BSE" else "https://www.nseindia.com/"
        attachment = urljoin(base, attachment)
    upstream_id = first(record, "seq_id", "newsid", "news_id", "id")
    identity = "|".join((ticker, parsed_time.isoformat(timespec="seconds"), subject, attachment))
    item_id = upstream_id or hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return {
        "id": item_id,
        "ticker": ticker,
        "company": companies[ticker],
        "time": parsed_time.isoformat(timespec="seconds"),
        "subject": subject,
        "category": classify_announcement(subject),
        "attachment_link": attachment,
        "source": source,
    }


def collect_announcements(now: Optional[datetime] = None) -> tuple[str, list[dict[str, Any]]]:
    now = now or datetime.now()
    start = now - timedelta(days=14)
    portfolio = json.loads((ROOT / "config" / "portfolio.json").read_text(encoding="utf-8"))
    companies = {item["ticker"].upper(): item["company_name"] for item in portfolio}
    start_text, end_text = start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    errors = []
    for source, fetch in (("NSE", fetch_nse), ("BSE", fetch_bse)):
        try:
            raw_items = fetch(start, now)
            normalized = [
                item for row in raw_items
                if (item := normalize_record(row, companies, source)) is not None
                and start_text <= item["time"][:10] <= end_text
            ]
            return source, deduplicate_announcements(normalized)
        except Exception as error:
            errors.append(f"{source}: {error}")
    raise RuntimeError("Both exchange feeds failed. " + " | ".join(errors))


def main() -> None:
    source, items = collect_announcements()
    ANNOUNCEMENT_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    ANNOUNCEMENT_FIXTURE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    initialize_database()
    saved = save_announcements(items)
    print(f"Fetched {len(items)} unique announcements from {source}; saved {saved}.")


if __name__ == "__main__":
    main()
