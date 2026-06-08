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


def _find_swing_highs(high: pd.Series, window: int) -> pd.Series:
    rolled = high.rolling(window=window, min_periods=window).max().shift(1)
    return high > rolled


def _find_swing_lows(low: pd.Series, window: int) -> pd.Series:
    rolled = low.rolling(window=window, min_periods=window).min().shift(1)
    return low < rolled


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


def run_ibr(
    df_15m: pd.DataFrame,
    ema_length: int = 200,
    ema_slope_bars: int = 5,
    swing_window: int = 5,
    fib_min: float = 0.382,
    fib_max: float = 0.618,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_15m.empty or len(df_15m) < 288:
        return pd.DataFrame()

    df_1h = _resample_ohlcv(df_15m, "1h")
    df_4h = _resample_ohlcv(df_15m, "4h")
    if df_1h.empty or len(df_1h) < 20 or df_4h.empty:
        return pd.DataFrame()

    # ── 4H Trend ──
    df_4h["ema200"] = _ema(df_4h["close"], ema_length)
    df_4h["trend"] = 0
    bull = (df_4h["close"] > df_4h["ema200"]) & (
        df_4h["ema200"] > df_4h["ema200"].shift(ema_slope_bars)
    )
    bear = (df_4h["close"] < df_4h["ema200"]) & (
        df_4h["ema200"] < df_4h["ema200"].shift(ema_slope_bars)
    )
    df_4h.loc[bull, "trend"] = 1
    df_4h.loc[bear, "trend"] = -1

    # Merge 4H trend into 15M (lookahead-safe: shift 1 period)
    df_15m = pd.merge_asof(
        df_15m.sort_index(),
        df_4h[["trend"]].shift(1).sort_index(),
        left_index=True, right_index=True, direction="backward",
    )
    df_15m.rename(columns={"trend": "trend_4h"}, inplace=True)
    df_15m["trend_4h"] = df_15m["trend_4h"].fillna(0).astype(int)

    # ── 1H Indicators ──
    df_1h["atr"] = _atr(df_1h, 14)
    df_1h["body_range"] = (df_1h["close"] - df_1h["open"]).abs()
    df_1h["candle_range"] = df_1h["high"] - df_1h["low"]
    df_1h["body_pct"] = df_1h["body_range"] / df_1h["candle_range"].replace(0, np.nan)
    df_1h["displacement"] = df_1h["close"].diff().abs()

    # Swing pivots
    df_1h["swing_high"] = _find_swing_highs(df_1h["high"], swing_window)
    df_1h["swing_low"] = _find_swing_lows(df_1h["low"], swing_window)

    # FVG strict
    df_1h["fvg_bull_strict"] = df_1h["low"] > df_1h["high"].shift(1)
    df_1h["fvg_bear_strict"] = df_1h["high"] < df_1h["low"].shift(1)

    # FVG imbalance
    df_1h["fvg_bull_imb"] = (
        (df_1h["close"] > df_1h["open"])
        & (df_1h["body_pct"] > 0.6)
        & (df_1h["displacement"] > df_1h["atr"])
    )
    df_1h["fvg_bear_imb"] = (
        (df_1h["close"] < df_1h["open"])
        & (df_1h["body_pct"] > 0.6)
        & (df_1h["displacement"] > df_1h["atr"])
    )

    # FVG composite
    df_1h["fvg_bull"] = df_1h["fvg_bull_strict"] | df_1h["fvg_bull_imb"]
    df_1h["fvg_bear"] = df_1h["fvg_bear_strict"] | df_1h["fvg_bear_imb"]
    df_1h["fvg_bull_score"] = np.where(
        df_1h["fvg_bull_strict"], 2,
        np.where(df_1h["fvg_bull_imb"], 1, 0),
    )
    df_1h["fvg_bear_score"] = np.where(
        df_1h["fvg_bear_strict"], 2,
        np.where(df_1h["fvg_bear_imb"], 1, 0),
    )

    # Impulse candles
    df_1h["impulse_bull"] = (
        (df_1h["close"] > df_1h["open"])
        & (df_1h["candle_range"] > df_1h["atr"] * 1.5)
    )
    df_1h["impulse_bear"] = (
        (df_1h["close"] < df_1h["open"])
        & (df_1h["candle_range"] > df_1h["atr"] * 1.5)
    )

    # ── 1H State Tracking ──
    last_swing_high = np.nan
    last_swing_low = np.nan

    bull_zone_active = False
    bull_zone_high = np.nan
    bull_zone_low = np.nan
    bull_zone_fvg = 0
    bull_retest_count = 0
    bull_struct_broken = False
    bull_retest_ok = False
    bull_impulse_high = np.nan
    bull_swing_at_entry = np.nan

    bear_zone_active = False
    bear_zone_high = np.nan
    bear_zone_low = np.nan
    bear_zone_fvg = 0
    bear_retest_count = 0
    bear_struct_broken = False
    bear_retest_ok = False
    bear_impulse_low = np.nan
    bear_swing_at_entry = np.nan

    out_bull_zone = pd.Series(False, index=df_1h.index)
    out_bull_retest = pd.Series(False, index=df_1h.index)
    out_bull_struct = pd.Series(False, index=df_1h.index)
    out_bull_zone_high = pd.Series(np.nan, index=df_1h.index)
    out_bull_zone_low = pd.Series(np.nan, index=df_1h.index)
    out_bull_swing = pd.Series(np.nan, index=df_1h.index)

    out_bear_zone = pd.Series(False, index=df_1h.index)
    out_bear_retest = pd.Series(False, index=df_1h.index)
    out_bear_struct = pd.Series(False, index=df_1h.index)
    out_bear_zone_high = pd.Series(np.nan, index=df_1h.index)
    out_bear_zone_low = pd.Series(np.nan, index=df_1h.index)
    out_bear_swing = pd.Series(np.nan, index=df_1h.index)

    for i in range(len(df_1h)):
        idx = df_1h.index[i]
        row = df_1h.iloc[i]
        close = row["close"]
        high = row["high"]
        low = row["low"]

        # ── Bullish zone ──
        if (
            not bull_zone_active
            and row["impulse_bull"]
            and row["fvg_bull"]
            and not pd.isna(last_swing_high)
            and close > last_swing_high
        ):
            bull_zone_active = True
            bull_zone_high = high
            bull_zone_low = row["open"]
            bull_zone_fvg = row["fvg_bull_score"]
            bull_impulse_high = high
            bull_swing_at_entry = last_swing_high
            bull_retest_count = 0
            bull_struct_broken = True
            bull_retest_ok = False

        # ── Bullish retest ──
        if bull_zone_active and bull_struct_broken and not bull_retest_ok:
            impulse_range = bull_impulse_high - bull_swing_at_entry
            if impulse_range > 0:
                retrace = (bull_impulse_high - close) / impulse_range
                if fib_min <= retrace <= fib_max and close >= bull_swing_at_entry:
                    bull_retest_ok = True
                    bull_retest_count += 1
                elif close < bull_swing_at_entry:
                    bull_struct_broken = False

        if bull_retest_count >= 2:
            bull_zone_active = False

        out_bull_zone.iloc[i] = bull_zone_active
        out_bull_retest.iloc[i] = bull_retest_ok
        out_bull_struct.iloc[i] = bull_struct_broken
        out_bull_zone_high.iloc[i] = bull_zone_high if bull_zone_active else np.nan
        out_bull_zone_low.iloc[i] = bull_zone_low if bull_zone_active else np.nan
        out_bull_swing.iloc[i] = bull_swing_at_entry if bull_zone_active else np.nan

        # ── Bearish zone ──
        if (
            not bear_zone_active
            and row["impulse_bear"]
            and row["fvg_bear"]
            and not pd.isna(last_swing_low)
            and close < last_swing_low
        ):
            bear_zone_active = True
            bear_zone_high = row["open"]
            bear_zone_low = low
            bear_zone_fvg = row["fvg_bear_score"]
            bear_impulse_low = low
            bear_swing_at_entry = last_swing_low
            bear_retest_count = 0
            bear_struct_broken = True
            bear_retest_ok = False

        # ── Bearish retest ──
        if bear_zone_active and bear_struct_broken and not bear_retest_ok:
            impulse_range = bear_swing_at_entry - bear_impulse_low
            if impulse_range > 0:
                retrace = (close - bear_impulse_low) / impulse_range
                if fib_min <= retrace <= fib_max and close <= bear_swing_at_entry:
                    bear_retest_ok = True
                    bear_retest_count += 1
                elif close > bear_swing_at_entry:
                    bear_struct_broken = False

        if bear_retest_count >= 2:
            bear_zone_active = False

        out_bear_zone.iloc[i] = bear_zone_active
        out_bear_retest.iloc[i] = bear_retest_ok
        out_bear_struct.iloc[i] = bear_struct_broken
        out_bear_zone_high.iloc[i] = bear_zone_high if bear_zone_active else np.nan
        out_bear_zone_low.iloc[i] = bear_zone_low if bear_zone_active else np.nan
        out_bear_swing.iloc[i] = bear_swing_at_entry if bear_zone_active else np.nan

        # Update swing points after all zone checks (no lookahead)
        if row["swing_high"]:
            last_swing_high = high
        if row["swing_low"]:
            last_swing_low = low

    # ── Merge 1H state → 15M (lookahead-safe: shift 1) ──
    df_1h_out = pd.DataFrame({
        "zone_bull": out_bull_zone,
        "retest_bull": out_bull_retest,
        "struct_bull": out_bull_struct,
        "zone_bull_high": out_bull_zone_high,
        "zone_bull_low": out_bull_zone_low,
        "swing_bull": out_bull_swing,
        "zone_bear": out_bear_zone,
        "retest_bear": out_bear_retest,
        "struct_bear": out_bear_struct,
        "zone_bear_high": out_bear_zone_high,
        "zone_bear_low": out_bear_zone_low,
        "swing_bear": out_bear_swing,
    }, index=df_1h.index)

    df_1h_out["fvg_bull_score"] = df_1h["fvg_bull_score"]
    df_1h_out["fvg_bear_score"] = df_1h["fvg_bear_score"]

    df_15m = pd.merge_asof(
        df_15m.sort_index(),
        df_1h_out.shift(1).sort_index(),
        left_index=True, right_index=True, direction="backward",
    )

    for col in ["zone_bull", "retest_bull", "struct_bull",
                 "zone_bear", "retest_bear", "struct_bear"]:
        df_15m[col] = df_15m[col].fillna(False).astype(bool)

    for col in ["fvg_bull_score", "fvg_bear_score"]:
        df_15m[col] = df_15m[col].fillna(0).astype(int)

    # ── 15M Entry ──
    df_15m["signal"] = 0
    df_15m["entry_price"] = np.nan
    df_15m["sl_price"] = np.nan
    df_15m["tp_price"] = np.nan

    vol_sma = df_15m["volume"].rolling(20, min_periods=20).mean()

    for i in range(len(df_15m)):
        if i < 1:
            continue
        row = df_15m.iloc[i]
        idx = df_15m.index[i]

        trend = row["trend_4h"]
        if trend == 0:
            continue

        if trend == 1:
            zone_ok = row["zone_bull"]
            fvg_score = int(row["fvg_bull_score"])
            struct_ok = row["struct_bull"]
            retest_ok = row["retest_bull"]
            pa_ok = _is_bull_engulfing(df_15m, i) or _is_bull_pin_bar(row)
        else:
            zone_ok = row["zone_bear"]
            fvg_score = int(row["fvg_bear_score"])
            struct_ok = row["struct_bear"]
            retest_ok = row["retest_bear"]
            pa_ok = _is_bear_engulfing(df_15m, i) or _is_bear_pin_bar(row)

        if not pa_ok:
            continue

        vol_ok = (
            not pd.isna(vol_sma.iloc[i])
            and vol_sma.iloc[i] > 0
            and row["volume"] > vol_sma.iloc[i] * 1.5
        )

        score = 0
        if trend != 0:
            score += 1
        if zone_ok:
            score += 1 + (1 if fvg_score >= 2 else 0)
        if struct_ok:
            score += 1
        if retest_ok:
            score += 1
        if pa_ok:
            score += 1
        if vol_ok:
            score += 1

        if score < 4:
            continue

        entry = row["close"]

        if trend == 1:
            swing_price = row["swing_bull"]
            zone_low = row["zone_bull_low"]
            sl = min(s for s in [swing_price, zone_low] if not pd.isna(s)) if not pd.isna(swing_price) or not pd.isna(zone_low) else entry * 0.99
            if pd.isna(sl):
                continue
            if sl >= entry:
                continue
            risk = entry - sl
            tp = entry + risk * rr
            df_15m.at[idx, "signal"] = 1
        else:
            swing_price = row["swing_bear"]
            zone_high = row["zone_bear_high"]
            sl = max(s for s in [swing_price, zone_high] if not pd.isna(s)) if not pd.isna(swing_price) or not pd.isna(zone_high) else entry * 1.01
            if pd.isna(sl):
                continue
            if sl <= entry:
                continue
            risk = sl - entry
            tp = entry - risk * rr
            df_15m.at[idx, "signal"] = -1

        df_15m.at[idx, "entry_price"] = entry
        df_15m.at[idx, "sl_price"] = sl
        df_15m.at[idx, "tp_price"] = tp

    # Clean up merge columns
    extra_cols = [
        "trend_4h",
        "zone_bull", "retest_bull", "struct_bull",
        "zone_bull_high", "zone_bull_low", "swing_bull",
        "zone_bear", "retest_bear", "struct_bear",
        "zone_bear_high", "zone_bear_low", "swing_bear",
        "fvg_bull_score", "fvg_bear_score",
    ]
    df_15m.drop(columns=[c for c in extra_cols if c in df_15m.columns], inplace=True, errors="ignore")

    return df_15m
