# Session: Telegram Robustness, Heartbeat Cadence, Level Tags, Symbol Dropdown

**Date:** 2026-06-11

---

## Summary

This session focused on fixing **Telegram notification reliability** (messages were
not arriving at all or were silently dropped), adding **log level tags** (`[INFO]`,
`[WARN]`, `[ERROR]`) to every Telegram message, adjusting **heartbeat cadences**
(file log → 5 min, Telegram → 20 min), silencing noisy HTTP polling logs, and
adding a **symbol dropdown** to the Streamlit backtest UI.

---

## Files Modified

| File | Changes |
|------|---------|
| `live/telegram_bot.py` | Added `import urllib.error` (was missing — caused `NameError` crash in `_send_http_direct()`) |
| | Added `from datetime import datetime` |
| | Added token length guard (`self.token[-6:]` crash for short tokens) |
| | Added placeholder token warning (detects `your_` or unedited template values) |
| | Added startup self-test via `_send_http_direct()` — logs PASSED or FAILED instantly with HTTP error code |
| | Modified `send()` to accept `level` param (`INFO`/`WARN`/`ERROR`) — auto-prefixes every message with `ℹ️ [INFO] 2026-06-11 14:30` |
| | Increased direct HTTP fallback threshold (queue >= 3 triggers direct send) |
| `live/engine.py` | File log heartbeat: every **2 min → 5 min** (`_tick_count % 2` → `% 5`) |
| | Telegram heartbeat: every **30 min → 20 min** (`>= 15` → `>= 4` × 5 min ticks) |
| | Simplified heartbeat format: removed DD/Daily, added "ATR Bot" identity |
| | Added `level` parameter to all `send()` calls — INFO for normal, WARN for losses/safety, ERROR for exceptions |
| `live/run.py` | Added `logging.getLogger("httpx").setLevel(logging.WARNING)` — silences the `POST 200` Telegram poll lines |
| | Removed duplicate test ping (now handled by `telegram_bot.start()` self-test) |
| `streamlit_app.py` | Fixed `KeyError: 'int'` on float params (`cfg["int"]` → `cfg.get("int", False)`) |
| | Added `POPULAR_SYMBOLS` list (18 symbols, excluding MATIC and PEPE) |
| | Replaced symbol text input with `st.selectbox()` dropdown + "Custom..." option |
| | Changed default R:R from 2.0 to 5.0 (matches ATR Trend-Breakout desktop UI default) |

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `start_polling()` over `run_polling()` | `run_polling()` calls `signal.set_wakeup_fd()` which crashes outside main thread; `start_polling()` avoids this entirely |
| Direct HTTP fallback via `urllib` | Stdlib only — no extra dependency needed. Fires when queue reaches 3+ messages or polling fails |
| Level tags in message body (not metadata) | `[INFO]` / `[WARN]` / `[ERROR]` visible in Telegram notification preview at a glance |
| 5 min file heartbeat / 20 min Telegram | 5 min matches common trading bot standards; 20 min is frequent enough to know bot is alive without being noisy |
| Removed DD/Daily from heartbeat | User requested "details, date, where it came from" only — performance metrics available via `/status` command |
| Removed MATIC and PEPE from symbol list | User reported CCXT cannot fetch data for these pairs |

---

## Bugs Fixed

### 1. `NameError: name 'urllib' is not defined` in `_send_http_direct()` (`telegram_bot.py:61`)

**Symptom:** When direct HTTP fallback triggered (queue >= 3), `except urllib.error.HTTPError` threw `NameError` because `urllib.error` was never imported. Error was silently caught by the generic `except Exception` and logged as a non-specific warning. All queued messages lost forever.

**Fix:** Added `import urllib.error` at top of file.

### 2. `self.token[-6:]` crash for short tokens (`telegram_bot.py:73`)

**Symptom:** If token was empty or shorter than 6 characters, negative slice crashed.

**Fix:** Added length guard: `self.token[-6:] if len(self.token) >= 6 else "(too short)"`.

### 3. No notification on startup failure (`telegram_bot.py`)

**Symptom:** If polling failed at startup (wrong token, network down), no error was surfaced. User had to wait 30+ minutes to notice no heartbeat arrived.

**Fix:** Added immediate self-test via `_send_http_direct("🔌 Telegram self-test...")` in `start()` — logs `PASSED` or `FAILED` within 2 seconds of launching.

### 4. Placeholder token not detected

**Symptom:** If user copied `.env.example` to `.env` without editing values, token was `your_telegram_bot_token_here` — polling fails silently.

**Fix:** Added check in `start()` — if token starts with `your_` or equals the example placeholder, logs a clear `WARNING` telling user to edit `.env`.

### 5. `KeyError: 'int'` in `streamlit_app.py:76`

**Symptom:** Selecting ATR Trend-Breakout or any strategy with float-only params crashed with `KeyError: 'int'`.

**Fix:** Changed `if cfg["int"]:` → `if cfg.get("int", False):`. Float param dicts lack the `"int"` key.

---

## Known Issues

1. **pyarrow/parquet caching** — will fail on Termux ARM (no pre-compiled wheel). CSV fallback planned but not yet implemented.
2. **Telegram startup delay** — self-test logs result immediately, but `start_polling()` may take 3-8 seconds before first heartbeat notification is sent.
3. **Bot pauses when screen off without `termux-wake-lock`** — Android suspends CPU. Must use wake-lock for 24/7 operation.
4. **Streamlit live bot page** — reads logs from file (not stdout). `config.json` may briefly show stale state between saves.
5. **`.env` with live keys** — still present in working directory (gitignored). Regenerate keys if repo is shared publicly.

---

## Project Structure (current state)

```
trading_bot/
├── streamlit_app.py            # Backtest UI (symbol dropdown, 5 strategies, Plotly charts)
├── pages/live.py               # Live bot control page
├── backtest_cli.py             # CLI backtest runner
├── live/
│   ├── telegram_bot.py         # Fixed: start_polling, urllib.error, self-test, level tags
│   ├── run.py                  # Added: httpx suppression
│   ├── engine.py               # Updated: 5min/20min cadence, level tags on all sends
│   ├── executor.py             # Unchanged
│   ├── config.py               # Unchanged
│   ├── position_manager.py     # Unchanged
│   └── news_checker.py         # Unchanged
├── core/                       # Unchanged (all 5 strategies)
├── data/ohlcv.py               # Unchanged
├── exchange/connector.py       # Unchanged
├── .env.example                # API key template
├── requirements.txt            # pip deps
├── SETUP_TERMUX.md             # Android guide
├── config.json                 # gitignored
├── .env                        # gitignored
├── main.py                     # PyQt6 (not Termux-compatible)
├── main_window.py              # PyQt6 (not Termux-compatible)
└── widgets/                    # PyQt6 (not Termux-compatible)
```

---

## What to Continue With Next

1. **CSV cache fallback in `ohlcv.py`** — try/except on `import pyarrow`; fall back to `.csv.gz` so Termux users still get disk caching
2. **Streamlit equity persistence** — save last backtest results to `st.session_state` so they survive page reruns
3. **Multi-symbol backtest in CLI** — allow comma-separated symbols or batch mode in `backtest_cli.py`
4. **HTTPS proxy support** — SOCKS5 proxy option in `.env` for restricted mobile networks
5. **Configurable heartbeat interval** — make Telegram heartbeat configurable via `config.json` instead of hardcoded in `engine.py`
