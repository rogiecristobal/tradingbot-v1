import argparse
import sys
from datetime import datetime, timedelta

from data.ohlcv import fetch_ohlcv
from core.backtest_engine import run_backtest
from core.metrics import calculate_metrics


def parse_args():
    p = argparse.ArgumentParser(
        description="Crypto Trading Bot — CLI Backtest",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--exchange", default="bybit", help="Exchange ID (ccxt)")
    p.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    p.add_argument(
        "--strategy", default="atr-breakout",
        choices=["atr-breakout", "trend-pullback", "ny-range", "ibr", "slc"],
        help="Strategy to test",
    )
    p.add_argument("--lookback", type=int, default=90, help="Days of history")
    p.add_argument("--capital", type=float, default=10000, help="Initial capital ($)")

    # Shared strategy params
    p.add_argument("--rr", type=float, default=2.0, help="Risk:Reward ratio")
    p.add_argument("--risk-percent", type=float, default=1.0, help="Risk per trade (%)")
    p.add_argument("--fee-rate", type=float, default=0.001, help="Fee rate (decimal)")

    # ATR Breakout params
    p.add_argument("--ema-fast", type=int, default=50)
    p.add_argument("--ema-slow", type=int, default=200)
    p.add_argument("--donchian-period", type=int, default=20)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--volume-sma-period", type=int, default=20)
    p.add_argument("--volume-mult", type=float, default=1.5)
    p.add_argument("--atr-min-pct", type=float, default=2.0)
    p.add_argument("--atr-sl-mult", type=float, default=2.0)
    p.add_argument("--trail-activation", type=float, default=2.0)
    p.add_argument("--trail-offset", type=float, default=1.0)

    # Trend Pullback / IBR / SLC params
    p.add_argument("--ema-length", type=int, default=200)
    p.add_argument("--ema-slope-bars", type=int, default=5)
    p.add_argument("--rsi-length", type=int, default=14)
    p.add_argument("--rsi-buy", type=int, default=35)
    p.add_argument("--rsi-sell", type=int, default=65)
    p.add_argument("--swing-window", type=int, default=5)
    p.add_argument("--atr-sl", type=float, default=1.0, help="ATR SL multiplier")
    p.add_argument("--impulse-mult", type=float, default=1.5)
    p.add_argument("--zone-buffer-atr", type=float, default=0.3)

    # IBR params
    p.add_argument("--fib-min", type=float, default=0.382)
    p.add_argument("--fib-max", type=float, default=0.618)

    return p.parse_args()


def main():
    args = parse_args()

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.lookback)).strftime("%Y-%m-%d")

    strategy = args.strategy

    # Determine timeframe
    if strategy == "atr-breakout":
        tf, tf_label = "4h", "4-hour"
    elif strategy in ("ibr", "slc"):
        tf, tf_label = "15m", "15-minute"
    else:
        tf, tf_label = "5m", "5-minute"

    print(f"┌──────────────────────────────────────────────┐")
    print(f"│  Backtest CLI                                │")
    print(f"│  Exchange: {args.exchange:<28s} │")
    print(f"│  Symbol:   {args.symbol:<28s} │")
    print(f"│  Strategy: {strategy:<28s} │")
    print(f"│  Timeframe: {tf:<27s} │")
    print(f"│  Period:   {start_date} → {end_date}        │")
    print(f"│  Capital:  ${args.capital:>8.2f}                │")
    print(f"└──────────────────────────────────────────────┘")

    print(f"\nFetching {args.symbol} {tf} data...")
    df = fetch_ohlcv(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=tf,
        start_date=start_date,
        end_date=end_date,
        use_cache=True,
    )
    if df.empty:
        print("Error: no data fetched.")
        sys.exit(1)
    print(f"Got {len(df):,} bars.\n")

    # Run strategy
    params = {
        "risk_percent": args.risk_percent,
        "rr": args.rr,
        "fee_rate": args.fee_rate,
    }

    if strategy == "atr-breakout":
        from core.strategy_atr_breakout import run_atr_breakout
        params.update(
            ema_fast=args.ema_fast, ema_slow=args.ema_slow,
            donchian_period=args.donchian_period, atr_period=args.atr_period,
            volume_sma_period=args.volume_sma_period, volume_mult=args.volume_mult,
            atr_min_pct=args.atr_min_pct, atr_sl_mult=args.atr_sl_mult,
            trail_activation=args.trail_activation, trail_offset=args.trail_offset,
        )
        signals = run_atr_breakout(df, **params)
        trail_act = args.trail_activation
        trail_off = args.trail_offset

    elif strategy == "trend-pullback":
        from core.strategy_trend_pullback import run_trend_pullback
        params.update(
            ema_length=args.ema_length, rsi_length=args.rsi_length,
            rsi_buy=args.rsi_buy, rsi_sell=args.rsi_sell,
            atr_period=args.atr_period if hasattr(args, 'atr_period') else 14,
        )
        signals = run_trend_pullback(df, **params)
        trail_act = trail_off = 0

    elif strategy == "ny-range":
        from core.strategy import run_4h_ny_range_reentry
        print("Fetching 4H data for NY range calculation...")
        df_4h = fetch_ohlcv(
            exchange_id=args.exchange, symbol=args.symbol,
            timeframe="4h", start_date=start_date, end_date=end_date,
            use_cache=True,
        )
        if df_4h.empty:
            print("Error: no 4H data.")
            sys.exit(1)
        signals = run_4h_ny_range_reentry(df, df_4h, rr=args.rr, risk_percent=args.risk_percent)
        trail_act = trail_off = 0

    elif strategy == "ibr":
        from core.strategy_ibr import run_ibr
        params.update(
            ema_length=args.ema_length, ema_slope_bars=args.ema_slope_bars,
            swing_window=args.swing_window, fib_min=args.fib_min,
            fib_max=args.fib_max,
        )
        signals = run_ibr(df, **params)
        trail_act = trail_off = 0

    elif strategy == "slc":
        from core.strategy_slc import run_slc
        params.update(
            ema_length=args.ema_length, ema_slope_bars=args.ema_slope_bars,
            swing_window=args.swing_window, atr_period=args.atr_period,
            impulse_mult=args.impulse_mult, zone_buffer_atr=args.zone_buffer_atr,
        )
        signals = run_slc(df, **params)
        trail_act = trail_off = 0

    else:
        print(f"Unknown strategy: {strategy}")
        sys.exit(1)

    if signals.empty:
        print("Strategy produced no signals.")
        sys.exit(1)

    signal_count = len(signals[signals["signal"] != 0])
    print(f"Signals generated: {signal_count}\n")

    result = run_backtest(
        signals,
        initial_capital=args.capital,
        risk_percent=args.risk_percent,
        fee_rate=args.fee_rate,
        max_hold_bars=288 if strategy == "ny-range" else 0,
        trail_activation_atr=trail_act,
        trail_offset_atr=trail_off,
    )
    metrics = calculate_metrics(result)

    if "error" in metrics:
        print(f"Backtest error: {metrics['error']}")
        sys.exit(1)

    # ── Print results ──
    print("┌─────────────── Results ───────────────┐")
    print(f" Initial Capital:   ${metrics['initial_capital']:>10.2f}")
    print(f" Final Capital:     ${metrics['final_capital']:>10.2f}")
    print(f" Total Return:      {metrics['total_return_pct']:>+8.2f}%")
    print(f" CAGR:              {metrics['cagr_pct']:>+8.2f}%")
    print(f" Sharpe Ratio:      {metrics['sharpe_ratio']:>10.3f}")
    print(f" Sortino Ratio:     {metrics['sortino_ratio']:>10.3f}")
    print(f" Max Drawdown:      {metrics['max_drawdown_pct']:>8.2f}%")
    print(f" Calmar Ratio:      {metrics['calmar_ratio']:>10.3f}")
    print(f" Profit Factor:     {metrics['profit_factor']:>10.3f}")
    print(f"──────────────────────────────────────────")
    print(f" Total Trades:      {metrics['total_trades']:>10d}")
    print(f" Win Rate:          {metrics['win_rate_pct']:>8.2f}%")
    print(f" Expectancy:        ${metrics['expectancy']:>9.2f}")
    print(f" Avg PnL:           ${metrics['avg_pnl']:>9.2f}")
    print(f" Avg Win:           ${metrics['avg_win_pnl']:>9.2f}")
    print(f" Avg Loss:          ${metrics['avg_loss_pnl']:>9.2f}")
    print(f" Best Trade:        ${metrics['best_trade_pnl']:>9.2f}")
    print(f" Worst Trade:       ${metrics['worst_trade_pnl']:>9.2f}")
    print(f" Avg Duration:      {metrics['avg_duration']}")
    print(f"└────────────────────────────────────────┘")

    # Trade log
    if result.trades:
        print("\nTrade log:")
        print(f"  {'#':>3s} {'Side':>5s} {'Entry':>12s} {'Exit':>12s} {'PnL':>10s} {'Reason':>10s}")
        print(f"  {'-'*55}")
        for i, t in enumerate(result.trades, 1):
            side = "LONG" if t.side == 1 else "SHORT"
            et = t.entry_time.strftime("%m-%d %H:%M")
            xt = t.exit_time.strftime("%m-%d %H:%M") if t.exit_time else "—"
            pnl_s = f"${t.pnl:>+7.2f}" if t.pnl is not None else "—"
            print(f"  {i:>3d} {side:>5s} {et:>12s} {xt:>12s} {pnl_s:>10s} {t.exit_reason:>10s}")

    if "monthly_returns" in metrics and not metrics["monthly_returns"].empty:
        print("\nMonthly returns (%):")
        print(metrics["monthly_returns"].to_string())


if __name__ == "__main__":
    main()
