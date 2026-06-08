import pandas as pd
import numpy as np


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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


def run_rsi_mean_reversion(
    df_5m: pd.DataFrame,
    rsi_length: int = 14,
    rsi_oversold: int = 30,
    rsi_overbought: int = 70,
    rr: float = 1.5,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < max(rsi_length * 2, 50):
        return pd.DataFrame()

    df = df_5m.copy()
    df["rsi"] = _rsi(df["close"], rsi_length)

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

        rsi = row["rsi"]
        prev_rsi = prev["rsi"]
        close = row["close"]

        if pd.isna(rsi) or pd.isna(prev_rsi):
            continue

        cross_above = prev_rsi < rsi_oversold and rsi > rsi_oversold

        cross_below = prev_rsi > rsi_overbought and rsi < rsi_overbought

        if cross_above:
            df.at[idx, "signal"] = 1
            df.at[idx, "entry_price"] = close
            sl = _find_swing_low(df, i, lookback=20)
            df.at[idx, "sl_price"] = sl
            risk = close - sl
            df.at[idx, "tp_price"] = close + risk * rr if risk > 0 else close * 1.01

        elif cross_below:
            df.at[idx, "signal"] = -1
            df.at[idx, "entry_price"] = close
            sl = _find_swing_high(df, i, lookback=20)
            df.at[idx, "sl_price"] = sl
            risk = sl - close
            df.at[idx, "tp_price"] = close - risk * rr if risk > 0 else close * 0.99

    df.drop(columns=["rsi"], inplace=True, errors="ignore")
    return df
