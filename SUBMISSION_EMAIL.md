Hello,

I built FINN, a phone-first investor research prototype for an 18-company Indian equity watchlist. It has a Push digest and price/volume alerts, plus Pull research pages with financial statement trends and simple calculated metrics.

I made the demo fixtures-first so it can start without a database or internet connection. Prices and saved Screener.in research load from checked-in fixtures, and the app labels announcements as sample data because NSE and BSE blocked automated downloads. The fetch scripts are included for live use when those sources are accessible. I kept the financial calculations in Python rather than asking AI to calculate them, and packaged the frontend and API as one deployable service.

I deliberately left out earnings-call transcripts and promised-versus-delivered analysis, annual report ingestion, management-change background lookup, Gemini features, and live NSE/BSE announcements. Those would need more source handling and validation than I could responsibly add to this prototype.

Next, I would add documented primary-source ingestion with stronger date and ticker validation, persistent hosted storage, and source-linked research claims. I would then add transcript and annual-report workflows with clear coverage and missing-data states, followed by carefully scoped Gemini summaries that cite only supplied source documents.

Regards,

Deepika
