import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


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
    "symbol": "BTC/USDT:USDT",
    "mode": "paper",
    "leverage": 1,
    "params": dict(DEFAULT_PARAMS),
    "position": None,
    "capital": 10000.0,
    "max_daily_loss_pct": 10.0,
    "max_drawdown_pct": 20.0,
}


def _merge(defaults, overrides):
    result = dict(defaults)
    result.update(overrides)
    return result


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG, path)
        return dict(DEFAULT_CONFIG)
    with open(path, "r") as f:
        data = json.load(f)
    merged = _merge(DEFAULT_CONFIG, data)
    if "params" in data:
        merged["params"] = _merge(DEFAULT_PARAMS, data["params"])
    return merged


def save_config(config: dict, path: str = CONFIG_PATH):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
