# Session: Termux Android Support, Streamlit Web UI, Telegram Fixes

**Date:** 2026-06-11

---

## Summary

This session retrofitted the Crypto Trading Bot for Android via Termux, replacing
the PyQt6 desktop-only GUI with a Streamlit web UI (works in phone browser),
added a CLI backtest runner, and fixed the Telegram bot crash on subprocess
launch. Also created a full setup guide and dependency management for Termux ARM.

---

## Files Created

| File | Purpose |
|------|---------|
| trading_bot/requirements.txt | pip dependency list |
| trading_bot/.env.example | API key template (safe to commit) |
| trading_bot/SETUP_TERMUX.md | 250-line Android setup guide |
| trading_bot/backtest_cli.py | CLI backtest runner (all 5 strategies) |
| trading_bot/streamlit_app.py | Streamlit web UI for backtesting |
| trading_bot/pages/live.py | Streamlit live bot control page |

---

## Files Modified

| File | Change |
|------|--------|
| Pipfile | Added all 9 dependency packages (was empty) |
| trading_bot/AGENTS.md | Added Termux section, updated deps, added backtest CLI |
| trading_bot/SETUP_TERMUX.md | 3 run options, backtest examples, pip fixes |
| trading_bot/requirements.txt | Added streamlit, plotly |
| trading_bot/live/telegram_bot.py | Full rewrite of polling logic |
| trading_bot/streamlit_app.py | Fixed KeyError on float params |

---

## Key Decisions

- pip + requirements.txt over pipenv for Termux (simpler, no virtualenv issues)
- Streamlit over PyQt6 for mobile (browser-based, Plotly charts)
- Subprocess.Popen for live bot from Streamlit (keeps UI responsive)
- Message queue for Telegram (prevents lost messages at startup)
- CSV fallback planned for when pyarrow not available on ARM
- Replaced run_polling() with start_polling() to avoid set_wakeup_fd crash

---

## Bugs Fixed

1. KeyError in streamlit_app.py:76 -- changed cfg["int"] to cfg.get("int", False)
2. Telegram set_wakeup_fd crash in subprocess -- replaced run_polling() with manual poll
3. Telegram messages silently dropped -- added ready flag + send queue

---

## Errors Encountered (Termux Android)

- pip install --upgrade pip forbidden -- Termux manages pip via python-pip package
- pip install pandas fails on ARM -- use pkg install python-pandas python-numpy instead
- pip install pyarrow fails on ARM -- no pre-compiled wheel; CSV fallback planned
- Mixed tabs/spaces IndentationError -- fixed nano with -ET4 flag

---

## Known Issues

1. PyQt6 GUI will not work on Termux -- use Streamlit instead
2. pyarrow/parquet caching fails on ARM -- CSV fallback planned
3. Telegram startup may have 3-8s delay while event loop initializes
4. Bot pauses when screen off without termux-wake-lock
5. Streamlit live bot page reads logs from file (not stdout)

---

## What to Continue With Next

1. CSV cache fallback in ohlcv.py for Termux users
2. Streamlit equity persistence across page reruns
3. Multi-symbol backtest in CLI
4. HTTPS proxy option in .env for restricted mobile networks
5. Configurable Telegram heartbeat interval in config.json
