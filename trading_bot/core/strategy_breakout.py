import pandas as pd
import numpy as np


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def run_breakout(
    df: pd.DataFrame,
    range_period: int = 20,
    range_max_pct: float = 15.0,
    vol_sma_period: int = 20,
    vol_mult: float = 1.8,
    atr_period: int = 14,
    rr: float = 2.5,
    risk_percent: float = 1.0,
) -> pd.DataFrame:
    if df.empty or len(df) < max(range_period, vol_sma_period, atr_period) + 5:
        return pd.DataFrame()

    result = df.copy()
    result["range_high"] = result["high"].rolling(window=range_period, min_periods=range_period).max()
    result["range_low"] = result["low"].rolling(window=range_period, min_periods=range_period).min()
    result["range_depth"] = (result["range_high"] - result["range_low"]) / result["range_high"] * 100
    result["vol_sma"] = result["volume"].rolling(window=vol_sma_period, min_periods=vol_sma_period).mean()
    result["atr"] = _atr(result, atr_period)

    result["tight_range"] = result["range_depth"] < range_max_pct
    result["vol_surge"] = result["volume"] > result["vol_sma"] * vol_mult
    result["breakout_high"] = result["close"] > result["range_high"].shift(1)

    result["entry_cond"] = (
        result["tight_range"]
        & result["vol_surge"]
        & result["breakout_high"]
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan

    for i in range(len(result)):
        if result.iloc[i]["entry_cond"]:
            close_val = result.iloc[i]["close"]
            atr_val = result.iloc[i]["atr"]
            range_low = result.iloc[i]["range_low"]
            if pd.isna(atr_val) or atr_val == 0:
                continue
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = range_low - 0.1 * atr_val
            result.at[result.index[i], "tp_price"] = close_val + (close_val - (range_low - 0.1 * atr_val)) * rr

    result.drop(
        columns=[
            "range_high", "range_low", "range_depth",
            "vol_sma", "atr", "tight_range",
            "vol_surge", "breakout_high", "entry_cond",
        ],
        inplace=True,
        errors="ignore",
    )

    return result
