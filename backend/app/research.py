"""Deterministic financial calculations and saved Pull data access."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .db import ROOT_DIR, database_connection, get_database_path, initialize_database


FIXTURE_DIR = ROOT_DIR / "fixtures" / "research"
TABLES = ("profit_loss", "balance_sheet", "cash_flow", "ratios")


def _normalise_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _row_values(table: dict[str, Any], aliases: Iterable[str]) -> list[Optional[float]]:
    rows = table.get("rows", {})
    normalised = {_normalise_label(label): values for label, values in rows.items()}
    for alias in aliases:
        values = normalised.get(_normalise_label(alias))
        if values is not None:
            return [None if value is None else float(value) for value in values]
    return []


def _latest(values: list[Optional[float]]) -> tuple[Optional[int], Optional[float]]:
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return index, values[index]
    return None, None


def _previous_value(values: list[Optional[float]], index: Optional[int]) -> Optional[float]:
    if index is None:
        return None
    for position in range(index - 1, -1, -1):
        if values[position] is not None:
            return values[position]
    return None


def _growth(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def _series(table: dict[str, Any], aliases: Iterable[str]) -> list[Optional[float]]:
    return _row_values(table, aliases)


def _latest_metric(values: list[Optional[float]]) -> Optional[float]:
    return _latest(values)[1]


def calculate_metrics(document: dict[str, Any]) -> dict[str, Any]:
    """Calculate headline metrics from Screener's saved annual statement rows."""
    tables = document.get("tables", {})
    pnl = tables.get("profit_loss", {})
    balance = tables.get("balance_sheet", {})
    cash = tables.get("cash_flow", {})
    periods = list(pnl.get("periods", []))

    revenue = _series(pnl, ("Sales", "Revenue from operations", "Revenue", "Total revenue"))
    profit = _series(pnl, ("Net Profit", "Profit after tax", "PAT", "Net income"))
    operating_profit = _series(pnl, ("Operating Profit", "EBIT", "EBITDA"))
    revenue_index, latest_revenue = _latest(revenue)
    profit_index, latest_profit = _latest(profit)
    _, previous_revenue = _latest((_previous_value(revenue, revenue_index),))
    _, previous_profit = _latest((_previous_value(profit, profit_index),))
    latest_operating_profit = _latest_metric(operating_profit)

    borrowings = _latest_metric(_series(balance, ("Borrowings", "Total Borrowings", "Debt", "Total Debt")))
    direct_equity = _latest_metric(_series(balance, ("Total Equity", "Shareholders Equity", "Total Shareholders Equity")))
    reserves = _latest_metric(_series(balance, ("Reserves", "Other Equity")))
    equity_capital = _latest_metric(_series(balance, ("Equity Capital", "Share Capital")))
    equity = direct_equity if direct_equity is not None else (
        (reserves or 0) + (equity_capital or 0) if reserves is not None or equity_capital is not None else None
    )
    debt_to_equity = borrowings / equity if borrowings is not None and equity not in (None, 0) else None

    operating_cash = _series(cash, (
        "Cash from Operating Activity", "Cash from Operating Activities", "Operating Cash Flow",
        "Cash generated from operations",
    ))
    investing_cash = _series(cash, (
        "Cash from Investing Activity", "Cash from Investing Activities", "Investing Cash Flow",
    ))
    capex = _series(cash, (
        "Capital Expenditure", "Capex", "Purchase of Fixed Assets", "Fixed Assets Purchased",
        "Purchase of Property Plant and Equipment",
    ))
    latest_operating_cash = _latest_metric(operating_cash)
    latest_investing_cash = _latest_metric(investing_cash)
    latest_capex = _latest_metric(capex)
    if latest_operating_cash is None:
        free_cash_flow = None
        free_cash_flow_method = "unavailable"
    elif latest_capex is not None:
        free_cash_flow = latest_operating_cash - abs(latest_capex)
        free_cash_flow_method = "operating cash flow less capital expenditure"
    elif latest_investing_cash is not None:
        free_cash_flow = latest_operating_cash + latest_investing_cash
        free_cash_flow_method = "operating cash flow plus investing cash flow proxy"
    else:
        free_cash_flow = None
        free_cash_flow_method = "unavailable"

    cash_conversion = latest_operating_cash / latest_profit if latest_operating_cash is not None and latest_profit not in (None, 0) else None
    net_margin = latest_profit / latest_revenue * 100 if latest_profit is not None and latest_revenue not in (None, 0) else None
    operating_margin = latest_operating_profit / latest_revenue * 100 if latest_operating_profit is not None and latest_revenue not in (None, 0) else None

    revenue_growth = [_growth(value, _previous_value(revenue, index)) for index, value in enumerate(revenue)]
    profit_growth = [_growth(value, _previous_value(profit, index)) for index, value in enumerate(profit)]
    count = max(len(periods), len(revenue), len(profit))
    periods = (periods + [f"Period {index + 1}" for index in range(len(periods), count)])[:count]

    ratios_table = tables.get("ratios", {})
    ratios = {label: values for label, values in ratios_table.get("rows", {}).items()}
    return {
        "periods": periods,
        "trajectory": {
            "revenue": revenue,
            "profit": profit,
            "revenue_growth_percent": revenue_growth,
            "profit_growth_percent": profit_growth,
        },
        "snapshot": {
            "period": periods[revenue_index] if revenue_index is not None and revenue_index < len(periods) else None,
            "revenue": latest_revenue,
            "profit": latest_profit,
            "revenue_growth_percent": _growth(latest_revenue, previous_revenue),
            "profit_growth_percent": _growth(latest_profit, previous_profit),
            "net_margin_percent": net_margin,
            "operating_margin_percent": operating_margin,
        },
        "balance_sheet": {
            "period": _latest_period(tables.get("balance_sheet", {})),
            "borrowings": borrowings,
            "equity": equity,
            "debt_to_equity": debt_to_equity,
        },
        "cash_quality": {
            "period": _latest_period(tables.get("cash_flow", {})),
            "operating_cash_flow": latest_operating_cash,
            "profit_after_tax": latest_profit,
            "cash_conversion": cash_conversion,
            "free_cash_flow": free_cash_flow,
            "free_cash_flow_method": free_cash_flow_method,
        },
        "ratios": ratios,
    }


def _latest_period(table: dict[str, Any]) -> Optional[str]:
    periods = table.get("periods", [])
    rows = table.get("rows", {})
    for values in rows.values():
        for index in range(len(values) - 1, -1, -1):
            if values[index] is not None:
                return periods[index] if index < len(periods) else None
    return periods[-1] if periods else None


def save_research_document(document: dict[str, Any]) -> Path:
    ticker = str(document["ticker"]).upper()
    document["ticker"] = ticker
    document["metrics"] = calculate_metrics(document)
    initialize_database()
    with database_connection() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO research_data (ticker, payload, source_mode, saved_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (ticker, json.dumps(document, ensure_ascii=False), document.get("source_mode", "consolidated")),
        )
    return get_database_path()


def get_research_document(ticker: str) -> Optional[dict[str, Any]]:
    symbol = ticker.upper()
    initialize_database()
    with database_connection() as connection:
        row = connection.execute("SELECT payload, saved_at FROM research_data WHERE ticker = ?", (symbol,)).fetchone()
    if row:
        document = json.loads(row["payload"])
        document["saved_at"] = row["saved_at"]
        return document
    fixture_path = FIXTURE_DIR / f"{symbol}.json"
    if fixture_path.is_file():
        document = json.loads(fixture_path.read_text(encoding="utf-8"))
        document["saved_at"] = datetime.fromtimestamp(fixture_path.stat().st_mtime).isoformat(timespec="seconds")
        return document
    return None


def research_response(ticker: str, price: Optional[float] = None) -> dict[str, Any]:
    document = get_research_document(ticker)
    if document is None:
        return {
            "found": False,
            "ticker": ticker.upper(),
            "message": f"No saved financial tables for {ticker.upper()}. Run scripts/ingest.py {ticker.upper()} to fetch them.",
        }
    if "metrics" not in document:
        document["metrics"] = calculate_metrics(document)
    return {
        "found": True,
        **document,
        "company_name": document.get("company", ticker.upper()),
        "price": price,
    }
