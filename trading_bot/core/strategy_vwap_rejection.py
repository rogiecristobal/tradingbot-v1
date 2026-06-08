import pandas as pd
import numpy as np


def _vwap(df_day: pd.DataFrame) -> pd.Series:
    typical = (df_day["high"] + df_day["low"] + df_day["close"]) / 3
    vol = df_day["volume"]
    cum_pv = (typical * vol).cumsum()
    cum_vol = vol.cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def run_vwap_rejection(
    df_5m: pd.DataFrame,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < 100:
        return pd.DataFrame()

    df = df_5m.copy()
    df["vwap"] = np.nan

    for day, group in df.groupby(df.index.date):
        if group.empty:
            continue
        df.loc[group.index, "vwap"] = _vwap(group)

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

        vwap = row["vwap"]
        prev_vwap = prev["vwap"]

        if pd.isna(vwap) or pd.isna(prev_vwap):
            continue

        close = row["close"]
        low = row["low"]
        high = row["high"]

        was_above = prev["close"] > prev_vwap
        touches_vwap = low <= vwap and close > vwap
        bullish = close > row["open"]

        long_entry = was_above and touches_vwap and bullish

        was_below = prev["close"] < prev_vwap
        touches_vwap_short = high >= vwap and close < vwap
        bearish = close < row["open"]

        short_entry = was_below and touches_vwap_short and bearish

        if long_entry:
            df.at[idx, "signal"] = 1
            df.at[idx, "entry_price"] = close
            sl = low * 0.999
            df.at[idx, "sl_price"] = sl
            risk = close - sl
            df.at[idx, "tp_price"] = close + risk * rr if risk > 0 else close * 1.02

        elif short_entry:
            df.at[idx, "signal"] = -1
            df.at[idx, "entry_price"] = close
            sl = high * 1.001
            df.at[idx, "sl_price"] = sl
            risk = sl - close
            df.at[idx, "tp_price"] = close - risk * rr if risk > 0 else close * 0.98

    df.drop(columns=["vwap"], inplace=True, errors="ignore")
    return df
