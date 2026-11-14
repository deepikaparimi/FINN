import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import initialize_database
from .fixture_bootstrap import seed_from_fixtures
from .market_data import (
    get_alert_rules,
    list_alerts,
    list_prices,
    refresh_price_history,
    update_alert_rules,
)
from .push import build_digest_response, list_digest
from .research import research_response


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
CONFIG_DIR = ROOT_DIR / "config"

app = FastAPI(title="FINN", version="0.1.0")


class AlertRulesUpdate(BaseModel):
    volume_multiplier: float = Field(gt=0, le=100)
    price_change_percent: float = Field(gt=0, le=100)


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    app.state.fixtures_loaded = seed_from_fixtures()


def read_config(filename: str) -> Any:
    path = CONFIG_DIR / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Project configuration could not be loaded") from error


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "finn-api"}


@app.get("/api/portfolio")
def portfolio() -> Any:
    return read_config("portfolio.json")


@app.get("/api/research-demo")
def research_demo() -> Any:
    return read_config("research_demo.json")


@app.get("/api/research/{ticker}")
def company_research(ticker: str) -> dict[str, Any]:
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9&._-]{1,30}", symbol):
        return {
            "found": False,
            "ticker": symbol,
            "message": "Enter a valid NSE ticker symbol.",
        }
    price_rows = list_prices(symbol)
    latest_price = max(price_rows, key=lambda row: row["date"]) if price_rows else None
    return research_response(symbol, latest_price["close"] if latest_price else None)


@app.get("/api/prices")
def prices(ticker: Optional[str] = Query(default=None, min_length=1)) -> dict[str, Any]:
    rows = list_prices(ticker)
    return {"count": len(rows), "prices": rows}


@app.post("/api/prices/refresh")
def refresh_prices() -> dict[str, Any]:
    try:
        return refresh_price_history(
            allow_download=os.getenv("FINN_OFFLINE", "0") != "1"
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/alert-rules")
@app.get("/api/alerts/rules")
def read_alert_rules() -> dict[str, float]:
    return get_alert_rules()


@app.put("/api/alert-rules")
@app.put("/api/alerts/rules")
def write_alert_rules(rules: AlertRulesUpdate) -> dict[str, float]:
    try:
        return update_alert_rules(rules.volume_multiplier, rules.price_change_percent)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/alerts/today")
@app.get("/api/alerts")
def today_alerts() -> dict[str, Any]:
    return list_alerts()


@app.get("/api/digest")
def digest(hours: int = Query(default=24, ge=1, le=336)) -> dict[str, Any]:
    response = build_digest_response(list_digest(hours=hours), list_prices(), get_alert_rules())
    return {"hours": hours, **response}


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}")
def serve_frontend(path: str = "") -> FileResponse:
    index_file = FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    raise HTTPException(status_code=503, detail="Frontend is not built yet. Run the frontend build step in README.md.")
