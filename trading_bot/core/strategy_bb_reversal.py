import pandas as pd
import numpy as np


def run_bb_reversal(
    df_5m: pd.DataFrame,
    bb_period: int = 20,
    bb_std: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < bb_period * 2:
        return pd.DataFrame()

    df = df_5m.copy()
    df["sma"] = df["close"].rolling(window=bb_period, min_periods=bb_period).mean()
    df["std"] = df["close"].rolling(window=bb_period, min_periods=bb_period).std()
    df["upper"] = df["sma"] + df["std"] * bb_std
    df["lower"] = df["sma"] - df["std"] * bb_std

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        idx = df.index[i]

        close = row["close"]
        prev_close = prev["close"]
        prev_low = prev["low"]
        prev_high = prev["high"]
        prev_lower = prev["lower"]
        prev_upper = prev["upper"]
        mid = row["sma"]

        if pd.isna(prev_lower) or pd.isna(prev_upper) or pd.isna(mid):
            continue

        long_entry = prev_close < prev_lower and close > row["lower"]

        short_entry = prev_close > prev_upper and close < row["upper"]

        if long_entry:
            df.at[idx, "signal"] = 1
            df.at[idx, "entry_price"] = close
            df.at[idx, "sl_price"] = prev_low
            risk = close - prev_low
            df.at[idx, "tp_price"] = mid if mid > close else close + risk * 2

        elif short_entry:
            df.at[idx, "signal"] = -1
            df.at[idx, "entry_price"] = close
            df.at[idx, "sl_price"] = prev_high
            risk = prev_high - close
            df.at[idx, "tp_price"] = mid if mid < close else close - risk * 2

    df.drop(columns=["sma", "std", "upper", "lower"], inplace=True, errors="ignore")
    return df
