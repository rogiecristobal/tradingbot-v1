import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    side: int
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    sl_price: float
    tp_price: float
    exit_reason: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration: Optional[pd.Timedelta] = None
    atr_at_entry: float = 0.0
    trail_activated: bool = False
    highest_price: float = 0.0
    lowest_price: float = 0.0


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    initial_capital: float = 10000.0
    final_capital: float = 0.0
    total_return: float = 0.0


def _find_entry_bar(df: pd.DataFrame, signal_idx: int) -> Optional[int]:
    if signal_idx + 1 < len(df):
        return signal_idx + 1
    return None


def run_backtest(
    df_signals: pd.DataFrame,
    initial_capital: float = 10000.0,
    risk_percent: float = 1.0,
    fee_rate: float = 0.001,
    slippage: float = 0.0,
    max_hold_bars: int = 0,
    trail_activation_atr: float = 0.0,
    trail_offset_atr: float = 0.0,
) -> BacktestResult:
    if df_signals.empty or "signal" not in df_signals.columns:
        return BacktestResult(initial_capital=initial_capital)

    df = df_signals.copy()
    equity = float(initial_capital)
    trades: List[Trade] = []
    equity_curve = []

    open_trade: Optional[Trade] = None
    entry_bar_idx: Optional[int] = None

    for i in range(len(df)):
        idx = df.index[i]
        row = df.iloc[i]

        if open_trade is not None and entry_bar_idx is not None and i >= entry_bar_idx:
            low = row["low"]
            high = row["high"]
            close = row["close"]

            is_long = open_trade.side == 1
            is_short = open_trade.side == -1
            sl = open_trade.sl_price
            tp = open_trade.tp_price
            entry = open_trade.entry_price

            exit_price = None
            exit_reason = None

            if is_long:
                if low <= sl:
                    exit_price = sl
                    exit_reason = "sl"
                elif high >= tp:
                    exit_price = tp
                    exit_reason = "tp"
            else:
                if high >= sl:
                    exit_price = sl
                    exit_reason = "sl"
                elif low <= tp:
                    exit_price = tp
                    exit_reason = "tp"

            if exit_price is None and max_hold_bars > 0:
                bars_in_trade = i - entry_bar_idx + 1
                if bars_in_trade >= max_hold_bars:
                    exit_price = close
                    exit_reason = "max_hold"

            # Trailing stop
            if exit_price is None and open_trade.atr_at_entry > 0 and trail_activation_atr > 0:
                atr_val = open_trade.atr_at_entry
                if is_long:
                    if high > open_trade.highest_price:
                        open_trade.highest_price = high
                    if not open_trade.trail_activated:
                        if high - entry >= trail_activation_atr * atr_val:
                            open_trade.trail_activated = True
                    if open_trade.trail_activated:
                        new_sl = open_trade.highest_price - trail_offset_atr * atr_val
                        if new_sl > open_trade.sl_price:
                            open_trade.sl_price = new_sl
                            sl = new_sl
                            if low <= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"
                else:
                    if low < open_trade.lowest_price:
                        open_trade.lowest_price = low
                    if not open_trade.trail_activated:
                        if entry - low >= trail_activation_atr * atr_val:
                            open_trade.trail_activated = True
                    if open_trade.trail_activated:
                        new_sl = open_trade.lowest_price + trail_offset_atr * atr_val
                        if new_sl < open_trade.sl_price:
                            open_trade.sl_price = new_sl
                            sl = new_sl
                            if high >= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"

            if exit_price is not None:
                open_trade.exit_time = idx
                open_trade.exit_price = exit_price
                pnl = (exit_price - entry) * open_trade.quantity * open_trade.side
                pnl -= entry * open_trade.quantity * fee_rate
                pnl -= exit_price * open_trade.quantity * fee_rate
                open_trade.pnl = pnl
                open_trade.pnl_pct = (pnl / (entry * open_trade.quantity) * 100) if open_trade.quantity > 0 else 0
                open_trade.duration = idx - open_trade.entry_time
                open_trade.exit_reason = exit_reason
                trades.append(open_trade)
                equity += pnl
                open_trade = None
                entry_bar_idx = None

        if open_trade is None and i > 0:
            prev_idx = df.index[i - 1]
            prev_signal = df.loc[prev_idx, "signal"]
            prev_entry = df.loc[prev_idx, "entry_price"]
            prev_sl = df.loc[prev_idx, "sl_price"]
            prev_tp = df.loc[prev_idx, "tp_price"]

            if prev_signal != 0 and not pd.isna(prev_entry) and not pd.isna(prev_sl):
                entry_bar_idx = i
                entry_price = row["open"]

                if slippage > 0:
                    if prev_signal == 1:
                        entry_price *= (1 + slippage)
                    else:
                        entry_price *= (1 - slippage)

                diff = entry_price - prev_entry
                sl = prev_sl + diff
                tp = prev_tp + diff

                risk_per_unit = abs(entry_price - sl)
                if risk_per_unit > 0 and equity > 0:
                    risk_amount = equity * (risk_percent / 100.0)
                    quantity = risk_amount / risk_per_unit
                else:
                    quantity = 0

                open_trade = Trade(
                    entry_time=idx,
                    exit_time=None,
                    side=prev_signal,
                    entry_price=entry_price,
                    exit_price=None,
                    quantity=quantity,
                    sl_price=sl,
                    tp_price=tp,
                    exit_reason="",
                )
                if "atr" in df.columns:
                    atr_val = df.loc[prev_idx, "atr"]
                    if not pd.isna(atr_val):
                        open_trade.atr_at_entry = atr_val
                        open_trade.highest_price = entry_price
                        open_trade.lowest_price = entry_price

        equity_curve.append({"time": idx, "equity": equity})

    if open_trade is not None and open_trade.exit_time is None:
        last_idx = df.index[-1]
        last_close = df.iloc[-1]["close"]
        entry = open_trade.entry_price
        pnl = (last_close - entry) * open_trade.quantity * open_trade.side
        pnl -= entry * open_trade.quantity * fee_rate
        pnl -= last_close * open_trade.quantity * fee_rate
        open_trade.exit_time = last_idx
        open_trade.exit_price = last_close
        open_trade.pnl = pnl
        open_trade.pnl_pct = (pnl / (entry * open_trade.quantity) * 100) if open_trade.quantity > 0 else 0
        open_trade.duration = last_idx - open_trade.entry_time
        open_trade.exit_reason = "end_of_data"
        trades.append(open_trade)
        equity += pnl

    eq_df = pd.DataFrame(equity_curve)
    eq_series = (
        pd.Series(eq_df["equity"].values, index=pd.to_datetime(eq_df["time"]))
        if not eq_df.empty
        else pd.Series(dtype=float)
    )

    return BacktestResult(
        trades=trades,
        equity_curve=eq_series,
        initial_capital=initial_capital,
        final_capital=equity,
        total_return=((equity - initial_capital) / initial_capital) * 100,
    )
