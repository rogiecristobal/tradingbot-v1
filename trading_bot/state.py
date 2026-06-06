import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from core.backtest_engine import BacktestResult


@dataclass
class AppState:
    exchange_id: str = "bybit"
    api_key: str = ""
    api_secret: str = ""
    symbol: str = "BTC/USDT"
    custom_symbol: str = ""
    strategy_name: str = "4H NY Range Re-Entry"
    rr: float = 2.0
    risk_percent: float = 1.0
    fee_rate: float = 0.001
    backtest_result: Optional[BacktestResult] = None
    backtest_signals: Optional[pd.DataFrame] = None
    backtest_metrics: Optional[dict] = None
    backtest_symbol: str = ""
    backtest_exchange: str = ""
