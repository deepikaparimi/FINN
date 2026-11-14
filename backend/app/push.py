"""Keyword-only announcement classification, sorting, and persistence."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from .db import ROOT_DIR, database_connection, initialize_database


ANNOUNCEMENT_FIXTURE = ROOT_DIR / "fixtures" / "announcements.json"

CATEGORY_KEYWORDS = {
    "results": (
        "financial results", "quarterly results", "annual results", "audited results",
        "unaudited results", "revised results", "results for the quarter", "results for the year", "results",
    ),
    "M&A": (
        "acquisition", "acquire", "merger", "amalgamation", "demerger", "joint venture",
        "strategic investment", "stake sale", "sale of subsidiary",
    ),
    "management_change": (
        "resignation", "appointed as", "appointment of", "reappointed", "ceo", "chief executive",
        "chief financial officer", "cfo", "managing director", "director retires", "retirement",
        "key managerial",
    ),
    "litigation": (
        "litigation", "court order", "regulatory order", "penalty", "fine imposed", "show cause",
        "insolvency", "restructuring proceedings", "adjudication order",
    ),
    "credit_rating": (
        "credit rating", "rating rationale", "rating upgrade", "rating downgrade",
        "rating reaffirmed", "rating reaffirmation", "credit rating assigned", "rating assigned",
    ),
    "fund_raise": (
        "fund raising", "fund raise", "rights issue", "qualified institutional placement", "qip",
        "preferential allotment", "preferential issue", "commercial paper", "non convertible debenture",
        "buyback",
    ),
    "pledging": ("pledge", "pledging", "release of pledged", "encumbrance of shares"),
    "dividend": ("dividend",),
    "capex": ("capital expenditure", "capex", "new plant", "capacity expansion"),
    "bonus_split": ("bonus issue", "bonus shares", "stock split", "split of shares", "face value split"),
    "earnings_call": ("earnings call", "concall", "conference call", "transcript of call"),
    "press_release": (
        "press release", "order win", "order received", "product launch", "business update",
        "partnership", "rumour clarification",
    ),
    "insider_trading": (
        "insider trading", "acquisition of shares by promoter", "disposal of shares by promoter",
        "trading in securities", "sast disclosure",
    ),
    "investor_meetings": ("investor meeting", "investor conference", "one to one meeting"),
    "postal_ballot": ("postal ballot",),
    "agm_egm": ("annual general meeting", "extraordinary general meeting", "agm", "egm"),
}

LEVEL_ONE = {"results", "M&A", "management_change", "litigation", "credit_rating", "fund_raise", "pledging"}
LEVEL_TWO = {"dividend", "capex", "bonus_split", "earnings_call", "press_release", "insider_trading"}

RESULT_METRICS = ("Revenue", "EBITDA", "PBT", "PAT")


def _filing_summary(item: dict[str, Any]) -> dict[str, Any]:
    """Create compact, deterministic digest fields from the filing text."""
    filing = str(item.get("subject", "")).strip()
    category = item.get("category") or classify_announcement(filing)
    quarter_match = re.search(r"\bQ[1-4]\s+FY\s?\d{2,4}\b", filing, re.I)
    quarter = re.sub(r"\s+", " ", quarter_match.group(0).upper()) if quarter_match else "Latest"
    if category == "results":
        headline = f"{quarter} results"
    else:
        clean = re.sub(r"^SAMPLE ONLY\s*[—-]\s*", "", filing, flags=re.I)
        clean = re.split(r"[.;]", clean, maxsplit=1)[0].strip()
        headline = clean if len(clean) <= 72 else clean[:69].rsplit(" ", 1)[0] + "…"
    level = announcement_level(category)
    why_templates = {
        "results": "Shows whether sales and profit are growing this quarter.",
        "M&A": "A deal can change the company’s growth plans and financial risk.",
        "management_change": "A leadership change can affect execution and strategy.",
        "litigation": "The outcome may affect costs, operations, or future obligations.",
        "credit_rating": "A rating change can affect borrowing costs and access to credit.",
        "fund_raise": "New funding can change the share count, debt, or cash available.",
        "pledging": "Changes in pledged shares can signal a change in promoter financing risk.",
        "dividend": "The payout affects cash returned to shareholders and company reserves.",
        "capex": "New investment can shape future capacity and cash flow.",
        "bonus_split": "The share count changes, while each holding’s ownership value is unchanged.",
        "earnings_call": "Management commentary can add context to reported results.",
        "press_release": "The update may affect expected orders, products, or operations.",
        "insider_trading": "Promoter or insider transactions can change ownership exposure.",
    }
    summary: dict[str, Any] = {"headline": headline, "filing_text": filing}
    if level in (1, 2):
        summary["why_it_matters"] = why_templates.get(category, "This update may affect the company’s business or financial position.")
    if category == "results":
        # Values are extracted from the filing and comparisons are calculated here in Python.
        labels = {"current": (quarter, "this quarter"), "qoq": ("Last quarter", "QoQ %"), "yoy": ("Same quarter last year", "YoY %")}
        metric_rows = []
        for metric in RESULT_METRICS:
            found: dict[str, float] = {}
            for key, (period_label, _) in labels.items():
                match = re.search(rf"{re.escape(period_label)}\s*:?[^.]*?\b{metric}\s+₹?\s*([-+]?\d[\d,]*(?:\.\d+)?)\s*(?:cr|crore)?", filing, re.I)
                if match:
                    found[key] = float(match.group(1).replace(",", ""))
            current = found.get("current")
            metric_rows.append({
                "label": metric,
                "value": current,
                "qoq_percent": ((current - found["qoq"]) / abs(found["qoq"]) * 100) if current is not None and found.get("qoq") else None,
                "yoy_percent": ((current - found["yoy"]) / abs(found["yoy"]) * 100) if current is not None and found.get("yoy") else None,
                "confidence": "high" if current is not None and found.get("qoq") not in (None, 0) and found.get("yoy") not in (None, 0) else "low",
            })
        summary["results_metrics"] = metric_rows
        verdict, reason = results_verdict(metric_rows)
        summary["verdict"] = verdict
        summary["verdict_reason"] = reason
    return summary


def results_verdict(metrics: list[dict[str, Any]]) -> tuple[str, str]:
    """Classify results using only Revenue and PAT quarter/year comparisons."""
    by_label = {str(metric.get("label", "")).casefold(): metric for metric in metrics}
    revenue = by_label.get("revenue", {})
    pat = by_label.get("pat", {})
    values = (revenue.get("qoq_percent"), revenue.get("yoy_percent"), pat.get("qoq_percent"), pat.get("yoy_percent"))
    low_confidence = any(
        metric.get("confidence") == "low" or metric.get("low_confidence") is True
        for metric in by_label.values()
    )
    incomplete = any(
        label not in by_label
        or by_label[label].get("value") is None
        or by_label[label].get("qoq_percent") is None
        or by_label[label].get("yoy_percent") is None
        for label in ("revenue", "ebitda", "pbt", "pat")
    )
    if low_confidence or incomplete:
        return "Unclear", "Revenue or PAT comparisons are missing or low confidence."
    revenue_qoq, revenue_yoy, pat_qoq, pat_yoy = (float(value) for value in values)
    reason = f"Revenue {revenue_qoq:+.1f}% QoQ, PAT {pat_qoq:+.1f}% QoQ"
    if revenue_qoq > 0 and revenue_yoy > 0 and pat_qoq > 0 and pat_yoy > 0:
        return "Strong", reason
    if revenue_qoq < 0 and revenue_yoy < 0 and pat_qoq < 0 and pat_yoy < 0:
        return "Weak", reason
    return "Mixed", reason


def lookup_market_context(
    item: dict[str, Any], prices: Iterable[dict[str, Any]], rules: dict[str, Any],
) -> Optional[dict[str, Optional[float]]]:
    """Calculate triggered price and volume context from saved prices on filing day."""
    when = parse_announcement_time(item.get("time"))
    if when is None:
        return None
    ticker = str(item.get("ticker", "")).upper()
    history = sorted(
        (row for row in prices if str(row.get("ticker", "")).upper() == ticker),
        key=lambda row: str(row.get("date", "")),
    )
    day = when.date().isoformat()
    index = next((position for position, row in enumerate(history) if str(row.get("date", ""))[:10] == day), None)
    if index is None or index < 1:
        return None
    context: dict[str, Optional[float]] = {"volume_ratio": None, "price_change_pct": None}
    current = history[index]
    previous = history[index - 1]
    try:
        close = float(current["close"])
        prior_close = float(previous["close"])
        price_change = (close - prior_close) / prior_close * 100
        if abs(price_change) > float(rules["price_change_percent"]):
            context["price_change_pct"] = round(price_change, 2)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass

    lookback = int(rules.get("volume_lookback_days", 20))
    baseline = history[max(0, index - lookback):index]
    if lookback > 0 and len(baseline) == lookback:
        try:
            average = sum(float(row["volume"]) for row in baseline) / lookback
            ratio = float(current["volume"]) / average if average else 0
            if ratio > float(rules["volume_multiplier"]):
                context["volume_ratio"] = round(ratio, 2)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    return context if any(value is not None for value in context.values()) else None


def build_digest_response(
    items: Iterable[dict[str, Any]], prices: Iterable[dict[str, Any]], rules: dict[str, Any],
) -> dict[str, Any]:
    """Attach market context and rank the three highest-priority unique tickers."""
    price_rows = list(prices)
    enriched = []
    for original in items:
        item = dict(original)
        context = lookup_market_context(item, price_rows, rules)
        item["market_context"] = context
        enriched.append(item)

    def rank(item: dict[str, Any]) -> tuple[int, float]:
        score = {1: 100, 2: 40, 3: 0}.get(int(item.get("level", 3)), 0)
        if item.get("market_context") is not None:
            score += 30
        if item.get("category") == "results" and item.get("verdict") in {"Strong", "Weak"}:
            score += 15
        when = parse_announcement_time(item.get("time"))
        return score, when.timestamp() if when else 0

    top_items = []
    seen_tickers = set()
    for item in sorted((item for item in enriched if item.get("level") in (1, 2)), key=rank, reverse=True):
        ticker = str(item.get("ticker", "")).upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        top_items.append({
            "id": item.get("id") or _stable_id(item),
            "ticker": ticker,
            "category": item.get("category", "unclassified"),
            "level": item.get("level", 3),
            "time": item.get("time"),
            "verdict": item.get("verdict"),
            "verdict_reason": item.get("verdict_reason"),
            "results_metrics": item.get("results_metrics", []),
            "market_context": item.get("market_context"),
        })
        if len(top_items) == 3:
            break
    return {"announcements": enriched, "top_items": top_items}


def classify_announcement(subject: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (subject or "").casefold()).strip()
    if "acquisition of shares by promoter" in text or "disposal of shares by promoter" in text:
        return "insider_trading"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip() in text for phrase in keywords):
            return category
    return "unclassified"


def announcement_level(category: str) -> int:
    if category in LEVEL_ONE:
        return 1
    if category in LEVEL_TWO:
        return 2
    return 3


def parse_announcement_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        number = float(text)
        if number > 1_000_000_000_000:
            number /= 1000
        if number > 1_000_000_000:
            return datetime.fromtimestamp(number)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in (
        "%d-%b-%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y",
        "%Y-%m-%d", "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _dedupe_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("ticker", "")).upper(),
        str(item.get("time", ""))[:16],
        re.sub(r"\s+", " ", str(item.get("subject", "")).casefold()).strip(),
        str(item.get("attachment_link", "")).strip().casefold(),
    )


def deduplicate_announcements(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        clean = dict(item)
        clean["category"] = clean.get("category") or classify_announcement(clean.get("subject", ""))
        result.append(clean)
    return result


def _sort_key(item: dict[str, Any]) -> tuple[int, float]:
    when = parse_announcement_time(item.get("time"))
    timestamp = when.timestamp() if when else 0
    return announcement_level(item.get("category", "unclassified")), -timestamp


def build_digest(
    items: Iterable[dict[str, Any]], hours: int = 24,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    if hours < 1 or hours > 336:
        raise ValueError("hours must be between 1 and 336")
    now = now or datetime.now()
    cutoff = now - timedelta(hours=hours)
    selected = []
    for item in deduplicate_announcements(items):
        when = parse_announcement_time(item.get("time"))
        if when is None or when < cutoff or when > now:
            continue
        result = dict(item)
        result["level"] = announcement_level(result["category"])
        result.update(_filing_summary(result))
        selected.append(result)
    return sorted(selected, key=_sort_key)


def _stable_id(item: dict[str, Any]) -> str:
    raw = "|".join(str(item.get(key, "")) for key in ("ticker", "time", "subject", "attachment_link"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def save_announcements(items: Iterable[dict[str, Any]]) -> int:
    clean_items = deduplicate_announcements(items)
    initialize_database()
    with database_connection() as connection:
        for item in clean_items:
            item_id = str(item.get("id") or _stable_id(item))
            connection.execute(
                """INSERT OR REPLACE INTO announcements
                   (id, ticker, company, time, subject, category, attachment_link, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item_id,
                    str(item.get("ticker", "")).upper(),
                    str(item.get("company", "")),
                    str(item.get("time", "")),
                    str(item.get("subject", "")),
                    item["category"],
                    str(item.get("attachment_link", "")),
                    str(item.get("source", "NSE")),
                ),
            )
    return len(clean_items)


def list_digest(hours: int = 24, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            """SELECT id, ticker, company, time, subject, category, attachment_link, source
               FROM announcements"""
        ).fetchall()
    items = [dict(row) for row in rows]
    if not items and ANNOUNCEMENT_FIXTURE.is_file():
        items = json.loads(ANNOUNCEMENT_FIXTURE.read_text(encoding="utf-8"))
    return build_digest(items, hours=hours, now=now)
