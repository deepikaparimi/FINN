"""Price history, alert rules, and alerts derived from stored daily data."""

import json
import math
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Optional

from .db import ROOT_DIR, database_connection, initialize_database


PORTFOLIO_PATH = ROOT_DIR / "config" / "portfolio.json"
FIXTURE_PATH = ROOT_DIR / "fixtures" / "prices.json"
LEGACY_SAMPLE_PATH = ROOT_DIR / "data" / "sample" / "price_history.json"
DEFAULT_RULES = {"volume_multiplier": 2.0, "price_change_percent": 3.0}
VOLUME_LOOKBACK_DAYS = 20
HISTORY_DAYS = 60


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        date = str(row["date"])[:10]
        close = float(row["close"])
        volume = int(row["volume"])
        if not math.isfinite(close) or close <= 0 or volume < 0:
            continue
        result.append({"date": date, "close": close, "volume": volume})
    return sorted(result, key=lambda row: row["date"])[-HISTORY_DAYS:]


def _download_yfinance(ticker: str) -> list[dict[str, Any]]:
    """Download up to 60 calendar days of daily NSE data using yfinance."""
    import yfinance as yf

    frame = yf.download(
        f"{ticker}.NS",
        period="60d",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if frame is None or frame.empty:
        return []

    close = frame["Close"]
    volume = frame["Volume"]
    # yfinance may return a one-column DataFrame for a single ticker.
    if getattr(close, "ndim", 1) > 1:
        close = close.iloc[:, 0]
    if getattr(volume, "ndim", 1) > 1:
        volume = volume.iloc[:, 0]

    rows = []
    for date, value in close.items():
        raw_volume = volume.loc[date]
        if hasattr(raw_volume, "iloc"):
            raw_volume = raw_volume.iloc[0]
        if hasattr(value, "item"):
            value = value.item()
        if hasattr(raw_volume, "item"):
            raw_volume = raw_volume.item()
        try:
            rows.append({
                "date": str(date)[:10],
                "close": float(value),
                "volume": int(raw_volume),
            })
        except (TypeError, ValueError, OverflowError):
            continue
    return _clean_rows(rows)


def _sample_rows() -> dict[str, list[dict[str, Any]]]:
    path = FIXTURE_PATH if FIXTURE_PATH.is_file() else LEGACY_SAMPLE_PATH
    sample = _load_json(path)
    return {
        ticker: _clean_rows(rows)
        for ticker, rows in sample["prices"].items()
    }


def replace_ticker_prices(
    ticker: str, rows: Iterable[dict[str, Any]], source: str,
    connection: Optional[sqlite3.Connection] = None,
) -> int:
    cleaned = _clean_rows(rows)
    if not cleaned:
        raise ValueError(f"No valid daily price rows for {ticker}")
    owns_connection = connection is None
    connection = connection or database_connection()
    try:
        connection.execute("DELETE FROM daily_prices WHERE ticker = ?", (ticker,))
        connection.executemany(
            """INSERT INTO daily_prices (ticker, trade_date, close, volume, source)
               VALUES (?, ?, ?, ?, ?)""",
            [(ticker, row["date"], row["close"], row["volume"], source) for row in cleaned],
        )
        if owns_connection:
            connection.commit()
    finally:
        if owns_connection:
            connection.close()
    return len(cleaned)


def refresh_price_history(allow_download: bool = True) -> dict[str, Any]:
    """Refresh the full portfolio; use the saved per-ticker sample on failure."""
    initialize_database()
    portfolio = _load_json(PORTFOLIO_PATH)
    samples = _sample_rows()
    counts = {"yfinance": 0, "saved_sample": 0}
    tickers_without_sample = []
    downloaded: dict[str, list[dict[str, Any]]] = {}
    refreshed: dict[str, list[dict[str, Any]]] = {}
    refreshed_sources: dict[str, str] = {}

    if allow_download:
        for company in portfolio:
            ticker = company["ticker"]
            try:
                rows = _download_yfinance(ticker)
            except Exception:
                rows = []
            if rows:
                downloaded[ticker] = rows

    latest_live_date = min(
        rows[-1]["date"] for rows in downloaded.values()
    ) if downloaded else None

    with database_connection() as connection:
        for company in portfolio:
            ticker = company["ticker"]
            rows = downloaded.get(ticker, [])
            source = "yfinance" if rows else "saved_sample"
            if not rows:
                rows = samples.get(ticker, [])
                if rows and latest_live_date:
                    offset = date.fromisoformat(latest_live_date) - date.fromisoformat(rows[-1]["date"])
                    rows = [
                        {**row, "date": (date.fromisoformat(row["date"]) + offset).isoformat()}
                        for row in rows
                    ]
            if not rows:
                tickers_without_sample.append(ticker)
                continue
            replace_ticker_prices(ticker, rows, source, connection)
            counts[source] += 1
            refreshed[ticker] = rows
            refreshed_sources[ticker] = source
        connection.commit()

    if tickers_without_sample:
        raise RuntimeError(
            "No downloaded or saved price history for: " + ", ".join(tickers_without_sample)
        )
    latest_date = get_latest_price_date()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(
            {
                "as_of": latest_date,
                "is_live": counts["saved_sample"] == 0,
                "notice": "Rows marked saved_sample are illustrative fallback data, not live prices.",
                "sources": refreshed_sources,
                "prices": refreshed,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return {
        "as_of": latest_date,
        "companies_updated": sum(counts.values()),
        "sources": counts,
        "is_live": counts["saved_sample"] == 0,
    }


def get_latest_price_date() -> Optional[str]:
    with database_connection() as connection:
        row = connection.execute("SELECT MAX(trade_date) AS latest FROM daily_prices").fetchone()
    return row["latest"] if row else None


def list_prices(ticker: Optional[str] = None) -> list[dict[str, Any]]:
    with database_connection() as connection:
        if ticker:
            rows = connection.execute(
                """SELECT ticker, trade_date, close, volume, source
                   FROM daily_prices WHERE ticker = ?
                   ORDER BY trade_date DESC LIMIT ?""",
                (ticker.upper(), HISTORY_DAYS),
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT ticker, trade_date, close, volume, source
                   FROM daily_prices ORDER BY ticker, trade_date DESC"""
            ).fetchall()
    result = [
        {"ticker": row["ticker"], "date": row["trade_date"], "close": row["close"],
         "volume": row["volume"], "source": row["source"]}
        for row in rows
    ]
    if result:
        return result

    # An empty database can still serve the checked-in fixture without a fetch.
    fixture = _load_json(FIXTURE_PATH if FIXTURE_PATH.is_file() else LEGACY_SAMPLE_PATH)
    sources = fixture.get("sources", {})
    fixture_rows = [
        {"ticker": symbol, **row, "source": sources.get(symbol, fixture.get("source", "saved_sample"))}
        for symbol, history in fixture.get("prices", {}).items()
        if ticker is None or symbol == ticker.upper()
        for row in history
    ]
    return sorted(fixture_rows, key=lambda row: (row["ticker"], row["date"]), reverse=True)


def get_alert_rules() -> dict[str, float]:
    initialize_database()
    with database_connection() as connection:
        row = connection.execute(
            """SELECT volume_multiplier, price_change_percent
               FROM alert_rules WHERE id = 1"""
        ).fetchone()
    return {
        "volume_multiplier": float(row["volume_multiplier"]),
        "price_change_percent": float(row["price_change_percent"]),
        "volume_lookback_days": VOLUME_LOOKBACK_DAYS,
    }


def update_alert_rules(volume_multiplier: float, price_change_percent: float) -> dict[str, float]:
    if not math.isfinite(volume_multiplier) or volume_multiplier <= 0:
        raise ValueError("volume_multiplier must be a positive number")
    if not math.isfinite(price_change_percent) or price_change_percent <= 0:
        raise ValueError("price_change_percent must be a positive number")
    initialize_database()
    with database_connection() as connection:
        connection.execute(
            """UPDATE alert_rules
               SET volume_multiplier = ?, price_change_percent = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = 1""",
            (volume_multiplier, price_change_percent),
        )
    return get_alert_rules()


def list_alerts() -> dict[str, Any]:
    rules = get_alert_rules()
    with database_connection() as connection:
        latest = connection.execute(
            "SELECT MAX(trade_date) AS latest FROM daily_prices"
        ).fetchone()["latest"]
        if not latest:
            return {"as_of": None, "is_live": False, "alerts": []}
        companies = _load_json(PORTFOLIO_PATH)
        names = {company["ticker"]: company["company_name"] for company in companies}
        tickers = connection.execute(
            "SELECT DISTINCT ticker FROM daily_prices WHERE trade_date = ? ORDER BY ticker",
            (latest,),
        ).fetchall()
        alerts = []
        source_rows = connection.execute(
            "SELECT DISTINCT source FROM daily_prices WHERE trade_date = ?", (latest,)
        ).fetchall()
        for item in tickers:
            ticker = item["ticker"]
            history = connection.execute(
                """SELECT trade_date, close, volume FROM daily_prices
                   WHERE ticker = ? AND trade_date <= ?
                   ORDER BY trade_date DESC LIMIT ?""",
                (ticker, latest, VOLUME_LOOKBACK_DAYS + 1),
            ).fetchall()
            if len(history) < 2:
                continue
            current, previous = history[0], history[1]
            change = (current["close"] - previous["close"]) / previous["close"] * 100
            base = {
                "ticker": ticker,
                "company_name": names.get(ticker, ticker),
                "date": current["trade_date"],
            }
            if abs(change) > rules["price_change_percent"]:
                alerts.append({
                    **base,
                    "type": "price_move",
                    "value": round(change, 2),
                    "threshold": rules["price_change_percent"],
                    "summary": f"Price moved {change:+.2f}% in one session.",
                })
            if len(history) >= VOLUME_LOOKBACK_DAYS + 1:
                average_volume = sum(row["volume"] for row in history[1:]) / VOLUME_LOOKBACK_DAYS
                multiple = current["volume"] / average_volume if average_volume else 0
                if multiple > rules["volume_multiplier"]:
                    alerts.append({
                        **base,
                        "type": "volume_spike",
                        "value": round(multiple, 2),
                        "threshold": rules["volume_multiplier"],
                        "average_volume_20d": round(average_volume),
                        "summary": f"Volume is {multiple:.2f}x its 20-session average.",
                    })
    sources = {row["source"] for row in source_rows}
    return {
        "as_of": latest,
        "is_live": sources == {"yfinance"},
        "rules": rules,
        "alerts": alerts,
    }
