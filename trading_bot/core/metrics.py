import pandas as pd
import numpy as np
from typing import Dict, Any
from .backtest_engine import BacktestResult


def calculate_metrics(result: BacktestResult, risk_free_rate: float = 0.02) -> Dict[str, Any]:
    trades = result.trades
    eq = result.equity_curve

    if len(trades) == 0:
        return {"error": "No trades executed"}

    wins = [t for t in trades if t.pnl is not None and t.pnl > 0]
    losses = [t for t in trades if t.pnl is not None and t.pnl <= 0]
    total_trades = len(trades)
    winning_trades = len(wins)
    losing_trades = len(losses)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    pnls = np.array([t.pnl for t in trades if t.pnl is not None])
    avg_pnl = float(np.mean(pnls)) if len(pnls) > 0 else 0
    median_pnl = float(np.median(pnls)) if len(pnls) > 0 else 0
    std_pnl = float(np.std(pnls)) if len(pnls) > 0 else 0

    best_trade = float(np.max(pnls)) if len(pnls) > 0 else 0
    worst_trade = float(np.min(pnls)) if len(pnls) > 0 else 0

    avg_win = float(np.mean([t.pnl for t in wins])) if wins else 0
    avg_loss = float(np.mean([t.pnl for t in losses])) if losses else 0

    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * abs(avg_loss))

    durations = [t.duration for t in trades if t.duration is not None]
    avg_duration = pd.Timedelta(np.mean(durations)) if durations else pd.Timedelta(0)
    avg_win_duration = (
        pd.Timedelta(np.mean([t.duration for t in wins if t.duration is not None]))
        if wins
        else pd.Timedelta(0)
    )
    avg_loss_duration = (
        pd.Timedelta(np.mean([t.duration for t in losses if t.duration is not None]))
        if losses
        else pd.Timedelta(0)
    )

    init_cap = result.initial_capital or 10000
    final_cap = result.final_capital or init_cap
    total_return_pct = result.total_return

    if len(eq) > 1:
        eq_values = eq.values.astype(float)
        peak = np.maximum.accumulate(eq_values)
        drawdown = (eq_values - peak) / peak * 100
        max_drawdown = float(np.min(drawdown))
        max_drawdown_duration = _max_drawdown_duration(drawdown)
    else:
        max_drawdown = 0.0
        max_drawdown_duration = 0

    calmar_ratio = abs(total_return_pct / max_drawdown) if max_drawdown != 0 else 0

    sharpe_ratio = _sharpe_ratio(eq, risk_free_rate)
    sortino_ratio = _sortino_ratio(eq, risk_free_rate)

    monthly_returns = _monthly_returns(eq, init_cap)

    num_bars = len(eq)
    total_days = num_bars * 5 / (24 * 60)
    cagr = _cagr(init_cap, final_cap, total_days) if total_days > 0 else 0

    recovery_factor = abs(total_return_pct / max_drawdown) if max_drawdown != 0 else float("inf")

    return {
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr, 2),
        "sharpe_ratio": round(sharpe_ratio, 3),
        "sortino_ratio": round(sortino_ratio, 3),
        "max_drawdown_pct": round(max_drawdown, 2),
        "max_drawdown_duration": int(max_drawdown_duration),
        "calmar_ratio": round(calmar_ratio, 3),
        "recovery_factor": round(recovery_factor, 2),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "expectancy": round(expectancy, 2),
        "avg_pnl": round(avg_pnl, 2),
        "median_pnl": round(median_pnl, 2),
        "std_pnl": round(std_pnl, 2),
        "best_trade_pnl": round(best_trade, 2),
        "worst_trade_pnl": round(worst_trade, 2),
        "avg_win_pnl": round(avg_win, 2),
        "avg_loss_pnl": round(avg_loss, 2),
        "avg_duration": str(avg_duration).split(".")[0],
        "avg_win_duration": str(avg_win_duration).split(".")[0],
        "avg_loss_duration": str(avg_loss_duration).split(".")[0],
        "initial_capital": round(init_cap, 2),
        "final_capital": round(final_cap, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "monthly_returns": monthly_returns,
    }


def _max_drawdown_duration(drawdown_series: np.ndarray) -> int:
    max_dur = 0
    current_dur = 0
    for dd in drawdown_series:
        if dd < 0:
            current_dur += 1
            max_dur = max(max_dur, current_dur)
        else:
            current_dur = 0
    return max_dur


def _sharpe_ratio(eq_curve: pd.Series, risk_free_rate: float = 0.02) -> float:
    if len(eq_curve) < 2:
        return 0.0
    returns = eq_curve.pct_change().dropna()
    if len(returns) == 0:
        return 0.0
    n_per_year = (365.25 * 24 * 60) / 5
    excess_returns = returns - risk_free_rate / n_per_year
    if returns.std() == 0:
        return 0.0
    return float(np.sqrt(n_per_year) * excess_returns.mean() / returns.std())


def _sortino_ratio(eq_curve: pd.Series, risk_free_rate: float = 0.02) -> float:
    if len(eq_curve) < 2:
        return 0.0
    returns = eq_curve.pct_change().dropna()
    if len(returns) == 0:
        return 0.0
    n_per_year = (365.25 * 24 * 60) / 5
    excess_returns = returns - risk_free_rate / n_per_year
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float(np.sqrt(n_per_year) * excess_returns.mean() / downside.std())


def _cagr(initial: float, final: float, days: float) -> float:
    if initial <= 0 or final <= 0 or days <= 0:
        return 0.0
    years = days / 365.25
    if years <= 0:
        return 0.0
    ratio = final / initial
    if ratio <= 0:
        return 0.0
    return (ratio ** (1 / years) - 1) * 100


def _monthly_returns(eq_curve: pd.Series, initial_capital: float) -> pd.DataFrame:
    if len(eq_curve) < 2:
        return pd.DataFrame()
    returns = eq_curve.pct_change().dropna()
    monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly = monthly * 100
    result = monthly.to_frame(name="return_pct")
    result.index = result.index.strftime("%Y-%m")
    return result
