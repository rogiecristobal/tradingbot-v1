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
- Dependencies: ccxt, pandas, numpy, pytz, python-telegram-bot, pyarrow, feedparser.
- If `pipenv` is not on PATH:
  ```powershell
  pip install pipenv
  & "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\pipenv.exe" run python main.py
  ```

## Termux (Android)

See `SETUP_TERMUX.md` for full guide. The Streamlit web UI is the recommended
way to use the bot on a phone.

```bash
pkg install python git openssl-tool binutils -y
cd trading_bot
cp .env.example .env          # then nano .env to fill in keys
pip install -r requirements.txt

# Web UI (backtest + live bot control) — opens at http://localhost:8501
streamlit run streamlit_app.py

# CLI backtest only
python backtest_cli.py --symbol ETH/USDT --strategy atr-breakout

# Headless live bot only
python -m live.run
```

The Streamlit UI has two pages:
- **Backtest** — all 5 strategies with Plotly charts, trade log, monthly returns
- **Live Bot** — start/stop bot, view positions, tail logs, edit config

A CLI backtest script (`backtest_cli.py`) is also available. Run `python backtest_cli.py --help` for options.

## Architecture

```
main.py (entry point — QApplication + dark theme)
main_window.py (QMainWindow with QTabWidget navigation)
state.py (AppState dataclass — replaces st.session_state)

core/        Strategy* (4 strategies) + backtest_engine.py + metrics.py
data/        ohlcv.py (fetch OHLCV via CCXT, cache to parquet)
exchange/    connector.py (thin CCXT wrapper, 111 exchanges)

widgets/
├── settings_panel.py     Exchange config + API keys + backtest defaults
├── backtest_panel.py     Strategy params (4 strategies) + Run button + QThread + summary
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
- **ATR Trend-Breakout** uses 4H data only (fetched directly). 5M Trend Pullback uses 5M data.
- **IBR (Institutional Breakout Retest)** uses 15M data only. Resamples 1H and 4H internally from 15M using `df.resample("1h")` / `df.resample("4h")`. Lookahead is prevented by shifting resampled 1H/4H data +1 period before merging into 15M.
- **IBR swing detection** uses no-lookahead rolling max/min (past `swing_window` bars only, no `center=True`). Swing points are updated after zone checks in the 1H loop.
- **IBR FVG**: hybrid model — strict FVG (gap between 1H lows/highs) scores 2, imbalance FVG (displacement > 1 ATR + body > 60% range) scores 1. Both must accompany an impulse candle (range > 1.5 ATR) breaking a swing pivot to create a zone.
- **IBR scoring**: 7-point system — trend(1) + zone+fvg(1-2) + structure break(1) + retest(1) + price action engulfing/pin bar(1) + volume surge(1). Entry if score ≥ 4. Zone disabled after 2 retests.
- **IBR SL**: for buys, the lower of the swing price and zone low. For sells, the higher of the swing price and zone high.
- **ATR Trend-Breakout** passes `trail_activation_atr` and `trail_offset_atr` to `run_backtest()` for trailing stop support. Other strategies leave them at 0 (disabled).
- **Max 1 open trade at a time** — no pyramiding, no concurrent positions.
- **Slippage is always 0.0** — no UI slider exists.
- **NY range strategies** use `America/New_York` timezone via `pytz`. Daily range = midnight–4am NY time.
- **Fee input stores as %** in widget, converts to decimal in two places: in `settings_panel.py` for `state.fee_rate`, and in `backtest_panel.py:_on_run()` for strategy params (`params["fee_rate"] /= 100`).
- **4H NY Range SL logic**: two-step swing filter: (1) find nearest swing, (2) if swing is beyond range midpoint (>50% from the lower boundary for shorts, <50% for longs), skip it and find the swing closest to the breakout boundary (`range_high` for shorts, `range_low` for longs). Uses `_find_swing_high_closest_to` / `_find_swing_low_closest_to`.
- **Position sizing guard**: `run_backtest` checks `equity > 0` before computing quantity; if equity is wiped, `quantity=0`.
- **CCXT exchanges** are accessed via `getattr(ccxt, exchange_id)` — any CCXT-supported ID works.
- **Charts panel** has 3 tabs (Equity & Drawdown, Monthly Returns, Trade Analysis). Price + Signals tab was removed.
- **PyQtGraph symbols**: use `"t"` for triangle-up, `"t1"` for triangle-down, `"x"` for cross.
- **Crosshair** connects deferred via QTimer; scene must be available for `sigMouseMoved`.
- **`.gitignore`**: protects `config.json`, `.env`, `__pycache__/`, `cache/`, `live/logs/` from accidental git commits.

## Live bot (ATR Trend-Breakout on Bybit perp)

```
backtest_cli.py            CLI backtest runner (Termux-friendly, all 5 strategies)
live/
├── config.py              JSON load/save (symbols, params, API keys via .env, positions)
├── position_manager.py    SL/TP/trail math (mirrors backtest_engine.py logic)
├── executor.py            PaperExecutor (simulated fills) + LiveExecutor (CCXT Bybit orders)
├── engine.py              Main loop — poll 4H OHLCV every 60s, process all symbols, manage positions
└── run.py                 CLI entry point
config.json                Saved settings (gitignored — never commit API keys)
.env                       API keys only (gitignored — optional, overrides config.json)
.env.example               API key template (safe to commit)
requirements.txt           pip dependencies for Termux/pip users
SETUP_TERMUX.md            Full Android setup guide
```

### Run (paper mode — default)

```powershell
cd trading_bot
pipenv run python -m live.run
```

Use `-m live.run` (not `python live/run.py`) to keep the package import path correct.

First run auto-creates `config.json` with **20 popular symbols**, equal capital allocation.
Logs go to `live/logs/bot.log`.

### Switching to live

Two ways to provide API keys (pick one):

**Option A — `.env` file (recommended):**
Create `trading_bot/.env`:
```
BYBIT_API_KEY=your_key_here
BYBIT_API_SECRET=your_secret_here
```

**Option B — `config.json`:**
Set `api_key` and `api_secret` directly (never commit to git).

Then:
1. Change `"mode": "paper"` → `"mode": "live"` in `config.json`
2. Set `"capital": 100` (or your deposit amount)
3. Verify: `pipenv run python -c "from exchange.connector import build_exchange; ex = build_exchange('bybit', 'KEY', 'SECRET'); print(ex.fetch_balance()['USDT']['total'])"`

### Multi-symbol behavior

- **20 symbols** by default (BTC, ETH, SOL, ADA, etc. — all Bybit USDT perps)
- **Equal capital split**: $100 capital = $5 per symbol
- **Min-order filter**: symbols where computed quantity is below the exchange minimum order size are silently skipped
- **Independent tracking**: each symbol has its own position, SL/TP, candle tracking, and strategy execution
- **Simultaneous entries**: if multiple symbols trigger in the same 4H candle, all enter at once

### Safety

- Default mode is `"paper"` — no real orders
- **Server-side SL/TP** — in live mode, stop-loss and take-profit are conditional orders on Bybit. SL/TP execute even if the bot goes offline.
- Position reconciliation — every tick the bot checks the exchange's actual positions; if closed by SL/TP, engine state updates
- Max daily loss guard (`max_daily_loss_pct: 10.0`) — logs warning when hit
- Max drawdown guard (`max_drawdown_pct: 20.0`) — logs warning when hit
- Position persisted in `config.json` — bot survives restart
- On first run, the bot skips the first candle for each symbol (only trades new 4H candles after startup)
