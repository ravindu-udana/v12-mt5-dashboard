# V10 MT5 Live Dashboard

This repository contains the completely upgraded V10 Dashboard that connects directly to the MT5 IC Market data feed.

## Components
- `mt5_only_fetcher.py`: Fetches 1-minute OHLC data from the MT5 bridge every 5 seconds, converts broker time to True UTC, and continuously upserts into `mt5_gold.db`.
- `app.py`: FastAPI server that reads the 600 latest candles from `mt5_gold.db` every 1 second, saves historical records to `wizard_v7.db`, and broadcasts live candle updates over WebSockets.
- `database.py`: Helper script to manage `wizard_v7.db` schema and CRUD operations.
- `static/index.html`: The fully upgraded edge-to-edge UI with the 200 SMA on a unified axis to prevent rendering bugs.
- `static/style.css`: The styling for the dashboard.
