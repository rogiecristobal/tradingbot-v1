import pandas as pd
import numpy as np


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def run_atr_breakout(
    df_4h: pd.DataFrame,
    risk_percent: float = 1.0,
    ema_fast: int = 50,
    ema_slow: int = 200,
    donchian_period: int = 20,
    atr_period: int = 14,
    volume_sma_period: int = 20,
    volume_mult: float = 1.5,
    atr_min_pct: float = 2.0,
    atr_sl_mult: float = 2.0,
    rr: float = 2.0,
    trail_activation: float = 2.0,
    trail_offset: float = 1.0,
    fee_rate: float = 0.001,
) -> pd.DataFrame:
    if df_4h.empty or len(df_4h) < max(ema_slow, donchian_period, atr_period, volume_sma_period, 50):
        return pd.DataFrame()

    df = df_4h.copy()

    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
    df["atr"] = _atr(df, atr_period)
    df["vol_sma"] = df["volume"].rolling(window=volume_sma_period, min_periods=volume_sma_period).mean()
    df["donchian_high"] = df["high"].rolling(window=donchian_period, min_periods=donchian_period).max()
    df["donchian_low"] = df["low"].rolling(window=donchian_period, min_periods=donchian_period).min()

    price = df["close"]
    atr_series = df["atr"]
    vol = df["volume"]
    vol_sma = df["vol_sma"]

    uptrend = df["ema_fast"] > df["ema_slow"]
    downtrend = df["ema_fast"] < df["ema_slow"]

    breakout_long = price > df["donchian_high"].shift(1)
    breakout_short = price < df["donchian_low"].shift(1)

    vol_surge = vol > vol_sma * volume_mult
    vol_gate = atr_series > price * (atr_min_pct / 100.0)

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(len(df)):
        if pd.isna(atr_series.iloc[i]) or pd.isna(vol_sma.iloc[i]):
            continue
        if pd.isna(df["donchian_high"].iloc[i]) or pd.isna(df["donchian_low"].iloc[i]):
            continue

        atr_val = atr_series.iloc[i]
        close_val = price.iloc[i]

        long_ok = (
            uptrend.iloc[i]
            and breakout_long.iloc[i]
            and vol_surge.iloc[i]
            and vol_gate.iloc[i]
        )
        short_ok = (
            downtrend.iloc[i]
            and breakout_short.iloc[i]
            and vol_surge.iloc[i]
            and vol_gate.iloc[i]
        )

        if long_ok:
            df.at[df.index[i], "signal"] = 1
            df.at[df.index[i], "entry_price"] = close_val
            df.at[df.index[i], "sl_price"] = close_val - atr_val * atr_sl_mult
            df.at[df.index[i], "tp_price"] = close_val + atr_val * atr_sl_mult * rr

        elif short_ok:
            df.at[df.index[i], "signal"] = -1
            df.at[df.index[i], "entry_price"] = close_val
            df.at[df.index[i], "sl_price"] = close_val + atr_val * atr_sl_mult
            df.at[df.index[i], "tp_price"] = close_val - atr_val * atr_sl_mult * rr

    df.drop(
        columns=[
            "ema_fast", "ema_slow", "vol_sma",
            "donchian_high", "donchian_low",
        ],
        inplace=True,
        errors="ignore",
    )

    return df
