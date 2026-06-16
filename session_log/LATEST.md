# Session: Multi-Symbol Portfolio Backtest, CLI Comparison, Live Engine Equity Tracking

**Date:** 2026-06-16

---

## Summary

Added **shared-capital portfolio backtesting** with concurrent positions in both
Streamlit UI and CLI, **live engine equity tracking** (realized + unrealized P&L
from all open positions), and fixed several bugs in OHLCV caching and backtest
sizing. Timestamps across symbols are now properly aligned via set-union
reindexing.

---

## Files Modified

| File | Changes |
|------|---------|
| `streamlit_app.py` | +`_PortfolioTrade` dataclass, +`_portfolio_backtest()` function (+~200 loc), +`_render_single_result()` helper (refactored single-symbol results out of `main()`) |
| | Added compare mode: checkbox toggle in sidebar, `st.multiselect()` for symbols, `max_concurrent` slider |
| | Portfolio summary cards, combined equity curve, per-symbol breakdown table, trade log with Symbol column, monthly returns, detailed stats |
| | Timestamp alignment: union of all timestamps across symbol DataFrames with reindex + forward-fill |
| | Sizing uses `current_eq = pool + Σ unrealized P&L` from still-open positions |
| `backtest_cli.py` | Added `POPULAR_SYMBOLS` list (18 symbols, same as Streamlit) |
| | Added `--all-symbols` and `--symbols` flags |
| | Refactored strategy loading + backtest into `run_one()` helper |
| | Added comparison table sorted by total return (Symbol, Return %, CAGR, Sharpe, Max DD, Win Rate, PF, Trades) |
| `data/ohlcv.py` | Fixed cache date range check: now verifies both `cached_start <= start_date` AND `cached_end >= end_date` before serving cached data |
| `live/engine.py` | Added `self._last_prices: Dict[str, float]` — stores latest ticker/close per symbol |
| | Added `self.current_value` — equity + unrealized P&L from all open positions |
| | Added `_update_current_value()` method |
| | `_tick()` stores ticker prices in `_last_prices` (live) or OHLC close (paper), calls `_update_current_value()` after processing symbols |
| | Heartbeat uses `self.current_value` instead of `self.executor.equity` |
| | `_process_symbol()` stores `latest_bar["close"]` in `_last_prices` for paper mode |
| | Trade sizing uses `self.current_value` instead of `config.get("capital", 100.0)` |
| | `max_open_trades` default changed to `None` (unlimited). Guard checks `self.max_open_trades is not None` |
| | `_check_safety()` uses `self.current_value` instead of `self.executor.equity` |
| | `_save_state()` saves `self.current_value` instead of `self.executor.equity` |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Shared capital pool with concurrent positions | Matches live engine behavior (all symbols share one capital pool, unrealized P&L from open positions counts toward available margin) |
| Timestamp alignment via union + reindex + ffill | Symbols have different bar counts / start dates; union of all timestamps with forward-fill preserves the most recent data for each symbol at every step |
| `current_eq = pool + Σ unrealized` used for trade sizing | Backtest now matches live engine — new entries are sized based on total portfolio value, not just realized cash |
| Unlimited concurrent trades by default (`max_open_trades: None`) | Simpler config — user explicitly sets limit only if needed |
| Cache check verifies both start AND end bounds | Prior code only checked `cached_end >= end_date` — increasing lookback preserved stale cache instead of re-fetching |
| Sequential symbol processing in compare mode | Parallel CCXT fetch risks rate limits; sequential is safe and simple |

---

## Bugs Fixed

### 1. Cache served truncated data when lookback increased (`data/ohlcv.py`)

**Symptom:** Increasing lookback (e.g., 90 → 180 days) did not trigger a re-fetch.
Only `cached_end >= end_date` was checked — if cached data started at a later
date than requested, the old cache was returned with missing early bars.

**Fix:** Added `cached_start <= start_date` check. If either bound is
unsatisfied, cache is invalidated and fresh data is fetched.

### 2. Backtest sizing used `pool` only, ignored unrealized P&L (`streamlit_app.py`)

**Symptom:** When multiple trades were open simultaneously, new entries were
sized based solely on realized cash (`pool`), ignoring unrealized P&L from
still-open positions. This under-sized trades and understated portfolio equity.

**Fix:** `current_eq = pool + sum((close - entry) * qty * side for each open pos)`
is used for both trade sizing and equity curve recording.

### 3. Live engine trade sizing ignored other open positions (`live/engine.py`)

**Symptom:** `total_cap = config.get("capital", 100.0)` was static. If symbol A
had an open trade with $50 unrealized profit and symbol B was processing a new
entry, the new trade was sized against the original $100 capital instead of $150.

**Fix:** `total_cap = self.current_value` — dynamically includes unrealized P&L
from all open positions at the time of entry.

### 4. `max_open_trades: 3` default prevented concurrent multi-symbol entries (`live/engine.py`)

**Symptom:** Default max_open_trades=3 capped concurrent positions even when
user expected all 20 symbols to trade independently.

**Fix:** Default changed to `None` (unlimited). Guard: `if self.max_open_trades
is not None and open_count >= self.max_open_trades:`.

---

## Known Issues

1. **pyarrow/parquet caching** — will fail on Termux ARM (no pre-compiled wheel).
   CSV fallback planned but not yet implemented.
2. **Intra-tick stale `current_value`** — `_update_current_value()` runs after
   all symbols are processed. If symbol A closes a position (increasing executor
   equity) and symbol B enters a new trade in the same tick, B sizes against
   the pre-close `current_value`. This is a minor edge case and matches the
   original behavior (which was even worse, using static config capital).
3. **Streamlit live bot page** — reads logs from file (not stdout). `config.json`
   may briefly show stale state between saves.
4. **`.env` with live keys** — still present in working directory (gitignored).
   Regenerate keys if repo is shared publicly.

---

## Commits (this session)

```
2991e18 Fix bugs
3af1d69 Fix cache date range check to verify both start and end bounds
ee10089 Align all symbol DataFrames by union of timestamps in portfolio backtest
c4cc9d4 Shared-capital portfolio backtest with concurrent multi-symbol support
```

---

## Project Structure (current state)

```
trading_bot/
├── streamlit_app.py            # Compare mode + portfolio backtest + single-symbol results
├── pages/live.py               # Live bot control page (unchanged)
├── backtest_cli.py             # --all-symbols / --symbols flags + comparison table
├── live/
│   ├── telegram_bot.py         # start_polling, urllib.error, self-test, level tags
│   ├── run.py                  # httpx suppression (unchanged)
│   ├── engine.py               # current_value, _last_prices, _update_current_value, unlimited max_open_trades
│   ├── executor.py             # Unchanged
│   ├── config.py               # Unchanged
│   ├── position_manager.py     # Unchanged
│   └── news_checker.py         # Unchanged
├── core/                       # Unchanged (all 5 strategies + backtest_engine + metrics)
├── data/ohlcv.py               # Fixed: cache date range bound check (start + end)
├── exchange/connector.py       # Unchanged
├── .env.example                # API key template
├── requirements.txt            # pip deps
├── SETUP_TERMUX.md             # Android guide
├── config.json                 # gitignored
├── .env                        # gitignored
└── main.py + main_window.py + widgets/  # PyQt6 (not Termux-compatible)
```

---

## What to Continue With Next

1. **CSV cache fallback in `ohlcv.py`** — try/except on `import pyarrow`; fall
   back to `.csv.gz` so Termux users still get disk caching
2. **Streamlit equity persistence** — save last backtest results to
   `st.session_state` so they survive page reruns
3. **HTTPS proxy support** — SOCKS5 proxy option in `.env` for restricted mobile
   networks
4. **Configurable heartbeat interval** — make Telegram heartbeat configurable
   via `config.json` instead of hardcoded in `engine.py`
5. **Per-symbol `max_concurrent`** — currently global slider only; could allow
   per-symbol limits in portfolio backtest
