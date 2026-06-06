import pandas as pd
import numpy as np
import pytz
from datetime import datetime, time

NY_TZ = pytz.timezone("America/New_York")


def _get_ny_date(utc_dt: pd.Timestamp) -> datetime.date:
    return utc_dt.tz_convert(NY_TZ).date()


def _ny_time(utc_dt: pd.Timestamp) -> time:
    return utc_dt.tz_convert(NY_TZ).time()


def _is_ny_midnight_cross(prev_ny_date, curr_ny_date) -> bool:
    return curr_ny_date != prev_ny_date


def _find_nearest_swing_high(df: pd.DataFrame, start_i: int, end_i: int, above_val: float):
    nearest = None
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev_high = df.iloc[i - 1]["high"]
        curr_high = df.iloc[i]["high"]
        next_high = df.iloc[i + 1]["high"]
        if curr_high > prev_high and curr_high > next_high and curr_high > above_val:
            if nearest is None or curr_high < nearest:
                nearest = curr_high
    return nearest


def _find_nearest_swing_low(df: pd.DataFrame, start_i: int, end_i: int, below_val: float):
    nearest = None
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev_low = df.iloc[i - 1]["low"]
        curr_low = df.iloc[i]["low"]
        next_low = df.iloc[i + 1]["low"]
        if curr_low < prev_low and curr_low < next_low and curr_low < below_val:
            if nearest is None or curr_low > nearest:
                nearest = curr_low
    return nearest


def _find_swing_high_closest_to(df: pd.DataFrame, start_i: int, end_i: int, above_val: float, target: float):
    closest = None
    best_dist = float("inf")
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev_high = df.iloc[i - 1]["high"]
        curr_high = df.iloc[i]["high"]
        next_high = df.iloc[i + 1]["high"]
        if curr_high > prev_high and curr_high > next_high and curr_high > above_val:
            dist = abs(curr_high - target)
            if dist < best_dist:
                best_dist = dist
                closest = curr_high
    return closest


def _find_swing_low_closest_to(df: pd.DataFrame, start_i: int, end_i: int, below_val: float, target: float):
    closest = None
    best_dist = float("inf")
    for i in range(start_i, end_i + 1):
        if i <= 0 or i >= len(df) - 1:
            continue
        prev_low = df.iloc[i - 1]["low"]
        curr_low = df.iloc[i]["low"]
        next_low = df.iloc[i + 1]["low"]
        if curr_low < prev_low and curr_low < next_low and curr_low < below_val:
            dist = abs(curr_low - target)
            if dist < best_dist:
                best_dist = dist
                closest = curr_low
    return closest


def run_4h_ny_range_reentry(
    df_5m: pd.DataFrame,
    df_4h: pd.DataFrame,
    rr: float = 2.0,
    risk_percent: float = 1.0,
) -> pd.DataFrame:
    if df_5m.empty or len(df_5m) < 100 or df_4h.empty:
        return pd.DataFrame()

    df = df_5m.copy()
    df["ny_date"] = df.index.map(_get_ny_date)
    df["ny_time"] = df.index.map(_ny_time)

    df["range_high"] = np.nan
    df["range_low"] = np.nan
    df["signal"] = 0
    df["entry_price"] = np.nan
    df["sl_price"] = np.nan
    df["tp_price"] = np.nan

    unique_days = sorted(df["ny_date"].unique())

    for day in unique_days:
        ny_midnight = pd.Timestamp(
            datetime(day.year, day.month, day.day, 0, 0), tz=NY_TZ
        )
        ny_4am = pd.Timestamp(
            datetime(day.year, day.month, day.day, 4, 0), tz=NY_TZ
        )
        ny_midnight_utc = ny_midnight.tz_convert(pytz.UTC)
        ny_4am_utc = ny_4am.tz_convert(pytz.UTC)

        # 4H bars whose range overlaps NY midnight-4AM
        overlap = (
            (df_4h.index < ny_4am_utc)
            & (df_4h.index + pd.Timedelta(hours=4) > ny_midnight_utc)
        )
        session_bars = df_4h[overlap]

        if session_bars.empty:
            continue

        range_high_val = session_bars["high"].max()
        range_low_val = session_bars["low"].min()

        # Forward-fill to 5M bars after 4AM NY
        day_mask = df["ny_date"] == day
        bars_after = df[day_mask][df[day_mask].index >= ny_4am_utc]

        if bars_after.empty:
            continue

        first_bar_after = bars_after.index[0]
        df.loc[first_bar_after:, "range_high"] = range_high_val
        df.loc[first_bar_after:, "range_low"] = range_low_val

    broke_up = False
    broke_down = False
    breakout_high = np.nan
    breakout_low = np.nan
    breakout_up_start_idx = None
    breakout_down_start_idx = None

    for i in range(len(df)):
        row = df.iloc[i]
        idx = df.index[i]

        if pd.isna(row["range_high"]) or pd.isna(row["range_low"]):
            continue

        if i == 0:
            continue

        if i > 0:
            prev_ny_date = df.iloc[i - 1]["ny_date"]
            curr_ny_date = row["ny_date"]
            if _is_ny_midnight_cross(prev_ny_date, curr_ny_date):
                broke_up = False
                broke_down = False
                breakout_high = np.nan
                breakout_low = np.nan
                breakout_up_start_idx = None
                breakout_down_start_idx = None

        range_high_val = row["range_high"]
        range_low_val = row["range_low"]
        close_val = row["close"]
        high_val = row["high"]
        low_val = row["low"]

        break_above = close_val > range_high_val
        break_below = close_val < range_low_val

        if break_above:
            if not broke_up:
                breakout_up_start_idx = i
            broke_up = True
            breakout_high = high_val

        if break_below:
            if not broke_down:
                breakout_down_start_idx = i
            broke_down = True
            breakout_low = low_val

        short_signal = broke_up and (close_val < range_high_val)
        long_signal = broke_down and (close_val > range_low_val)

        if short_signal:
            df.at[idx, "signal"] = -1
            entry = close_val
            start = breakout_up_start_idx if breakout_up_start_idx is not None else breakout_down_start_idx
            swing_sl = _find_nearest_swing_high(df, start, i, entry) if start is not None else None
            range_mid = range_low_val + (range_high_val - range_low_val) / 2
            if swing_sl is not None and swing_sl > range_mid:
                swing_sl = _find_swing_high_closest_to(df, start, i, entry, range_high_val)
            sl = swing_sl if swing_sl is not None else (breakout_high if not pd.isna(breakout_high) else breakout_low)
            risk = sl - entry
            tp = entry - (risk * rr)
            df.at[idx, "entry_price"] = entry
            df.at[idx, "sl_price"] = sl
            df.at[idx, "tp_price"] = tp
            broke_up = False
            breakout_high = np.nan
            breakout_up_start_idx = None
            breakout_down_start_idx = None

        if long_signal:
            df.at[idx, "signal"] = 1
            entry = close_val
            start = breakout_down_start_idx if breakout_down_start_idx is not None else breakout_up_start_idx
            swing_sl = _find_nearest_swing_low(df, start, i, entry) if start is not None else None
            range_mid = range_low_val + (range_high_val - range_low_val) / 2
            if swing_sl is not None and swing_sl < range_mid:
                swing_sl = _find_swing_low_closest_to(df, start, i, entry, range_low_val)
            sl = swing_sl if swing_sl is not None else (breakout_low if not pd.isna(breakout_low) else breakout_high)
            risk = entry - sl
            tp = entry + (risk * rr)
            df.at[idx, "entry_price"] = entry
            df.at[idx, "sl_price"] = sl
            df.at[idx, "tp_price"] = tp
            broke_down = False
            breakout_low = np.nan
            breakout_down_start_idx = None
            breakout_up_start_idx = None

    return df
