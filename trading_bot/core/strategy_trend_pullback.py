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


def run_trend_pullback(
    df_5m: pd.DataFrame,
    ema_length: int = 200,
    rsi_length: int = 14,
    rsi_buy: int = 35,
    rsi_sell: int = 65,
    rr: float = 1.5,
    atr_period: int = 14,
    risk_percent: float = 1.0,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < max(ema_length, rsi_length, 50):
        return pd.DataFrame()

    df = df_5m.copy()
    df["ema"] = _ema(df["close"], ema_length)
    df["rsi"] = _rsi(df["close"], rsi_length)
    df["atr"] = _atr(df, atr_period)
    df["vol_sma"] = df["volume"].rolling(window=20, min_periods=20).mean()

    df["bull_trend"] = df["close"] > df["ema"]
    df["bear_trend"] = df["close"] < df["ema"]
    df["vol_filter"] = df["volume"] > df["vol_sma"]

    df["rsi_below_buy"] = df["rsi"] < rsi_buy
    df["rsi_above_sell"] = df["rsi"] > rsi_sell

    df["rsi_cross_above_buy"] = (
        (df["rsi"] > rsi_buy) & (df["rsi"].shift(1) <= rsi_buy)
    )
    df["rsi_cross_above_sell"] = (
        (df["rsi"] > rsi_sell) & (df["rsi"].shift(1) <= rsi_sell)
    )

    df["buy_signal_raw"] = (
        df["bull_trend"]
        & df["rsi_below_buy"]
        & df["rsi_cross_above_buy"]
        & df["vol_filter"]
    )

    df["sell_signal_raw"] = (
        df["bear_trend"]
        & df["rsi_above_sell"]
        & df["rsi_cross_above_sell"]
        & df["vol_filter"]
    )

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(len(df)):
        if df.iloc[i]["buy_signal_raw"]:
            df.at[df.index[i], "signal"] = 1
            close_val = df.iloc[i]["close"]
            atr_val = df.iloc[i]["atr"]
            df.at[df.index[i], "entry_price"] = close_val
            df.at[df.index[i], "sl_price"] = close_val - atr_val
            df.at[df.index[i], "tp_price"] = close_val + atr_val * rr

        elif df.iloc[i]["sell_signal_raw"]:
            df.at[df.index[i], "signal"] = -1
            close_val = df.iloc[i]["close"]
            atr_val = df.iloc[i]["atr"]
            df.at[df.index[i], "entry_price"] = close_val
            df.at[df.index[i], "sl_price"] = close_val + atr_val
            df.at[df.index[i], "tp_price"] = close_val - atr_val * rr

    df.drop(
        columns=[
            "ema", "rsi", "atr", "vol_sma",
            "bull_trend", "bear_trend", "vol_filter",
            "rsi_below_buy", "rsi_above_sell",
            "rsi_cross_above_buy", "rsi_cross_above_sell",
            "buy_signal_raw", "sell_signal_raw",
        ],
        inplace=True,
        errors="ignore",
    )

    return df
