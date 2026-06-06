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
pipenv run python main.py
```

> **Do NOT auto-start the app.** Only run this when explicitly asked by the user.

## Startup

- Python 3.13. Environment managed via **pipenv** (`Pipfile` + `Pipfile.lock` in `trading_bot/`).
- Create the venv and install dependencies: `pipenv install` (reads `Pipfile`, venv goes to `~/.virtualenvs/trading_bot-*/`).
- To run a one-off command: `pipenv run <command>`.
- To activate an interactive shell: `pipenv shell`.
- Dependencies: ccxt, pandas, numpy, pytz, pyqt6, pyqtgraph.
- If `pipenv` is not on PATH:
  ```powershell
  pip install pipenv
  & "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\pipenv.exe" run python main.py
  ```

## Architecture

```
main.py (entry point — QApplication + dark theme)
main_window.py (QMainWindow with QTabWidget navigation)
state.py (AppState dataclass — replaces st.session_state)

core/        Strategy* (5 strategies) + backtest_engine.py + metrics.py
data/        ohlcv.py (fetch OHLCV via CCXT, cache to parquet)
exchange/    connector.py (thin CCXT wrapper, 111 exchanges)

widgets/
├── settings_panel.py     Exchange config + API keys + backtest defaults
├── backtest_panel.py     Strategy params (5 strategies) + Run button + QThread + summary
├── statistics_panel.py   QTableWidget-based metrics + trade log + CSV export
├── charts_panel.py       QTabWidget with 3 chart tabs (equity, monthly, trade)
└── chart_widgets.py      PyQtGraph plot builders (equity, histogram, scatter) + ChartViewBox
```

- App state lives in `MainWindow.state` (an `AppState` instance), referenced by all panels.
- Backtest runs in a **QThread** — UI stays responsive during fetch + strategy + backtest.
- No persistence layer — all results live in `AppState`, lost on restart.
- No tests, no CI, no pre-commit, no lint/typecheck config.

## Key conventions & gotchas

- **All strategies return DataFrame with `signal`/`entry_price`/`sl_price`/`tp_price` columns.**
- **Entry is at next bar open** (not signal bar close). SL/TP are auto-shifted relative to the actual entry price in `backtest_engine.py` (`diff = entry_price - prev_entry`).
- **Strategies imported explicitly** inside `BacktestWorker.run()` — a syntax error in a strategy file appears only when "Run Backtest" is clicked.
- **4H NY Range Re-Entry** accepts both `df_5m` (signal generation) and `df_4h` (range calculation). Worker fetches both timeframes separately.
- **ATR Trend-Breakout** uses 4H data only (fetched directly). All other strategies use 5M data only.
- **ATR Trend-Breakout** passes `trail_activation_atr` and `trail_offset_atr` to `run_backtest()` for trailing stop support. Other strategies leave them at 0 (disabled).
- **Max 1 open trade at a time** — no pyramiding, no concurrent positions.
- **Slippage is always 0.0** — no UI slider exists.
- **NY range strategies** use `America/New_York` timezone via `pytz`. Daily range = midnight–4am NY time.
- **Fee input stores as %** in widget, converts to decimal in two places: in `settings_panel.py` for `state.fee_rate`, and in `backtest_panel.py:_on_run()` for strategy params (`params["fee_rate"] /= 100`).
- **4H NY Range SL logic**: two-step swing filter: (1) find nearest swing, (2) if swing is beyond range midpoint (>50% from the lower boundary for shorts, <50% for longs), skip it and find the swing closest to the breakout boundary (`range_high` for shorts, `range_low` for longs). Uses `_find_swing_high_closest_to` / `_find_swing_low_closest_to`.
- **Position sizing guard**: `run_backtest` checks `equity > 0` before computing quantity; if equity is wiped, `quantity=0`.
- **`resample_to_4h()` in `data/ohlcv.py` is dead code** — defined but never called.
- **CCXT exchanges** are accessed via `getattr(ccxt, exchange_id)` — any CCXT-supported ID works.
- **Charts panel** has 3 tabs (Equity & Drawdown, Monthly Returns, Trade Analysis). Price + Signals tab was removed.
- **PyQtGraph symbols**: use `"t"` for triangle-up, `"t1"` for triangle-down, `"x"` for cross.
- **Crosshair** connects deferred via QTimer; scene must be available for `sigMouseMoved`.
- **Old Streamlit files** (`app.py`, `pages/`, `components/`) still exist on disk but are unused.

## Live bot (ATR Trend-Breakout on Bybit perp)

```
live/
├── config.py              JSON load/save (exchange, keys, params, position state)
├── position_manager.py    SL/TP/trail math (mirrors backtest_engine.py logic)
├── executor.py            PaperExecutor (simulated fills) + LiveExecutor (CCXT Bybit orders)
├── engine.py              Main loop — poll 4H OHLCV every 60s, run strategy, manage position
└── run.py                 CLI entry point
config.json                Saved settings (gitignored — never commit API keys)
```

### Run (paper mode — default)

```powershell
cd trading_bot
pipenv run python live/run.py
```

Creates `config.json` on first run with defaults (`mode: "paper"`). Logs go to `live/logs/bot.log`.

### Switching to live

1. Add API keys to `config.json` (`api_key`, `api_secret`)
2. Change `"mode": "paper"` → `"mode": "live"`
3. Verify on Bybit testnet first (config: `exchange_id: "bybit"`, use testnet keys)

### Safety

- Default mode is `"paper"` — no real orders
- Max daily loss guard (`max_daily_loss_pct: 10.0`) — logs warning when hit
- Max drawdown guard (`max_drawdown_pct: 20.0`) — logs warning when hit
- Position persisted in `config.json` — bot survives restart
- On first run, the bot skips the first candle (only trades new 4H candles after startup)
