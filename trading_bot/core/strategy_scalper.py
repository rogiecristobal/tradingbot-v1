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


def run_scalper(
    df: pd.DataFrame,
    ema_length: int = 20,
    rsi_length: int = 14,
    rsi_buy: int = 40,
    rsi_sell: int = 60,
    rr: float = 2.0,
    risk_percent: float = 100.0,
) -> pd.DataFrame:
    if df.empty or len(df) < max(ema_length, rsi_length, 50):
        return pd.DataFrame()

    result = df.copy()
    result["ema"] = _ema(result["close"], ema_length)
    result["rsi"] = _rsi(result["close"], rsi_length)

    result["above_ema"] = result["close"] > result["ema"]
    result["below_ema"] = result["close"] < result["ema"]
    result["rsi_below_buy"] = result["rsi"] < rsi_buy
    result["rsi_above_sell"] = result["rsi"] > rsi_sell
    result["rsi_rising"] = result["rsi"] > result["rsi"].shift(1)
    result["rsi_falling"] = result["rsi"] < result["rsi"].shift(1)

    result["buy_raw"] = (
        result["above_ema"]
        & result["rsi_below_buy"]
        & result["rsi_rising"]
    )
    result["sell_raw"] = (
        result["below_ema"]
        & result["rsi_above_sell"]
        & result["rsi_falling"]
    )

    result["signal"] = 0
    result["entry_price"] = np.nan
    result["sl_price"] = np.nan
    result["tp_price"] = np.nan

    for i in range(len(result)):
        if result.iloc[i]["buy_raw"]:
            close_val = result.iloc[i]["close"]
            result.at[result.index[i], "signal"] = 1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val * 0.995
            result.at[result.index[i], "tp_price"] = close_val * 1.01

        elif result.iloc[i]["sell_raw"]:
            close_val = result.iloc[i]["close"]
            result.at[result.index[i], "signal"] = -1
            result.at[result.index[i], "entry_price"] = close_val
            result.at[result.index[i], "sl_price"] = close_val * 1.005
            result.at[result.index[i], "tp_price"] = close_val * 0.99

    result.drop(
        columns=[
            "ema", "rsi",
            "above_ema", "below_ema",
            "rsi_below_buy", "rsi_above_sell",
            "rsi_rising", "rsi_falling",
            "buy_raw", "sell_raw",
        ],
        inplace=True,
        errors="ignore",
    )

    return result
