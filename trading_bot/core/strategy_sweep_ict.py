import pandas as pd
import numpy as np


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


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


def run_sweep_ict(
    df: pd.DataFrame,
    lookback: int = 10,
    rsi_length: int = 14,
    rsi_oversold: int = 35,
    rsi_overbought: int = 65,
    atr_period: int = 14,
    atr_sl_mult: float = 0.5,
    rr: float = 2.0,
    risk_percent: float = 1.0,
) -> pd.DataFrame:
    if df.empty or len(df) < max(lookback, rsi_length, atr_period, 30):
        return pd.DataFrame()

    result = df.copy()
    result["rsi"] = _rsi(result["close"], rsi_length)
    result["atr"] = _atr(result, atr_period)
    result["swing_high"] = result["high"].rolling(window=lookback, min_periods=lookback).max()
    result["swing_low"] = result["low"].rolling(window=lookback, min_periods=lookback).min()

    result["sweep_high"] = result["high"] > result["swing_high"].shift(1)
    result["sweep_low"] = result["low"] < result["swing_low"].shift(1)

    result["close_up"] = result["close"] > result["close"].shift(1)
    result["close_down"] = result["close"] < result["close"].shift(1)

    result["rsi_lo"] = result["rsi"] < rsi_oversold
    result["rsi_hi"] = result["rsi"] > rsi_overbought

    result["buy_cond"] = (
        result["sweep_low"]
        & (result["close_up"] | result["rsi_lo"])
    )
    result["sell_cond"] = (
        result["sweep_high"]
        & (result["close_down"] | result["rsi_hi"])
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan

    for i in range(len(result)):
        atr_val = result.iloc[i]["atr"]
        swing_low = result.iloc[i]["swing_low"]
        swing_high = result.iloc[i]["swing_high"]
        if pd.isna(atr_val) or atr_val == 0:
            continue

        if result.iloc[i]["buy_cond"]:
            close_val = result.iloc[i]["close"]
            sl_price = swing_low - atr_sl_mult * atr_val
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = sl_price
            result.at[result.index[i], "tp_price"] = close_val + abs(close_val - sl_price) * rr

        elif result.iloc[i]["sell_cond"]:
            close_val = result.iloc[i]["close"]
            sl_price = swing_high + atr_sl_mult * atr_val
            result.at[result.index[i], "signal"] = -1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = sl_price
            result.at[result.index[i], "tp_price"] = close_val - abs(close_val - sl_price) * rr

    result.drop(
        columns=[
            "rsi", "atr", "swing_high", "swing_low",
            "sweep_high", "sweep_low",
            "close_up", "close_down",
            "rsi_lo", "rsi_hi",
            "buy_cond", "sell_cond",
        ],
        inplace=True,
        errors="ignore",
    )

    return result
