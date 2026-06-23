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


def run_ma_crossover(
    df: pd.DataFrame,
    fast_ema: int = 10,
    slow_ema: int = 30,
    atr_period: int = 14,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df.empty or len(df) < slow_ema + 5:
        return pd.DataFrame()

    result = df.copy()
    result["fast_ema"] = _ema(result["close"], fast_ema)
    result["slow_ema"] = _ema(result["close"], slow_ema)
    result["atr"] = _atr(result, atr_period)

    result["cross_above"] = (
        (result["fast_ema"] > result["slow_ema"])
        & (result["fast_ema"].shift(1) <= result["slow_ema"].shift(1))
    )
    result["cross_below"] = (
        (result["fast_ema"] < result["slow_ema"])
        & (result["fast_ema"].shift(1) >= result["slow_ema"].shift(1))
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan

    for i in range(len(result)):
        atr_val = result.iloc[i]["atr"]
        if pd.isna(atr_val) or atr_val == 0:
            continue

        if result.iloc[i]["cross_above"]:
            close_val = result.iloc[i]["close"]
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val - 1.5 * atr_val
            result.at[result.index[i], "tp_price"] = close_val + atr_val * rr

        elif result.iloc[i]["cross_below"]:
            close_val = result.iloc[i]["close"]
            result.at[result.index[i], "signal"] = -1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val + 1.5 * atr_val
            result.at[result.index[i], "tp_price"] = close_val - atr_val * rr

    result.drop(
        columns=["fast_ema", "slow_ema", "atr", "cross_above", "cross_below"],
        inplace=True,
        errors="ignore",
    )

    return result
