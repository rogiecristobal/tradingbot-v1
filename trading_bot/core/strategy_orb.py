import pandas as pd
import numpy as np


def run_orb(
    df_5m: pd.DataFrame,
    range_bars: int = 6,
    volume_mult: float = 1.5,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < max(range_bars + 20, 50):
        return pd.DataFrame()

    df = df_5m.copy()
    df["day"] = df.index.date
    df["vol_sma"] = df["volume"].rolling(window=20, min_periods=20).mean()

    df["range_high"] = np.nan
    df["range_low"] = np.nan

    for day in df["day"].unique():
        day_mask = df["day"] == day
        day_indices = df.index[day_mask]
        if len(day_indices) < range_bars:
            continue

        first_bars = day_indices[:range_bars]
        range_h = df.loc[first_bars, "high"].max()
        range_l = df.loc[first_bars, "low"].min()

        after_range = day_indices[range_bars:]
        if len(after_range) == 0:
            continue
        df.loc[after_range, "range_high"] = range_h
        df.loc[after_range, "range_low"] = range_l

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(len(df)):
        row = df.iloc[i]
        idx = df.index[i]

        range_h = row["range_high"]
        range_l = row["range_low"]
        close = row["close"]
        vol = row["volume"]
        vol_sma = row["vol_sma"]

        if pd.isna(range_h) or pd.isna(range_l) or pd.isna(vol_sma) or vol_sma == 0:
            continue

        vol_ok = vol > vol_sma * volume_mult

        if close > range_h and vol_ok:
            df.at[idx, "signal"] = 1
            df.at[idx, "entry_price"] = close
            df.at[idx, "sl_price"] = range_l
            risk = close - range_l
            df.at[idx, "tp_price"] = close + risk * rr if risk > 0 else close * 1.02

        elif close < range_l and vol_ok:
            df.at[idx, "signal"] = -1
            df.at[idx, "entry_price"] = close
            df.at[idx, "sl_price"] = range_h
            risk = range_h - close
            df.at[idx, "tp_price"] = close - risk * rr if risk > 0 else close * 0.98

    df.drop(
        columns=["day", "vol_sma", "range_high", "range_low"],
        inplace=True,
        errors="ignore",
    )
    return df
