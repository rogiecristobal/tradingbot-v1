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
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def run_trend_breakout(
    df: pd.DataFrame,
    ema_length: int = 20,
    breakout_period: int = 10,
    vol_sma_period: int = 20,
    vol_mult: float = 1.5,
    atr_period: int = 14,
    atr_sl_mult: float = 0.3,
    trail_pct: float = 3.0,
    risk_percent: float = 1.0,
) -> pd.DataFrame:
    if df.empty or len(df) < max(ema_length, breakout_period, vol_sma_period, atr_period) + 5:
        return pd.DataFrame()

    result = df.copy()
    result["ema"] = _ema(result["close"], ema_length)
    result["atr"] = _atr(result, atr_period)
    result["breakout_high"] = result["high"].rolling(window=breakout_period, min_periods=breakout_period).max()
    result["vol_sma"] = result["volume"].rolling(window=vol_sma_period, min_periods=vol_sma_period).mean()

    result["above_ema"] = result["close"] > result["ema"]
    result["new_high"] = result["high"] > result["breakout_high"].shift(1)
    result["vol_surge"] = result["volume"] > result["vol_sma"] * vol_mult

    result["entry_cond"] = (
        result["above_ema"]
        & result["new_high"]
        & result["vol_surge"]
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan
    result["atr_original"] = result["atr"]

    for i in range(len(result)):
        if result.iloc[i]["entry_cond"]:
            close_val = result.iloc[i]["close"]
            low_val = result.iloc[i]["low"]
            atr_val = result.iloc[i]["atr"]
            if pd.isna(atr_val) or atr_val == 0:
                continue
            sl_val = low_val - atr_sl_mult * atr_val
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = sl_val
            tp_val = close_val + (close_val - sl_val) * 2.0
            result.at[result.index[i], "tp_price"] = tp_val
            result.at[result.index[i], "atr"] = atr_val

    result.drop(
        columns=[
            "ema", "atr_original", "breakout_high", "vol_sma",
            "above_ema", "new_high", "vol_surge", "entry_cond",
        ],
        inplace=True,
        errors="ignore",
    )

    return result
