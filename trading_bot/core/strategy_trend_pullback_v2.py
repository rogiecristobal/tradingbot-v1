import pandas as pd
import numpy as np


def _rsi(series: pd.Series, length: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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


def run_trend_pullback_v2(
    df_5m: pd.DataFrame,
    rr: float = 1.5,
    risk_percent: float = 1.0,
    ema_length: int = 200,
    rsi_length: int = 14,
    rsi_buy_lower: int = 30,
    rsi_buy_upper: int = 40,
    rsi_sell_upper: int = 70,
    rsi_sell_lower: int = 60,
    atr_period: int = 14,
    atr_sl_mult: float = 1.5,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < max(ema_length, rsi_length, 50):
        return pd.DataFrame()

    df = df_5m.copy()
    df["rsi"] = _rsi(df["close"], rsi_length)
    df["atr"] = _atr(df, atr_period)
    df["ema"] = df["close"].ewm(span=ema_length, adjust=False).mean()

    df["trend_bull"] = df["close"] > df["ema"]
    df["trend_bear"] = df["close"] < df["ema"]

    df["rsi_cross_above_lower"] = (
        (df["rsi"] > rsi_buy_lower) & (df["rsi"].shift(1) <= rsi_buy_lower)
    )
    df["rsi_cross_below_upper"] = (
        (df["rsi"] < rsi_sell_upper) & (df["rsi"].shift(1) >= rsi_sell_upper)
    )

    df["rsi_in_buy_zone"] = (df["rsi"] < rsi_buy_upper) & (df["rsi"] > rsi_buy_lower)
    df["rsi_in_sell_zone"] = (df["rsi"] > rsi_sell_lower) & (df["rsi"] < rsi_sell_upper)

    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    for i in range(len(df)):
        row = df.iloc[i]
        idx = df.index[i]

        if pd.isna(row["atr"]) or pd.isna(row["rsi"]):
            continue

        buy_condition = (
            row["trend_bull"]
            and row["rsi_cross_above_lower"]
            and row["rsi_in_buy_zone"]
        )

        sell_condition = (
            row["trend_bear"]
            and row["rsi_cross_below_upper"]
            and row["rsi_in_sell_zone"]
        )

        if buy_condition:
            df.at[idx, "signal"] = 1
            close_val = row["close"]
            atr_val = row["atr"]
            df.at[idx, "entry_price"] = close_val
            df.at[idx, "sl_price"] = close_val - atr_val * atr_sl_mult
            df.at[idx, "tp_price"] = close_val + atr_val * atr_sl_mult * rr

        elif sell_condition:
            df.at[idx, "signal"] = -1
            close_val = row["close"]
            atr_val = row["atr"]
            df.at[idx, "entry_price"] = close_val
            df.at[idx, "sl_price"] = close_val + atr_val * atr_sl_mult
            df.at[idx, "tp_price"] = close_val - atr_val * atr_sl_mult * rr

    df.drop(
        columns=[
            "rsi", "atr", "ema",
            "trend_bull", "trend_bear",
            "rsi_cross_above_lower", "rsi_cross_below_upper",
            "rsi_in_buy_zone", "rsi_in_sell_zone",
        ],
        inplace=True,
        errors="ignore",
    )

    return df
