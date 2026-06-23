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
    max_concurrent_trades: int = 18,
) -> BacktestResult:
    if df_signals.empty or "signal" not in df_signals.columns:
        return BacktestResult(initial_capital=initial_capital)

    df = df_signals.copy()
    equity = float(initial_capital)
    trades: List[Trade] = []
    equity_curve = []

    open_trades: List[Trade] = []
    entry_bar_indices: List[int] = []

    for i in range(len(df)):
        idx = df.index[i]
        row = df.iloc[i]

        for j in range(len(open_trades) - 1, -1, -1):
            ot = open_trades[j]
            ebi = entry_bar_indices[j]
            if i < ebi:
                continue

            low = row["low"]
            high = row["high"]
            close = row["close"]

            is_long = ot.side == 1
            sl = ot.sl_price
            tp = ot.tp_price
            entry = ot.entry_price

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
                bars_in_trade = i - ebi + 1
                if bars_in_trade >= max_hold_bars:
                    exit_price = close
                    exit_reason = "max_hold"

            if exit_price is None and ot.atr_at_entry > 0 and trail_activation_atr > 0:
                atr_val = ot.atr_at_entry
                if is_long:
                    if high > ot.highest_price:
                        ot.highest_price = high
                    if not ot.trail_activated:
                        if high - entry >= trail_activation_atr * atr_val:
                            ot.trail_activated = True
                    if ot.trail_activated:
                        new_sl = ot.highest_price - trail_offset_atr * atr_val
                        if new_sl > ot.sl_price:
                            ot.sl_price = new_sl
                            sl = new_sl
                            if low <= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"
                else:
                    if low < ot.lowest_price:
                        ot.lowest_price = low
                    if not ot.trail_activated:
                        if entry - low >= trail_activation_atr * atr_val:
                            ot.trail_activated = True
                    if ot.trail_activated:
                        new_sl = ot.lowest_price + trail_offset_atr * atr_val
                        if new_sl < ot.sl_price:
                            ot.sl_price = new_sl
                            sl = new_sl
                            if high >= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"

            if exit_price is not None:
                ot.exit_time = idx
                ot.exit_price = exit_price
                pnl = (exit_price - entry) * ot.quantity * ot.side
                pnl -= entry * ot.quantity * fee_rate
                pnl -= exit_price * ot.quantity * fee_rate
                ot.pnl = pnl
                ot.pnl_pct = (pnl / (entry * ot.quantity) * 100) if ot.quantity > 0 else 0
                ot.duration = idx - ot.entry_time
                ot.exit_reason = exit_reason
                trades.append(ot)
                equity += pnl
                open_trades.pop(j)
                entry_bar_indices.pop(j)

        if len(open_trades) < max_concurrent_trades and i > 0:
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

                new_trade = Trade(
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
                        new_trade.atr_at_entry = atr_val
                        new_trade.highest_price = entry_price
                        new_trade.lowest_price = entry_price
                open_trades.append(new_trade)
                entry_bar_indices.append(i)

        equity_curve.append({"time": idx, "equity": equity})

    for ot in open_trades:
        last_idx = df.index[-1]
        last_close = df.iloc[-1]["close"]
        entry = ot.entry_price
        pnl = (last_close - entry) * ot.quantity * ot.side
        pnl -= entry * ot.quantity * fee_rate
        pnl -= last_close * ot.quantity * fee_rate
        ot.exit_time = last_idx
        ot.exit_price = last_close
        ot.pnl = pnl
        ot.pnl_pct = (pnl / (entry * ot.quantity) * 100) if ot.quantity > 0 else 0
        ot.duration = last_idx - ot.entry_time
        ot.exit_reason = "end_of_data"
        trades.append(ot)
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
