# Session Summary — June 6, 2026 (Full Session)

---

## What Was Built/Changed

### Live Trading Bot — Complete Module

The major deliverable this session is a fully functional live trading bot for Bybit USDT perpetuals running the ATR Trend-Breakout strategy. It supports multi-symbol, server-side SL/TP, paper mode for testing, `.env`-based API key management, 2-minute heartbeat logging, and on-chain balance display.

#### Files Created

| File | Lines | Purpose |
|---|---|---|
| `live/__init__.py` | 0 | Package marker |
| `live/config.py` | 130 | JSON config load/save, `.env` API key loading, multi-symbol schema, old-to-new config migration, `allocate_capital()` helper |
| `live/position_manager.py` | 91 | `Position` dataclass with `to_dict()`/`from_dict()`, `check_exit()`, `update_trail()` — mirrors `backtest_engine.py` logic exactly |
| `live/executor.py` | 116 | `PaperExecutor` (simulated fills, equity tracking) + `LiveExecutor` (CCXT Bybit market orders with server-side SL/TP via conditional orders), factory function `build_executor()` |
| `live/engine.py` | 302 | `LiveEngine` class — 60s polling loop, per-symbol 4H OHLCV fetch, candle detection, SL/TP/trail, ATR strategy execution, min-order filter for live mode, position reconciliation with exchange, safety checks (daily loss + drawdown), 2-minute heartbeat logging, state persistence |
| `live/run.py` | 90 | CLI entry point — startup banner (exchange, mode, keys source, on-chain balance, symbol list, per-symbol allocation), Ctrl+C handler, file + console logging |
| `.env` | 2 | Template for API keys (`BYBIT_API_KEY`, `BYBIT_API_SECRET`) — gitignored |
| `.gitignore` | 6 | Ignores `config.json`, `__pycache__/`, `cache/`, `live/logs/`, `.streamlit/secrets.toml`, `.env` |

#### Key Capabilities

- **20 symbols** by default (BTC, ETH, SOL, ADA, etc. — all in `SYMBOL/USDT:USDT` perp format)
- **Equal capital allocation** across all symbols (e.g., $74.53 ÷ 18 = $4.14 each)
- **Min-order filter** — skips symbols where computed quantity is below Bybit's minimum contract size (checked via `exchange.market()` limits)
- **Server-side SL/TP** — stop-loss and take-profit placed as Bybit v5 conditional orders via `create_order()` params (`stopLoss`/`takeProfit`). Exchange handles execution even if bot crashes
- **Position reconciliation** — every tick checks exchange's actual position via `fetch_positions()`; if closed by SL/TP server-side, engine state updates automatically
- **Leverage + margin setup** — auto-calls `set_leverage()` and `set_margin_mode("cross")` for all symbols on startup
- **Order cancellation on close** — calls `cancel_all_orders()` before placing close market order to prevent stale SL/TP orders
- **On-chain balance display** — startup banner fetches real Bybit USDT wallet balance when API keys are set
- **2-minute heartbeat** — logs `Heartbeat — N symbols, M open, equity=$X.XX` every 2 ticks
- **First-candle skip** — on startup, each symbol records its latest candle without trading it, preventing stale historical signals
- **Persistence** — all positions and candle timestamps saved to `config.json` every tick, restored on restart
- **Old config auto-migration** — single-symbol `config.json` from prior sessions auto-upgrades to new multi-symbol format
- **`.env` API key management** — keys read from `.env` file at runtime, override `config.json` values, never committed to git

---

### Bug Fixes

#### 1. `RuntimeError: wrapped C/C++ object of type QThread has been deleted` (`widgets/backtest_panel.py:350`)

- **Root cause**: On second "Run Backtest" click, `self._thread` held a Python reference to a `QThread` whose C++ object had been deleted by `deleteLater()` (scheduled via signal on the previous run). Calling `.isRunning()` on the deleted object crashed.
- **Fix (3 parts)**:
  - `_on_run` (line 349-355): Wrapped `isRunning()` guard in `try/except RuntimeError` — catches stale C++ objects and nulls references
  - Added `_on_thread_finished()` connected to `self._thread.finished` — nulls `self._thread` and `self._worker` only *after* thread event loop has actually exited
  - `_on_error`: Added proper thread cleanup (`quit()`, `deleteLater()`, null references)

#### 2. `QThread: Destroyed while thread is still running`

- **Root cause**: `_on_finished` set `self._thread = None` while `_thread.quit()` had only been *posted* — thread event loop still running. Dropping the Python reference caused Qt to destroy the C++ QThread mid-flight.
- **Fix**: Moved null-out to `_on_thread_finished()` (connected to `QThread.finished`) which fires only after thread event loop fully exits.

#### 3. `QWidget::setLayout: Attempting to set QLayout on QWidget which already has a layout` (`widgets/charts_panel.py`)

- **Root cause**: `charts_panel.py:refresh()` called `setLayout(QHBoxLayout())` on every backtest completion. Second call failed because `_clear_layout()` detached old layout via `old.setParent(None)` but widget still considered itself as having one.
- **Fix**: Guarded `setLayout` with `if container.layout() is None`. Removed `old.setParent(None)` from `_clear_layout()`.

#### 4. `AttributeError: 'LiveExecutor' object has no attribute 'equity'`

- **Root cause**: `_check_safety()` and `_process_symbol()` both reference `self.executor.equity`, but `LiveExecutor.__init__()` didn't initialize it — only `PaperExecutor` had it.
- **Fix**: Added `self.equity = config.get("capital", 100.0)` to `LiveExecutor.__init__()`.

#### 5. Old config migration bug

- **Root cause**: `_migrate_config()` checked `if "position" in data and "positions" not in data`, but `DEFAULT_CONFIG` already had `"positions"` from the merge, so the condition was always False for old configs.
- **Fix**: Changed migration to detect old format by `"symbol" in data or "position" in data`, then do a full replacement of symbols/positions from the old single-symbol setup.

#### 6. Allocation display mismatch

- **Root cause**: Banner top line used `display_capital` (real balance) for "per symbol" calculation, but per-symbol breakdown used `allocations` computed from `config["capital"]` ($100). Values didn't match.
- **Fix**: Moved `allocations = allocate_capital(...)` after balance fetch, computing from `display_capital`.

#### 7. Safety warnings on first run with no trades

- **Root cause**: `peak_equity` and `daily_start_equity` initialized from `config["capital"]` ($100), but `executor.equity` was the real balance ($74.53). Every tick computed 25.5% "loss" on a phantom $100 baseline.
- **Fix**: After setting `executor.equity` from real balance, also sync `engine.peak_equity` and `engine.daily_start_equity`.

---

### Strategy Changes

#### 8. ATR TP changed from ATR-multiple to Risk:Reward

- **Files**: `core/strategy_atr_breakout.py:28,90,96` + `widgets/backtest_panel.py:123,316`
- **Before**: `tp = entry ± ATR × atr_target_mult` (TP distance independent of SL distance)
- **After**: `tp = entry ± ATR × atr_sl_mult × rr` (TP = SL distance × RR ratio)
- Parameter replaced: `atr_target_mult` → `rr`
- UI label changed from "Target (ATR)" to "Risk:Reward"
- Defaults updated: `rr=5.0`, `risk_percent=3.0`

---

## Files Modified

| File | Change |
|---|---|
| `widgets/backtest_panel.py` | QThread crash fix (try/except guard, `_on_thread_finished`, error cleanup), ATR defaults update (rr=5.0, risk=3.0%), ATR param `atr_target_mult` → `rr` |
| `widgets/charts_panel.py` | Layout warning fix (guarded `setLayout`, removed `old.setParent(None)`) |
| `core/strategy_atr_breakout.py` | Replaced `atr_target_mult` with `rr`, TP now = `SL_distance × rr` |
| `AGENTS.md` | Added live bot architecture, run commands, .env setup, multi-symbol docs, safety section |

## Files Created

| File | Lines |
|---|---|
| `live/__init__.py` | 0 |
| `live/config.py` | 130 |
| `live/position_manager.py` | 91 |
| `live/executor.py` | 116 |
| `live/engine.py` | 302 |
| `live/run.py` | 90 |
| `.env` | 2 |
| `.gitignore` | 6 |

---

## Key Decisions

1. **Server-side SL/TP via Bybit conditional orders** — instead of polling-based SL/TP (which dies if the bot crashes), the live executor passes `stopLoss`/`takeProfit` params in CCXT's `create_order()`. Exchange handles execution even if bot is offline.

2. **`.env` for API keys** — keys read from `.env` file at runtime via `_load_env_overrides()`, overriding `config.json` values. Keeps credentials out of config and prevents accidental git commits.

3. **Min-order filter over capital redistribution** — when a symbol's computed quantity is below Bybit's minimum, the bot skips it rather than redistributing capital. Keeps allocation model simple and predictable.

4. **Equal allocation by default** — capital split evenly across all symbols. No weighting, no per-symbol config required.

5. **Old config auto-migration** — if `config.json` has `symbol` or `position` (old single-symbol format), `_migrate_config()` converts it to the new multi-symbol format on load.

6. **`build_executor()` factory** — `PaperExecutor` and `LiveExecutor` share `place_market_entry()`/`place_market_close()` interface. Engine is agnostic to paper vs. live mode.

7. **2-minute heartbeat** — confirms the loop is alive, shows open position count and equity. Prevents ambiguity during long periods without signals.

8. **On-chain balance in banner** — shows real Bybit USDT wallet balance at startup when keys are set, rather than the static `config.json` capital value. Updated via `display_capital` variable.

9. **`_process_symbol()` extraction** — multi-symbol engine extracts per-symbol logic into a separate method, keeping `_tick()` as a clean loop over symbols with heartbeat and safety checks.

10. **`_on_thread_finished` over `_on_finished` for null-out** — the `QThread.finished` signal fires only after the thread event loop has fully exited, safe for dropping Python references.

---

## Errors Encountered

1. **`RuntimeError: wrapped C/C++ object of type QThread has been deleted`** — on second GUI backtest run. Fixed with try/except + `_on_thread_finished`.
2. **`QThread: Destroyed while thread is still running`** — nulled references too early in `_on_finished`. Fixed by moving null-out to `_on_thread_finished`.
3. **`QWidget::setLayout` warning** — on second backtest run in GUI. Fixed with guarded `setLayout` + removed `old.setParent(None)`.
4. **`AttributeError: 'LiveExecutor' object has no attribute 'equity'`** — `LiveExecutor` missing `self.equity`. Fixed by adding initialization.
5. **Old config migration not triggering** — `DEFAULT_CONFIG` had `positions` key which blocked migration check. Fixed with old-format detection via `"symbol" in data or "position" in data`.
6. **Allocation mismatch in banner** — per-symbol used config capital, summary used real balance. Fixed by recomputing `allocations` from `display_capital`.
7. **False safety warnings on first run** — `peak_equity` vs `executor.equity` mismatch (config $100 vs real $74.53). Fixed by syncing all three values.
8. **PowerShell escaping** with f-strings containing brackets and special characters — worked around by using simpler syntax or writing temp `.py` test files.

---

## Known Issues

1. **Paper mode SL/TP uses 4H bar range only** — SL/TP checks against the 4H candle's high/low. Intra-candle wicks that hit SL/TP and retrace within the same candle are missed. Could be improved with 1-minute data or ticker stream.
2. **Safety guards are log-only** — `_check_safety()` logs warnings when max daily loss or drawdown is hit but does not stop the bot. Auto-shutdown not implemented.
3. **LiveExecutor SL/TP untested on testnet** — server-side conditional order placement via CCXT Bybit v5 params hasn't been verified against live or testnet exchange.
4. **`resample_to_4h()` in `data/ohlcv.py:103`** is dead code — defined but never called.
5. **Sharpe/Sortino `n_per_year` in `core/metrics.py`** hardcoded to 5M bars (105,120 bars/year) — wrong for ATR strategy (4H data).
6. **No tests/CI** — no test framework, lint, or typecheck.

---

## What to Continue With Next

1. **Test live bot on Bybit testnet** — run `python -m live.run` in paper mode first, then switch to live mode with testnet keys. Verify OHLCV fetching, candle detection, signal generation, entry/exit logging, and heartbeat.
2. **Test server-side SL/TP on testnet** — after a paper-mode test cycle, verify that Bybit conditional orders (`stopLoss`, `takeProfit`) are placed correctly and trigger when price hits SL/TP.
3. **Add auto-shutdown to safety guards** — kill the bot when max daily loss or max drawdown is breached.
4. **Add consecutive error guard** — if API calls fail N times in a row, shut down to prevent runaway behavior on stale data.
5. **Improve paper mode SL/TP resolution** — use 1-minute OHLCV or exchange ticker for more accurate stop/target hits.
6. **Parameterize `n_per_year` in `core/metrics.py`** by bar frequency instead of hardcoding 5M.
7. **Clean up dead code** — remove `resample_to_4h()` in `ohlcv.py`.
