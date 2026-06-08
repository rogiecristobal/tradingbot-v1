import pandas as pd
import numpy as np


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def _find_swing_low(df: pd.DataFrame, end_i: int, lookback: int = 20) -> float:
    start_i = max(0, end_i - lookback)
    swing = float("inf")
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev = df.iloc[i - 1]["low"]
        curr = df.iloc[i]["low"]
        nxt = df.iloc[i + 1]["low"]
        if curr < prev and curr < nxt:
            swing = min(swing, curr)
    if swing == float("inf"):
        swing = df.iloc[max(0, end_i - lookback):end_i + 1]["low"].min()
    return swing


def _find_swing_high(df: pd.DataFrame, end_i: int, lookback: int = 20) -> float:
    start_i = max(0, end_i - lookback)
    swing = float("-inf")
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev = df.iloc[i - 1]["high"]
        curr = df.iloc[i]["high"]
        nxt = df.iloc[i + 1]["high"]
        if curr > prev and curr > nxt:
            swing = max(swing, curr)
    if swing == float("-inf"):
        swing = df.iloc[max(0, end_i - lookback):end_i + 1]["high"].max()
    return swing


def run_ema_pullback(
    df_5m: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    sl_mode: str = "swing",
    atr_period: int = 14,
    atr_sl_mult: float = 1.5,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < max(ema_slow, atr_period, 100):
        return pd.DataFrame()

    df = df_5m.copy()
    df["ema_fast"] = _ema(df["close"], ema_fast)
    df["ema_slow"] = _ema(df["close"], ema_slow)
    df["atr"] = _atr(df, atr_period)

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(len(df)):
        if i < 1:
            continue
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        idx = df.index[i]

        ema_f = row["ema_fast"]
        ema_s = row["ema_slow"]
        close = row["close"]
        low = row["low"]
        high = row["high"]
        prev_close = prev["close"]

        if pd.isna(ema_f) or pd.isna(ema_s) or pd.isna(row["atr"]):
            continue

        bull_trend = ema_f > ema_s
        bear_trend = ema_f < ema_s

        above_both = prev_close > ema_f and prev_close > ema_s
        pullback_long = low <= ema_f
        bullish_close = close > row["open"] and close > ema_f

        long_entry = bull_trend and above_both and pullback_long and bullish_close

        below_both = prev_close < ema_f and prev_close < ema_s
        pullback_short = high >= ema_f
        bearish_close = close < row["open"] and close < ema_f

        short_entry = bear_trend and below_both and pullback_short and bearish_close

        if long_entry:
            df.at[idx, "signal"] = 1
            df.at[idx, "entry_price"] = close
            if sl_mode == "swing":
                sl = _find_swing_low(df, i, lookback=20)
            else:
                sl = close - row["atr"] * atr_sl_mult
            df.at[idx, "sl_price"] = sl
            risk = close - sl
            df.at[idx, "tp_price"] = close + risk * rr if risk > 0 else close + row["atr"] * rr

        elif short_entry:
            df.at[idx, "signal"] = -1
            df.at[idx, "entry_price"] = close
            if sl_mode == "swing":
                sl = _find_swing_high(df, i, lookback=20)
            else:
                sl = close + row["atr"] * atr_sl_mult
            df.at[idx, "sl_price"] = sl
            risk = sl - close
            df.at[idx, "tp_price"] = close - risk * rr if risk > 0 else close - row["atr"] * rr

    df.drop(
        columns=["ema_fast", "ema_slow", "atr"],
        inplace=True,
        errors="ignore",
    )

    return df
