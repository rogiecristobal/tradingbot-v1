# Session Summary — 2026-06-08

## What was built

Two major feature sets were implemented in this session:

### 1. Five New Backtest Strategies (`core/`)

Created 5 new strategy files following the existing architecture (accepts 5M OHLCV DataFrame, returns DataFrame with `signal`/`entry_price`/`sl_price`/`tp_price` columns):

| File | Strategy | Key Logic |
|------|----------|-----------|
| `core/strategy_ema_pullback.py` | EMA 20/50 Pullback Scalping | EMA20 > EMA50 trend filter, pullback to EMA20, bullish/bearish candle close. SL mode param: `swing` (nearest swing low/high) or `atr` (ATR × multiplier). TP: 1:2 RR. |
| `core/strategy_vwap_rejection.py` | VWAP Rejection Scalping | VWAP resets daily at 00:00 UTC. Rejection candle: price touches VWAP, closes in trend direction. SL: 0.1% below/above candle extreme. TP: 1:2 RR. |
| `core/strategy_orb.py` | Opening Range Breakout | First 6 bars of each day (00:00–00:30 UTC) define range. Breakout with volume surge (×1.5 SMA) confirms entry. SL: opposite side of range. TP: 2× risk. |
| `core/strategy_rsi_mean_reversion.py` | RSI Mean Reversion | RSI 14, oversold < 30 / overbought > 70. Entry on cross back above/below threshold. SL: nearest swing in last 20 bars. TP: 1.5:1 RR. |
| `core/strategy_bb_reversal.py` | Bollinger Band Reversal | BB(20, 2). Candle closes outside band, next candle closes back inside. SL: signal candle extreme. TP: middle band (falls back to 2R if unattainable). |

**Modified:** `widgets/backtest_panel.py`
- Added 5 entries to `STRATEGIES` list (now 9 total)
- Added param blocks in `_rebuild_strategy_params()` — EMA Pullback has a `sl_mode` QComboBox (swing/atr)
- Updated `_collect_params()` to handle `QComboBox` widgets (for `sl_mode`)
- Added 5 `elif` branches in `BacktestWorker.run()` with lazy imports

### 2. Telegram Notifications + Remote Control (`live/`)

| File | Action | Description |
|------|--------|-------------|
| `live/telegram_bot.py` | **Created** | TelegramBot class — runs async polling in a daemon thread. Sends notifications (startup, entry, exit, heartbeat, safety, errors). Handles 6 remote commands + button panel. |
| `live/config.py` | Modified | Added `telegram_token`, `telegram_chat_id` to `DEFAULT_CONFIG`. Added `.env` loading for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. |
| `live/engine.py` | Modified | Added `telegram` param to `__init__`. Added `_paused` / `_stopped` / `_telegram_heartbeat_count` flags. Startup notification, `_stopped` check in main loop, heartbeat every 30 min, entry/exit notifications, pause check before new entries, safety notifications. |
| `live/run.py` | Modified | Instantiates `TelegramBot`, wires it into `LiveEngine`, starts bot thread. |
| `Pipfile` | Modified | Added `python-telegram-bot >=20.0` dependency. |

**Notification types (bot → user):**
- 🤖 Bot started (mode, exchange, symbols, capital)
- 🟢 Trade entry (symbol, side, price, qty, SL, TP)
- 🔴/🟢 Trade exit (symbol, reason, P&L, equity)
- 📊 Heartbeat every 30 min (open trades, equity, drawdown %, daily P&L)
- ⚠️ Max daily loss / max drawdown warnings
- 🛑 Bot stopped
- ⚠️ Tick errors

**Remote commands (user → bot):**

| Command/Button | Action |
|----------------|--------|
| `/start`, 📊 Status | Bot state, mode, equity, open trades |
| `/pause`, ⏸ Pause | Stop new entries (existing trades continue) |
| `/resume`, ▶ Resume | Resume new entries |
| `/stop`, 🛑 Stop | Shut down after current tick |
| `/positions`, 📋 Positions | List all open positions with SL/TP |
| `/help`, ❓ Help | Available commands |

The button panel uses a persistent `ReplyKeyboardMarkup` with 2 rows of 3 buttons each.

## Key Decisions

1. **VWAP reset**: Midnight UTC (standard for crypto — 24/7 market)
2. **EMA Pullback SL**: Dual mode — `swing` (nearest swing low/high) or `atr` (ATR × multiplier), user-selectable via dropdown. Ready for future hybrid version.
3. **ORB range**: First 6 × 5M bars of each day (00:00–00:30 UTC) — no midnight-UTC ORB since crypto never closes
4. **BB TP**: Middle band (mean reversion target), with 2R fallback
5. **Stop behavior**: `/stop` prevents new entries but lets existing trades reach SL/TP
6. **Heartbeat**: Every 30 min (15 heartbeats × 2 min interval)
7. **Telegram thread**: Daemon thread with own asyncio event loop; async message sending via `asyncio.run_coroutine_threadsafe()`

## Bugs Fixed

1. **Missing `/start` handler** — `CommandHandler("start", self._cmd_start)` was registered in `_run_polling()` but the `_cmd_start` method was never defined. Added a welcome message + button panel on `/start`.
2. **Wrong keyword argument** `persistent` in `ReplyKeyboardMarkup` — should be `is_persistent`. Error logged at `2026-06-08 10:13:47`: `ReplyKeyboardMarkup.__init__() got an unexpected keyword argument 'persistent'. Did you mean 'is_persistent'?`

## Errors Encountered

1. `UnicodeDecodeError` when verifying Python files — fixed by specifying `encoding='utf-8'` in file reads
2. `ReplyKeyboardMarkup.__init__() got an unexpected keyword argument 'persistent'` — fixed by renaming to `is_persistent`
3. Pipenv not on `PATH` — run with full path: `& "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\pipenv.exe"`

## Known Issues

1. **Strategy files not git-tracked** — 5 new `core/strategy_*.py` files may not have been committed to git
2. **Live bot only runs ATR Trend-Breakout** — the live engine hardcodes `from core.strategy_atr_breakout import run_atr_breakout`. The 5 new strategies are only available in the backtest UI
3. **No persistency** — All backtest results live in `AppState` / `st.session_state`, lost on restart
4. **Slippage always 0.0** — no UI control exists
5. **Bot needs PC running** — Telegram bot thread dies when the process stops. No cloud/24/7 hosting
6. **Logs may grow large** — `live/logs/bot.log` accumulates with no rotation

## What To Continue With Next

- [ ] **Commit new strategy files** to git if not already tracked
- [ ] **Support more strategies in live engine** — extend `_process_symbol()` to allow selecting which strategy to run per-symbol (via `config.json` or per-symbol param)
- [ ] **Regime filter** — add market regime detection (trending vs ranging) for RSI Mean Reversion and Bollinger Reversal (as noted in the strategy spec)
- [ ] **Log rotation** for `live/logs/bot.log`
- [ ] **Server hosting** — deploy the live bot to a VPS so it runs 24/7 without your PC
- [ ] **Add more remote commands** — `/settings` to show current params, `/cancel_all` to close all positions
- [ ] **Inline keyboard buttons** — replace `ReplyKeyboardMarkup` with `InlineKeyboardMarkup` for a more polished UX (buttons inline with message text)
