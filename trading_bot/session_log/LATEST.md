# Session: SLC Strategy (Structure-Level-Confirmation) + ccxt Startup Fix

**Date:** 2026-06-10

---

## Summary

Built the SLC (Structure-Level-Confirmation) backtest strategy — a 3-tier multi-timeframe system (4H structure, 1H supply/demand zones, 15M confirmation + entry). Fixed a pre-existing startup hang caused by top-level `import ccxt`. The app now launches in ~1.4s vs. 30-90s previously.

---

## Files Created

### `trading_bot/core/strategy_slc.py` (new, 366 lines)

Full SLC strategy implementation following the spec from the "Systematic Crypto Version" video.

**Architecture:** Fetches 15M OHLCV only; resamples internally to 1H (zone detection) and 4H (trend structure) via `pd.DataFrame.resample()`.

**Pipeline components:**

| Step | Timeframe | Logic |
|---|---|---|
| **S — Structure** | 4H (resampled) | EMA200 + slope over `ema_slope_bars`. Trend = 1 if price > EMA200 and slope > 0; -1 if price < EMA200 and slope < 0; 0 otherwise. Merged into 15M via `pd.merge_asof` with `.shift(1)` for lookahead safety. |
| **L — Level** | 1H (resampled) | Stateful loop detecting bearish impulse candles (range > `impulse_mult * ATR`) after a bullish base → supply zone, and bullish impulses after a bearish base → demand zone. Zone = full range `[high, low]` of the base candle. Touch count increments on entry; zone invalid after 2 touches. Shifted +1 before merge into 15M. |
| **C — Confirmation** | 15M | 4 detectors OR'd together: (1) bullish/bearish engulfing, (2) pin bar with wick ≥ 60% of range + body < 30%, (3) CHOCH via swing point break, (4) break of minor support/resistance. |
| **Entry** | 15M | All 3 must align. SL = zone boundary ± `zone_buffer_atr * ATR`. TP = entry ± risk × fixed RR. |

**8 adjustable UI params:** EMA Length, EMA Slope Bars, Swing Window, ATR Period, Impulse ATR Multiplier, Zone Buffer (ATR), Risk:Reward, Risk per trade.

**Helpers defined:** `_resample_ohlcv`, `_ema`, `_atr`, `_is_bull_engulfing`, `_is_bear_engulfing`, `_is_bull_pin_bar`, `_is_bear_pin_bar`, `_find_swing_highs`, `_find_swing_lows`.

---

## Files Modified

### `trading_bot/widgets/backtest_panel.py` (3 insertions)

1. **Line 26** — Added `"SLC (Structure-Level-Confirmation)"` to `STRATEGIES` list
2. **Lines 58, 61** — Added `is_slc` flag alongside `is_ibr`, shares 15M timeframe
3. **Lines 138-151** — Added `elif is_slc:` block in `BacktestWorker.run()` importing and calling `run_slc()` with all 9 params
4. **Lines 344-353** — Added `elif name == "SLC..."` block in `_rebuild_strategy_params()` with 9 param widgets

### `trading_bot/exchange/connector.py` (bug fix)

**Problem:** Top-level `import ccxt` at module startup imported all 110+ exchange classes, blocking the GUI for 30-90 seconds on Windows.

**Fix:** Moved `import ccxt` into the two functions that need it (`get_exchange_names()` and `build_exchange()`). `validate_credentials()` and `get_markets()` already delegate to `build_exchange()`, so they needed no change.

| Line | Before | After |
|------|--------|-------|
| 1 | `import ccxt` | *(removed)* |
| 8 | `return sorted(ccxt.exchanges)` | `import ccxt` inside function first |
| 13 | `exchange_class = getattr(ccxt, exchange_id, None)` | `import ccxt` inside function first |

---

## Bash Commands Executed

| Command | Purpose | Result |
|---------|---------|--------|
| `pipenv run python -c "import py_compile; ..."` *×2* | Syntax check both changed .py files | PASS |
| `pipenv run python -c "from core.strategy_slc import run_slc"` | Verify runtime import | PASS |
| `pipenv run python -c "from widgets.backtest_panel import BacktestPanel, STRATEGIES"` | Verify UI registration + strategy list | 5 strategies printed |
| `pipenv run python -c "..."` (mock 3000-bar DataFrame) | Smoke test strategy logic | 69 signals generated on random data, correct columns |
| `pipenv run python -c "from widgets.settings_panel import SettingsPanel"` | Verify startup import no longer hangs | 0.66s (previously 30-90s) |
| `pipenv run python -c "..."` (verbose startup timing) | Measure full app startup time | 1.39s total |

---

## Errors Encountered

1. **`import ccxt` startup hang (30-90s)** — Top-level `import ccxt` in `connector.py` blocked GUI initialization. Fixed with lazy imports inside functions.

2. **Bybit API connection failure** — Warnings `Failed to init bybit (attempt N/3): bybit GET https://api.bybit.com/v5/market/instruments-info?category=spot` appear at startup. These come from `build_exchange("bybit")` when `load_markets()` is called during validation (no API key mode). Root cause: firewall/network blocking Bybit API. Non-blocking — the QApplication event loop is already running by this point (it runs as a delayed log line after `app.exec()` starts). The app is fully usable for backtesting; only live trading/bybit data fetches will fail.

---

## Known Issues

- **Bybit API blocked** — Same issue as previous sessions. The exchange's REST API (`api.bybit.com`) is inaccessible from this network. Workaround: use a different exchange or VPN.
- **SLC untuned on real data** — Strategy passed smoke test on random data but hasn't been backtested with real OHLCV data. Zone detection thresholds (`impulse_mult=1.5`, `zone_buffer_atr=0.3`) may need tuning per market.
- **No max_hold_bars** — Unlike NY Range (288 bars), SLC has no force-close mechanism. A runaway trade could theoretically hold indefinitely. Add a `max_hold_bars` param if needed.
- **Zone invalidation is strict** — Invalidated after 2 touches. Some traders prefer tracking chop vs. clean breakout for the second touch. The strict model might miss re-entries after a clean displacement.
- **CHOCH detection is basic** — Uses simple swing-point breakout. Doesn't distinguish between micro-structure shifts during ranging markets vs. genuine trend reversals. May produce false confirmation signals in choppy 15M action.

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **15M primary, resample to 1H/4H internally** | Single data fetch (one API call), cleaner code, matches IBR pattern. User confirmed. |
| **Invalidate zone after 2 touches** | Matches spec (first/second interaction only). User confirmed. |
| **Swing window = 5 bars (user-adjustable)** | Balances reactivity vs false signals. User requested making it a parameter. |
| **Confidence = OR of 4 detectors** | Engulfing + pin bar + CHOCH + support/resistance break. Any single one is enough for entry when structure + zone align. |
| **Lazy ccxt import** | Eliminates 30-90s startup delay. CCXT loads on-demand only when user opens Settings or runs a backtest. |
| **Followed IBR pattern** for resampling, merge_asof, shift(1) lookahead protection | Proven pattern already in the codebase. The backtest engine and metrics pipeline work unchanged. |

---

## What to Continue With Next

1. **Backtest SLC on real data** — Run on BTC/USDT or ETH/USDT with 90+ days of history. Tune thresholds.
2. **Add `max_hold_bars` param** — Guard against runaway trades (e.g. 288 bars = 3 days on 15M).
3. **Add stochastic RSI as optional bonus confirmation** — Spec mentions this as a non-required filter. Could increase win rate.
4. **FVG detection** — Spec mentions FVG inside impulse as optional criterion for zone strength scoring.
5. **Partial TP (TP1 = 1R, TP2 = next opposing zone)** — The spec's "better version" of TP logic.
6. **Fix Bybit API connectivity** — If live trading on Bybit is needed, resolve firewall/VPN issue.
