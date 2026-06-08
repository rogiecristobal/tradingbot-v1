import json
import os
from typing import Optional, List

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

POPULAR_SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "DOT/USDT:USDT",
    "AVAX/USDT:USDT", "LINK/USDT:USDT", "MATIC/USDT:USDT", "UNI/USDT:USDT",
    "ATOM/USDT:USDT", "LTC/USDT:USDT", "BCH/USDT:USDT", "APT/USDT:USDT",
    "ARB/USDT:USDT", "OP/USDT:USDT", "SUI/USDT:USDT", "PEPE/USDT:USDT",
]

DEFAULT_PARAMS = {
    "ema_fast": 50,
    "ema_slow": 200,
    "donchian_period": 20,
    "atr_period": 14,
    "volume_sma_period": 20,
    "volume_mult": 1.5,
    "atr_min_pct": 2.0,
    "atr_sl_mult": 2.0,
    "rr": 5.0,
    "risk_percent": 3.0,
    "trail_activation": 2.0,
    "trail_offset": 1.0,
}

DEFAULT_CONFIG = {
    "exchange_id": "bybit",
    "api_key": "",
    "api_secret": "",
    "symbols": list(POPULAR_SYMBOLS),
    "mode": "paper",
    "leverage": 1,
    "params": dict(DEFAULT_PARAMS),
    "symbol_params": {},
    "positions": {s: None for s in POPULAR_SYMBOLS},
    "last_candle_times": {},
    "capital": 100.0,
    "max_daily_loss_pct": 10.0,
    "max_drawdown_pct": 20.0,
    "max_open_trades": 3,
    "telegram_token": "",
    "telegram_chat_id": "",
}


def _merge(defaults, overrides):
    result = dict(defaults)
    result.update(overrides)
    return result


def _migrate_config(data: dict):
    changed = False
    has_old = "symbol" in data or "position" in data

    if has_old:
        old_sym = data.pop("symbol", None) or (data.get("symbols", [None]) or [None])[0]
        old_pos = data.pop("position", None)
        data["symbols"] = [old_sym]
        data["positions"] = {old_sym: old_pos} if old_pos else {old_sym: None}
        data["last_candle_times"] = {}
        data["symbol_params"] = {}
        changed = True

    for k in ("positions", "last_candle_times", "symbol_params"):
        if k not in data:
            data[k] = {} if k in ("last_candle_times", "symbol_params") else {s: None for s in data.get("symbols", [])}
            changed = True

    syms = data.get("symbols", [])
    existing = set(data.get("positions", {}).keys())
    if existing != set(syms):
        for s in syms:
            if s not in data["positions"]:
                data["positions"][s] = None
                changed = True
        for s in list(data["positions"].keys()):
            if s not in syms:
                del data["positions"][s]
                changed = True

    if changed:
        save_config(data)


def _load_env_overrides(config: dict) -> dict:
    if not os.path.exists(ENV_PATH):
        return config
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "BYBIT_API_KEY" and value:
                config["api_key"] = value
            elif key == "BYBIT_API_SECRET" and value:
                config["api_secret"] = value
            elif key == "TELEGRAM_BOT_TOKEN" and value:
                config["telegram_token"] = value
            elif key == "TELEGRAM_CHAT_ID" and value:
                config["telegram_chat_id"] = value
    return config


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG, path)
        data = dict(DEFAULT_CONFIG)
    else:
        with open(path, "r") as f:
            data = json.load(f)
        data = _merge(DEFAULT_CONFIG, data)
        if "params" in data:
            data["params"] = _merge(DEFAULT_PARAMS, data.get("params", {}))
    _migrate_config(data)
    _load_env_overrides(data)
    return data


def save_config(config: dict, path: str = CONFIG_PATH):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def allocate_capital(symbols: List[str], total_capital: float) -> dict:
    if not symbols:
        return {}
    per = total_capital / len(symbols)
    return {s: per for s in symbols}
