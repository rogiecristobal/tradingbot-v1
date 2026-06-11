import os
import pandas as pd
from datetime import datetime, timedelta
import pytz
from exchange.connector import build_exchange
from typing import Callable, Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(exchange_id: str, symbol: str, timeframe: str):
    safe_sym = symbol.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{exchange_id}_{safe_sym}_{timeframe}.parquet")


def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "5m",
    start_date: str = None,
    end_date: str = None,
    use_cache: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None,
):
    if start_date is None:
        start_date = (datetime.now(pytz.UTC) - timedelta(days=90)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now(pytz.UTC).strftime("%Y-%m-%d")

    cache_path = _cache_path(exchange_id, symbol, timeframe)

    if use_cache and os.path.exists(cache_path):
        df = pd.read_parquet(cache_path)
        if not df.empty:
            latest = df.index.max()
            earliest = df.index.min()
            cached_end = latest.strftime("%Y-%m-%d")
            cached_start = earliest.strftime("%Y-%m-%d")
            if cached_end >= end_date and cached_start <= start_date:
                start_ts = pd.Timestamp(start_date, tz=pytz.UTC)
                end_ts = pd.Timestamp(end_date, tz=pytz.UTC) + timedelta(days=1)
                mask = (df.index >= start_ts) & (df.index <= end_ts)
                return df[mask].copy()

    ex = build_exchange(exchange_id)
    if ex is None:
        return pd.DataFrame()

    since = ex.parse8601(f"{start_date}T00:00:00Z")
    end_ts_ms = ex.parse8601(f"{end_date}T23:59:59Z")

    all_ohlcv = []
    limit = 1000
    max_bars = 50000
    fetched = 0

    progress_text = f"Fetching {symbol} {timeframe} data from {start_date} to {end_date}..."

    if progress_callback:
        progress_callback(0.0, progress_text)

    while since < end_ts_ms and fetched < max_bars:
        try:
            ohlcv = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            fetched += len(ohlcv)
            since = ohlcv[-1][0] + 1
            pct = min(fetched / max_bars, 0.99)
            if progress_callback:
                progress_callback(pct, progress_text)
        except Exception as e:
            msg = f"Fetch error at {since}: {e}"
            if progress_callback:
                progress_callback(0.0, msg)
            break

    if progress_callback:
        progress_callback(1.0, "Done fetching")

    if not all_ohlcv:
        return pd.DataFrame()

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep="first")]

    if use_cache:
        _ensure_cache_dir()
        df.to_parquet(cache_path)

    start_ts = pd.Timestamp(start_date, tz=pytz.UTC)
    end_ts = pd.Timestamp(end_date, tz=pytz.UTC) + timedelta(days=1)
    mask = (df.index >= start_ts) & (df.index <= end_ts)
    return df[mask].copy()
