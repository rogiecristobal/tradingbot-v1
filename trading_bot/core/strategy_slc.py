import pandas as pd
import numpy as np


def _resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    return df.resample(timeframe).agg({
        "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum",
    }).dropna()


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _is_bull_engulfing(df: pd.DataFrame, i: int) -> bool:
    if i < 1:
        return False
    prev = df.iloc[i - 1]
    cur = df.iloc[i]
    return (
        cur["close"] > cur["open"]
        and cur["open"] < prev["close"]
        and cur["close"] > prev["open"]
    )


def _is_bear_engulfing(df: pd.DataFrame, i: int) -> bool:
    if i < 1:
        return False
    prev = df.iloc[i - 1]
    cur = df.iloc[i]
    return (
        cur["close"] < cur["open"]
        and cur["open"] > prev["close"]
        and cur["close"] < prev["open"]
    )


def _is_bull_pin_bar(row: pd.Series) -> bool:
    body = abs(row["close"] - row["open"])
    total = row["high"] - row["low"]
    if total <= 0 or body <= 0:
        return False
    lower_wick = min(row["close"], row["open"]) - row["low"]
    return lower_wick > total * 0.6 and body < total * 0.3


def _is_bear_pin_bar(row: pd.Series) -> bool:
    body = abs(row["close"] - row["open"])
    total = row["high"] - row["low"]
    if total <= 0 or body <= 0:
        return False
    upper_wick = row["high"] - max(row["close"], row["open"])
    return upper_wick > total * 0.6 and body < total * 0.3


def _find_swing_highs(high: pd.Series, window: int) -> pd.Series:
    rolled = high.rolling(window=window, min_periods=window).max().shift(1)
    return high > rolled


def _find_swing_lows(low: pd.Series, window: int) -> pd.Series:
    rolled = low.rolling(window=window, min_periods=window).min().shift(1)
    return low < rolled


def run_slc(
    df: pd.DataFrame,
    ema_length: int = 200,
    ema_slope_bars: int = 5,
    swing_window: int = 5,
    atr_period: int = 14,
    impulse_mult: float = 1.5,
    zone_buffer_atr: float = 0.3,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df.empty or len(df) < 288:
        return pd.DataFrame()

    df_15m = df.copy()
    df_1h = _resample_ohlcv(df_15m, "1h")
    df_4h = _resample_ohlcv(df_15m, "4h")

    if df_1h.empty or len(df_1h) < 20 or df_4h.empty:
        return pd.DataFrame()

    # ── S — Structure (4H Trend) ──
    df_4h["ema200"] = _ema(df_4h["close"], ema_length)
    df_4h["ema_slope"] = df_4h["ema200"] - df_4h["ema200"].shift(ema_slope_bars)
    df_4h["trend"] = 0
    bull = (df_4h["close"] > df_4h["ema200"]) & (df_4h["ema_slope"] > 0)
    bear = (df_4h["close"] < df_4h["ema200"]) & (df_4h["ema_slope"] < 0)
    df_4h.loc[bull, "trend"] = 1
    df_4h.loc[bear, "trend"] = -1

    df_15m = pd.merge_asof(
        df_15m.sort_index(),
        df_4h[["trend"]].shift(1).sort_index(),
        left_index=True, right_index=True, direction="backward",
    )
    df_15m.rename(columns={"trend": "trend_4h"}, inplace=True)
    df_15m["trend_4h"] = df_15m["trend_4h"].fillna(0).astype(int)

    # ── L — Level (1H Supply/Demand Zones) ──
    df_1h["atr"] = _atr(df_1h, atr_period)
    df_1h["candle_range"] = df_1h["high"] - df_1h["low"]
    df_1h["impulse_bull"] = (
        (df_1h["close"] > df_1h["open"])
        & (df_1h["candle_range"] > df_1h["atr"] * impulse_mult)
    )
    df_1h["impulse_bear"] = (
        (df_1h["close"] < df_1h["open"])
        & (df_1h["candle_range"] > df_1h["atr"] * impulse_mult)
    )
    df_1h["bull_candle"] = df_1h["close"] > df_1h["open"]
    df_1h["bear_candle"] = df_1h["close"] < df_1h["open"]

    # Stateful zone tracking
    last_bull_bar_idx = None
    last_bear_bar_idx = None

    supply_zone_high = np.nan
    supply_zone_low = np.nan
    supply_touch_count = 0
    supply_valid = False

    demand_zone_high = np.nan
    demand_zone_low = np.nan
    demand_touch_count = 0
    demand_valid = False

    out_supply_high = pd.Series(np.nan, index=df_1h.index)
    out_supply_low = pd.Series(np.nan, index=df_1h.index)
    out_supply_valid = pd.Series(False, index=df_1h.index)
    out_demand_high = pd.Series(np.nan, index=df_1h.index)
    out_demand_low = pd.Series(np.nan, index=df_1h.index)
    out_demand_valid = pd.Series(False, index=df_1h.index)

    for i in range(len(df_1h)):
        idx = df_1h.index[i]
        row = df_1h.iloc[i]
        close = row["close"]
        high = row["high"]
        low = row["low"]

        # Track last bullish/bearish candle
        if row["bull_candle"]:
            last_bull_bar_idx = i
        if row["bear_candle"]:
            last_bear_bar_idx = i

        # Create supply zone: bearish impulse after a bullish base candle
        if (
            row["impulse_bear"]
            and last_bull_bar_idx is not None
            and last_bull_bar_idx < i
        ):
            base = df_1h.iloc[last_bull_bar_idx]
            supply_zone_high = base["high"]
            supply_zone_low = base["low"]
            supply_touch_count = 0
            supply_valid = True

        # Create demand zone: bullish impulse after a bearish base candle
        if (
            row["impulse_bull"]
            and last_bear_bar_idx is not None
            and last_bear_bar_idx < i
        ):
            base = df_1h.iloc[last_bear_bar_idx]
            demand_zone_high = base["high"]
            demand_zone_low = base["low"]
            demand_touch_count = 0
            demand_valid = True

        # Check zone interactions (price enters zone)
        if supply_valid and not pd.isna(supply_zone_high):
            if high >= supply_zone_low and low <= supply_zone_high:
                supply_touch_count += 1
                if supply_touch_count >= 2:
                    supply_valid = False

        if demand_valid and not pd.isna(demand_zone_high):
            if high >= demand_zone_low and low <= demand_zone_high:
                demand_touch_count += 1
                if demand_touch_count >= 2:
                    demand_valid = False

        out_supply_high.iloc[i] = supply_zone_high if supply_valid else np.nan
        out_supply_low.iloc[i] = supply_zone_low if supply_valid else np.nan
        out_supply_valid.iloc[i] = supply_valid
        out_demand_high.iloc[i] = demand_zone_high if demand_valid else np.nan
        out_demand_low.iloc[i] = demand_zone_low if demand_valid else np.nan
        out_demand_valid.iloc[i] = demand_valid

    df_1h_out = pd.DataFrame({
        "supply_zone_high": out_supply_high,
        "supply_zone_low": out_supply_low,
        "supply_zone_valid": out_supply_valid,
        "demand_zone_high": out_demand_high,
        "demand_zone_low": out_demand_low,
        "demand_zone_valid": out_demand_valid,
    }, index=df_1h.index)

    df_15m = pd.merge_asof(
        df_15m.sort_index(),
        df_1h_out.shift(1).sort_index(),
        left_index=True, right_index=True, direction="backward",
    )

    for col in ["supply_zone_valid", "demand_zone_valid"]:
        df_15m[col] = df_15m[col].fillna(False).astype(bool)

    # ── C — Confirmation (15M Price Action) ──
    df_15m["bull_engulf"] = False
    df_15m["bear_engulf"] = False
    df_15m["bull_pin"] = False
    df_15m["bear_pin"] = False

    for i in range(len(df_15m)):
        if i < 1:
            continue
        df_15m.at[df_15m.index[i], "bull_engulf"] = _is_bull_engulfing(df_15m, i)
        df_15m.at[df_15m.index[i], "bear_engulf"] = _is_bear_engulfing(df_15m, i)
        df_15m.at[df_15m.index[i], "bull_pin"] = _is_bull_pin_bar(df_15m.iloc[i])
        df_15m.at[df_15m.index[i], "bear_pin"] = _is_bear_pin_bar(df_15m.iloc[i])

    # CHOCH detection via swing points
    df_15m["swing_high"] = _find_swing_highs(df_15m["high"], swing_window)
    df_15m["swing_low"] = _find_swing_lows(df_15m["low"], swing_window)

    # CHOCH up: price breaks above a recent swing high after a downtrend
    recent_swing_high = np.nan
    recent_swing_low = np.nan

    choch_up = pd.Series(False, index=df_15m.index)
    choch_down = pd.Series(False, index=df_15m.index)
    break_resistance = pd.Series(False, index=df_15m.index)
    break_support = pd.Series(False, index=df_15m.index)

    for i in range(len(df_15m)):
        idx = df_15m.index[i]
        row = df_15m.iloc[i]

        if row["swing_high"]:
            recent_swing_high = row["high"]
        if row["swing_low"]:
            recent_swing_low = row["low"]

        if not pd.isna(recent_swing_high) and row["close"] > recent_swing_high:
            choch_up.iloc[i] = True
        if not pd.isna(recent_swing_low) and row["close"] < recent_swing_low:
            choch_down.iloc[i] = True

        if not pd.isna(recent_swing_high) and row["close"] > recent_swing_high:
            break_resistance.iloc[i] = True
        if not pd.isna(recent_swing_low) and row["close"] < recent_swing_low:
            break_support.iloc[i] = True

    df_15m["choch_up"] = choch_up
    df_15m["choch_down"] = choch_down
    df_15m["break_resistance"] = break_resistance
    df_15m["break_support"] = break_support

    df_15m["bull_conf"] = (
        df_15m["bull_engulf"]
        | df_15m["bull_pin"]
        | df_15m["choch_up"]
        | df_15m["break_resistance"]
    )
    df_15m["bear_conf"] = (
        df_15m["bear_engulf"]
        | df_15m["bear_pin"]
        | df_15m["choch_down"]
        | df_15m["break_support"]
    )

    # ── Entry Generation ──
    df_15m["signal"] = 0
    df_15m["entry_price"] = np.nan
    df_15m["sl_price"] = np.nan
    df_15m["tp_price"] = np.nan
    df_15m["atr"] = _atr(df_15m, atr_period)

    for i in range(len(df_15m)):
        row = df_15m.iloc[i]
        idx = df_15m.index[i]

        trend = row["trend_4h"]
        if trend == 0:
            continue

        if trend == 1:
            zone_ok = (
                row["demand_zone_valid"]
                and not pd.isna(row["demand_zone_high"])
                and not pd.isna(row["demand_zone_low"])
                and row["low"] <= row["demand_zone_high"]
                and row["high"] >= row["demand_zone_low"]
            )
            conf_ok = row["bull_conf"]
            if not zone_ok or not conf_ok:
                continue
            if pd.isna(row["atr"]):
                continue
            entry = row["close"]
            sl = row["demand_zone_low"] - row["atr"] * zone_buffer_atr
            if sl >= entry:
                continue
            risk = entry - sl
            tp = entry + risk * rr
            df_15m.at[idx, "signal"] = 1

        else:
            zone_ok = (
                row["supply_zone_valid"]
                and not pd.isna(row["supply_zone_high"])
                and not pd.isna(row["supply_zone_low"])
                and row["low"] <= row["supply_zone_high"]
                and row["high"] >= row["supply_zone_low"]
            )
            conf_ok = row["bear_conf"]
            if not zone_ok or not conf_ok:
                continue
            if pd.isna(row["atr"]):
                continue
            entry = row["close"]
            sl = row["supply_zone_high"] + row["atr"] * zone_buffer_atr
            if sl <= entry:
                continue
            risk = sl - entry
            tp = entry - risk * rr
            df_15m.at[idx, "signal"] = -1

        df_15m.at[idx, "entry_price"] = entry
        df_15m.at[idx, "sl_price"] = sl
        df_15m.at[idx, "tp_price"] = tp

    # ── Cleanup ──
    extra_cols = [
        "trend_4h",
        "supply_zone_high", "supply_zone_low", "supply_zone_valid",
        "demand_zone_high", "demand_zone_low", "demand_zone_valid",
        "bull_engulf", "bear_engulf", "bull_pin", "bear_pin",
        "swing_high", "swing_low",
        "choch_up", "choch_down", "break_resistance", "break_support",
        "bull_conf", "bear_conf",
    ]
    df_15m.drop(columns=[c for c in extra_cols if c in df_15m.columns], inplace=True, errors="ignore")

    return df_15m
