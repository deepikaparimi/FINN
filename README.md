# FINN

FINN is a phone-first investor research prototype for an Indian equity portfolio. **Push** gives a daily digest of company announcements and alerts for unusual price or volume moves. **Pull** opens saved financial statements and deterministic metrics for a ticker.

## How it works

The React frontend is built into static files and served by the same FastAPI service as the API. SQLite stores prices, announcements, alert settings, cached downloads, and saved research. Financial comparisons and alert rules are calculated in Python; they do not depend on an AI model.

On a new or empty database, the server reads `fixtures/prices.json`, `fixtures/announcements.json`, and `fixtures/research/*.json` into SQLite. This startup path is offline and does not call a provider. It does not modify the research fixtures. Announcements from the checked-in fixture are labelled `sample`; the shared status line shows **Showing saved sample data** while sample announcements are being displayed.

The checked-in price fixture contains Yahoo Finance data. Research tables in `fixtures/research/` were collected from screener.in. Announcements are illustrative sample data: NSE and BSE blocked automated downloads. The fetch scripts are included for live use when exchange access is available.

## Run locally

Requirements: Python 3.9 or newer, Node.js 18 or newer, and npm.

From the project root:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Check <http://127.0.0.1:8000/api/health>. To run the local fixture tests, in another terminal from the project root:

```bash
source .venv/bin/activate
python3 -m pytest backend/tests
```

The first server start creates `backend/data/finn.sqlite3`. Set `DATABASE_PATH` to use a different SQLite path. Leave `GEMINI_API_KEY` blank unless you add an AI feature that uses it.

## Update data when online

These commands fetch external data and are deliberately not part of startup or tests:

```bash
source .venv/bin/activate
python3 scripts/fetch_prices.py
python3 scripts/fetch_announcements.py
python3 scripts/ingest.py RELIANCE
```

`fetch_prices.py` uses Yahoo Finance. `fetch_announcements.py` tries NSE and then BSE. `ingest.py` reads Screener pages. Review any refreshed data before submitting it. Keep the saved fixtures in the repository so an offline demo can be rebuilt.

## Deploy with Docker

Build and run the one-service image from the project root:

```bash
docker build -t finn:submission .
docker run --rm -p 8000:8000 -e PORT=8000 finn:submission
```

Open <http://127.0.0.1:8000>. The image builds the frontend with Node, installs the backend on Python 3.11, and serves both from one Uvicorn process. For Render, connect this repository and deploy its `render.yaml` Docker web service. Set `GEMINI_API_KEY` manually in the Render dashboard if needed; it is not committed. The Render free plan sleeps when idle, so the first request after a quiet period may take longer.

## Deliberately out of scope

- Earnings call transcripts and promised-versus-delivered analysis
- Annual report ingestion
- Background lookup for management changes
- Gemini-powered features
- Live NSE/BSE announcements in the demo

## Known limitations

- Announcement entries are fictional examples for UI demonstration and are explicitly labelled sample data.
- The 18-company portfolio is the current demonstration watchlist; the APIs can use other tickers when matching source data is available.
- The saved price fixture becomes stale until refreshed. The fixture itself can also contain sample fallback rows; check each row's source before treating it as current market data.
- Research depends on the supplied Screener-derived fixtures or a successful manual ingest. It does not fetch missing research on request.
- SQLite data written on a free hosted container may be ephemeral across restarts or redeploys. The checked-in fixtures restore the initial demo dataset.
- Financial ratios and free cash flow are simple calculations from available annual statement rows. Missing inputs remain unavailable, and investing cash flow may be used as a free-cash-flow proxy when direct capex is absent.
- There is no user account or portfolio editor, and the app is a prototype rather than investment advice.

## Project layout

- `backend/app/` — FastAPI, SQLite, fixture bootstrap, Python calculations
- `frontend/src/` — React interface
- `config/` — current portfolio and research demo settings
- `fixtures/` — price, sample announcement, and research source data
- `scripts/` — manual price, announcement, and research fetchers
- `backend/tests/` — local unit and fixture-backed API tests
