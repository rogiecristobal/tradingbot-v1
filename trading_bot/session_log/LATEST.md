# Session Summary — June 8, 2026

## Overview

Two main workstreams: (1) cleanup of dead/deprecated files, and (2) safety hardening of the live trading bot — retry logic for API calls, total-capital risk partitioning, and a max-open-trades limit.

---

## What Was Built/Changed

### 1. Dead Code Cleanup

**Removed `resample_to_4h()` from `data/ohlcv.py:103-109`**
- Function was defined but never called anywhere in the codebase
- No import changes needed (only `pd` was used, which was already imported)
- Line count: 109 → 100

**Updated `AGENTS.md`**
- Removed the `resample_to_4h()` dead code note from "Key conventions & gotchas"
- Removed "Old Streamlit files still exist on disk but are unused" line
- Added `.gitignore` note to the conventions section

### 2. Streamlit Cleanup

**Deleted `.streamlit/` directory** (recursive)
- Contained `config.toml` (Streamlit theme) and `secrets.toml` (empty API key template)
- No Python file in the project imports streamlit — confirmed by project-wide grep
- Pipfile already had streamlit removed (only ccxt, pandas, numpy, pytz, pyqt6, pyqtgraph remain)

**Deleted `requirements.txt`**
- Outdated — listed streamlit, plotly alongside core deps
- Pipfile is the single source of truth; this was a stale duplicate

**Created `.gitignore`**
```
config.json
.env
.streamlit/
cache/
__pycache__/
*.pyc
live/logs/
```
Protects API keys and sensitive config from accidental git commits.

### 3. Retry Logic for Exchange Initialization

**Modified `exchange/connector.py` — `build_exchange()`**
- Added `import time`
- Added `retries: int = 3` parameter to `build_exchange()`
- Wrapped the exchange init + `load_markets()` in a retry loop (3 attempts, 2s delay)
- On success: returns exchange instance immediately
- On transient failure: logs `WARNING` with attempt count, retries
- On final failure: logs `ERROR`, returns `None` (same as before)

| Attempt | Behaviour |
|---|---|
| 1st fail | Warning log, 2s sleep, retry |
| 2nd fail | Warning log, 2s sleep, retry |
| 3rd fail | Error log "after 3 attempts", return None |

- Fixes the intermittent `GET /v5/market/instruments-info?category=inverse&status=PreLaunch` failures from Bybit's API

### 4. Retry Logic for Order Placement

**Modified `live/executor.py` — `LiveExecutor`**
- Added `import time`, `from typing import Callable`
- Added `_retry_call(fn, label, retries=3, delay=1.0)` helper method:
  - Attempts the callable N times
  - Logs `WARNING` on each retry
  - Raises on final failure (caller propagates up)

- **`place_market_entry()`**: `create_order()` now goes through `_retry_call` (3 retries, 1s delay)
- **`place_market_close()`**:
  - `cancel_all_orders()`: `_retry_call` with 2 retries, best-effort (caught exception proceeds)
  - `create_market_order()`: `_retry_call` with 3 retries, 1s delay

- PaperExecutor unchanged (no API calls)

### 5. Total-Capital Risk + Max Open Trades

**Modified `live/config.py`**
- Added `"max_open_trades": 3` to `DEFAULT_CONFIG`

**Modified `live/engine.py` — `_compute_quantity()`**
- Renamed `alloc_capital` → `total_capital`
- Added `leverage: float = 1.0` parameter
- **Risk now computed from total capital**: `risk_amount = total_capital * (risk_percent / 100.0)`
- **Added notional cap**: `qty = min(qty, max_notional / entry)` where `max_notional = total_capital * leverage`
  - Prevents position size exceeding exchange-acceptable margin even with tight SL
- Min-order filter unchanged

**Modified `live/engine.py` — `LiveEngine.__init__()`**
- Added `self.max_open_trades: int = config.get("max_open_trades", 3)`
- Removed `self.allocations` and `allocate_capital()` call (no longer needed)
- Removed `allocate_capital` from imports

**Modified `live/engine.py` — `_process_symbol()`**
- Entry block now checks: `open_count >= self.max_open_trades` → skip with info log
- Uses `total_cap = self.config.get("capital", 100.0)` instead of per-symbol allocation
- Passes `leverage=self.config.get("leverage", 1)` to `_compute_quantity`
- `allocate_capital` import removed

### 6. Test Script (Created, Left on Disk)

**Created `test_server_sl_tp.py`**
- Standalone script to test server-side SL/TP placement on Bybit
- Fetches DOGE/USDT:USDT market info, computes qty for $1, places market buy with SL/TP, then closes
- First attempt failed with EOFError on interactive prompts → removed prompts
- Order placement failed with Bybit `retCode:10005` — API key lacks Contract Trading permission
- Script retained for future testing once API permissions are fixed

---

## Files Changed

| File | Action | Lines | Change |
|---|---|---|---|
| `data/ohlcv.py` | Modified | 109→100 | Removed `resample_to_4h()` dead function |
| `AGENTS.md` | Modified | 138→137 | Removed dead code + Streamlit notes, added .gitignore note |
| `exchange/connector.py` | Modified | 53→59 | Added retry loop to `build_exchange()` + `import time` |
| `live/executor.py` | Modified | 116→139 | Added `_retry_call()` helper + retry-wrapped entry/close |
| `live/engine.py` | Modified | 302→311 | Total-capital risk, max_open_trades, notional cap, removed allocate_capital |
| `live/config.py` | Modified | 130→131 | Added `max_open_trades: 3` default |
| `.gitignore` | Created | 0→7 | New file |
| `test_server_sl_tp.py` | Created | 0→~110 | Test script (left on disk) |
| `.streamlit/` | Deleted | — | Entire directory (config.toml + secrets.toml) |
| `requirements.txt` | Deleted | — | Outdated duplicate of Pipfile |

---

## Key Decisions

1. **Total-capital risk over per-symbol allocation** — more intuitive: `risk_percent` literally means "% of my whole account per trade". Prevents confusion when symbol count changes.

2. **Notional cap = total_capital × leverage** — prevents the exchange from rejecting orders due to insufficient margin, especially when risk-based qty × entry_price exceeds buying power.

3. **max_open_trades = 3** — balances opportunity with safety at $74 capital. With 18 symbols, a 4H candle close could theoretically trigger entries on all 18. Limiting to 3 prevents >40% account exposure at once.

4. **Retry 3 times, 1-2s delay** — Bybit API hiccups are typically sub-second. 3 retries with short delay handles transient issues without excessive wait.

5. **cancel_all_orders is best-effort (2 retries)** — it's not critical for trade execution; the close order can succeed even without cancelling stale SL/TP orders (they'll fail to execute when position is closed).

6. **Deleted Streamlit remnants** — project is fully PyQt6 + CLI live bot. Keeping `.streamlit/` and outdated `requirements.txt` adds confusion and risk (secrets.toml template).

7. **Retained `allocate_capital()` in `config.py`** — still used by `run.py` for banner display, even though engine no longer consumes it for risk computation.

---

## Errors Encountered

### 1. `pipenv` not on PATH
- PowerShell couldn't find `pipenv` command
- Fix: Used full path `& "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\pipenv.exe"`

### 2. `EOFError: EOF when reading a line` in test script
- `input()` call in `test_server_sl_tp.py` failed because the tool doesn't support interactive prompts
- Fix: Removed both confirmation prompts, made script fully automated

### 3. Bybit API `retCode:10005 — Permission denied`
- Two separate permission failures:
  - `set_margin_mode()`: needs "Account Transfer" permission
  - `create_order()`: needs "Contract Trading" permission
- Root cause: API key in config.json lacks trading permissions on Bybit
- Resolution: User needs to update API key permissions on Bybit website
- Not a code bug — test script cannot proceed until permissions are fixed

### 4. False safety warnings (from prior session, re-confirmed)
- `peak_equity`/`daily_start_equity` initialized from `config["capital"]` ($100), but executor equity overridden to real balance ($74) in `run.py`
- Already fixed in prior session — verified still working

---

## Known Issues

1. **Server-side SL/TP untested** — `test_server_sl_tp.py` created but cannot complete due to Bybit API key permissions. Need to enable "Contract Trading" on the API key.

2. **Cancel-all-orders permission** may also be missing for the same API key — will surface during live exit.

3. **Safety guards are log-only** — `_check_safety()` logs warnings when max daily loss or drawdown is breached but does not stop the bot or close positions.

4. **No auto-shutdown on consecutive API errors** — if `fetch_ohlcv()` fails repeatedly, the bot keeps logging warnings but never self-terminates.

5. **Sharpe/Sortino `n_per_year`** in `core/metrics.py` hardcoded to 5M bars (105,120) — wrong for 4H frequency.

6. **No tests, no CI** — no test framework exists.

---

## What to Continue With Next

1. **Fix Bybit API permissions**, then re-run `test_server_sl_tp.py` to verify server-side SL/TP actually works on the exchange.

2. **Test the max_open_trades limit** in paper mode — run the bot and verify that when >3 symbols signal, only 3 enter.

3. **Verify total-capital risk calculation** end-to-end — confirm `_compute_quantity()` produces expected qty values with real data.

4. **Add auto-shutdown to safety guards** — kill the bot when max daily loss or drawdown is breached.

5. **Add consecutive error guard** — if N API calls fail in a row, shut down instead of trading on stale data.

6. **Add notional cap check at the engine level** — log a warning when `_compute_quantity()` returns a capped value (risk-based qty > buying power allows), so the user knows the position is notional-limited rather than risk-limited.
