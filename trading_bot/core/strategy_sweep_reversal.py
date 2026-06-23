import pandas as pd
import numpy as np


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


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


def _prev_day_high_low(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = df.index.date if hasattr(df.index, "date") else df.index
    daily = df.resample("D").agg({"high": "max", "low": "min"})
    daily["pdh"] = daily["high"].shift(1)
    daily["pdl"] = daily["low"].shift(1)
    df = df.join(daily[["pdh", "pdl"]], how="left")
    df["pdh"] = df["pdh"].ffill()
    df["pdl"] = df["pdl"].ffill()
    return df


def run_sweep_reversal(
    df: pd.DataFrame,
    range_period: int = 20,
    rsi_length: int = 14,
    rsi_oversold: int = 35,
    rsi_overbought: int = 65,
    atr_period: int = 14,
    atr_sl_mult: float = 0.5,
    rr: float = 2.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df.empty or len(df) < max(range_period, rsi_length, atr_period, 50):
        return pd.DataFrame()

    result = df.copy()
    result["rsi"] = _rsi(result["close"], rsi_length)
    result["atr"] = _atr(result, atr_period)
    result["range20_high"] = result["high"].rolling(window=range_period, min_periods=range_period).max()
    result["range20_low"] = result["low"].rolling(window=range_period, min_periods=range_period).min()

    daily_df = _prev_day_high_low(result)
    result["pdh"] = daily_df["pdh"]
    result["pdl"] = daily_df["pdl"]

    result["sweep_low"] = (
        (result["low"] < result["pdl"])
        | (result["low"] < result["range20_low"].shift(1))
    )
    result["sweep_high"] = (
        (result["high"] > result["pdh"])
        | (result["high"] > result["range20_high"].shift(1))
    )

    result["price_bounce"] = result["close"] > result["close"].shift(1)
    result["price_drop"] = result["close"] < result["close"].shift(1)

    result["rsi_oversold"] = result["rsi"] < rsi_oversold
    result["rsi_overbought"] = result["rsi"] > rsi_overbought

    result["buy_cond"] = (
        result["sweep_low"]
        & (result["price_bounce"] | result["rsi_oversold"])
    )
    result["sell_cond"] = (
        result["sweep_high"]
        & (result["price_drop"] | result["rsi_overbought"])
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan

    for i in range(len(result)):
        atr_val = result.iloc[i]["atr"]
        if pd.isna(atr_val) or atr_val == 0:
            continue

        if result.iloc[i]["buy_cond"]:
            close_val = result.iloc[i]["close"]
            sl_dist = atr_sl_mult * atr_val
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val - sl_dist
            result.at[result.index[i], "tp_price"] = close_val + sl_dist * rr

        elif result.iloc[i]["sell_cond"]:
            close_val = result.iloc[i]["close"]
            sl_dist = atr_sl_mult * atr_val
            result.at[result.index[i], "signal"] = -1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val + sl_dist
            result.at[result.index[i], "tp_price"] = close_val - sl_dist * rr

    result.drop(
        columns=[
            "rsi", "atr", "range20_high", "range20_low",
            "pdh", "pdl", "sweep_low", "sweep_high",
            "price_bounce", "price_drop",
            "rsi_oversold", "rsi_overbought",
            "buy_cond", "sell_cond",
        ],
        inplace=True,
        errors="ignore",
    )

    return result
