# AGENTS.md — Crypto Trading Bot

## Session continuity

At session start, read `session_log/LATEST.md` if it exists to pick up context.
If the user requests a summary at session end, write the current session details
to `session_log/LATEST.md` (overwrite with new summary).

Custom command: `/createsummary` is defined in `opencode.json` — triggers the
agent to review all session changes and update `session_log/LATEST.md`.

## Run

```powershell
cd trading_bot
pipenv run streamlit run app.py
# Opens at http://localhost:8501
```

> **Do NOT auto-start the app.** Only run this when explicitly asked by the user.

## Startup

- Python 3.13. Environment managed via **pipenv** (`Pipfile` + `Pipfile.lock` in `trading_bot/`).
- Create the venv and install dependencies: `pipenv install` (reads `Pipfile`, venv goes to `~/.virtualenvs/trading_bot-*/`).
- To run a one-off command: `pipenv run <command>`.
- To activate an interactive shell: `pipenv shell`.
- Dependencies: streamlit, ccxt, pandas, numpy, plotly, pytz.
- If `pipenv` is not on PATH, install it and use the full path:
  ```powershell
  pip install pipenv
  & "$env:APPDATA\..\Local\Programs\Python\Python313\Scripts\pipenv.exe" run streamlit run app.py
  ```

## Architecture

```
app.py (home + sidebar nav)
  pages/      4 Streamlit pages (backtest, statistics, charts, settings)
  core/       strategy*.py (4 strategies) + backtest_engine.py + metrics.py
  data/       ohlcv.py (fetch OHLCV via CCXT, cache to parquet)
  exchange/   connector.py (thin CCXT wrapper, 111 exchanges)
  components/ charts.py (5 Plotly figure builders)
```

- No persistence layer — all results live in `st.session_state`, lost on server restart.
- No tests, no CI, no pre-commit, no lint/typecheck config.
- `.gitignore` missing — `cache/`, `__pycache__/`, and `secrets.toml` with real keys risk accidental commit.

## Key conventions & gotchas

- **All 4 strategies accept 5M OHLCV DataFrame, return DataFrame with `signal`/`entry_price`/`sl_price`/`tp_price` columns.**
- **Entry is at next bar open** (not signal bar close). SL/TP are auto-shifted relative to the actual entry price in `backtest_engine.py` (`diff = entry_price - prev_entry`).
- **Strategies imported lazily** inside `if run:` block in `backtest.py` — a syntax error in a strategy file appears only when selected and "Run Backtest" is clicked.
- **Max 1 open trade at a time** — no pyramiding, no concurrent positions.
- **Only V2 Range Re-Entry sets `max_hold_bars=288`** (24h force-close). Others default to 0 (unlimited).
- **Slippage is always 0.0** — no UI slider exists.
- **NY range strategies** use `America/New_York` timezone via `pytz`. Daily range = midnight–4am NY time.
- **Fee input stores as %** in widget, converts to decimal: `session_state.fee_rate = widget_value / 100`.
- **`resample_to_4h()` in `data/ohlcv.py` is dead code** — defined but never called.
- **Starlette version pinning** may be needed: `pip install "starlette>=0.46"` if streamlit fails with `ImportError: cannot import name 'DEFAULT_EXCLUDED_CONTENT_TYPES'`.
- **CCXT exchanges** are accessed via `getattr(ccxt, exchange_id)` — any CCXT-supported ID works.
