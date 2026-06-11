import argparse
import sys
from datetime import datetime, timedelta

from data.ohlcv import fetch_ohlcv
from core.backtest_engine import run_backtest
from core.metrics import calculate_metrics

POPULAR_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
    "AVAX/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT",
    "LTC/USDT", "BCH/USDT", "APT/USDT", "ARB/USDT",
    "OP/USDT", "SUI/USDT",
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Crypto Trading Bot — CLI Backtest",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--exchange", default="bybit", help="Exchange ID (ccxt)")
    p.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    p.add_argument("--all-symbols", action="store_true", help="Run on all popular symbols")
    p.add_argument("--symbols", help="Comma-separated symbols (overrides --symbol)")
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

    if args.all_symbols:
        symbols = POPULAR_SYMBOLS
    elif args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    else:
        symbols = [args.symbol]

    multi = len(symbols) > 1

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

    if not multi:
        print(f"┌──────────────────────────────────────────────┐")
        print(f"│  Backtest CLI                                │")
        print(f"│  Exchange: {args.exchange:<28s} │")
        print(f"│  Symbol:   {symbols[0]:<28s} │")
        print(f"│  Strategy: {strategy:<28s} │")
        print(f"│  Timeframe: {tf:<27s} │")
        print(f"│  Period:   {start_date} → {end_date}        │")
        print(f"│  Capital:  ${args.capital:>8.2f}                │")
        print(f"└──────────────────────────────────────────────┘")

    # Load strategy once
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
        strategy_fn = run_atr_breakout
        trail_act = args.trail_activation
        trail_off = args.trail_offset

    elif strategy == "trend-pullback":
        from core.strategy_trend_pullback import run_trend_pullback
        params.update(
            ema_length=args.ema_length, rsi_length=args.rsi_length,
            rsi_buy=args.rsi_buy, rsi_sell=args.rsi_sell,
            atr_period=args.atr_period if hasattr(args, 'atr_period') else 14,
        )
        strategy_fn = run_trend_pullback
        trail_act = trail_off = 0

    elif strategy == "ny-range":
        from core.strategy import run_4h_ny_range_reentry
        strategy_fn = run_4h_ny_range_reentry
        trail_act = trail_off = 0

    elif strategy == "ibr":
        from core.strategy_ibr import run_ibr
        params.update(
            ema_length=args.ema_length, ema_slope_bars=args.ema_slope_bars,
            swing_window=args.swing_window, fib_min=args.fib_min,
            fib_max=args.fib_max,
        )
        strategy_fn = run_ibr
        trail_act = trail_off = 0

    elif strategy == "slc":
        from core.strategy_slc import run_slc
        params.update(
            ema_length=args.ema_length, ema_slope_bars=args.ema_slope_bars,
            swing_window=args.swing_window, atr_period=args.atr_period,
            impulse_mult=args.impulse_mult, zone_buffer_atr=args.zone_buffer_atr,
        )
        strategy_fn = run_slc
        trail_act = trail_off = 0

    else:
        print(f"Unknown strategy: {strategy}")
        sys.exit(1)

    def run_one(sym):
        out = None
        print(f"  {sym} ...", end="", flush=True)
        df = fetch_ohlcv(
            exchange_id=args.exchange,
            symbol=sym,
            timeframe=tf,
            start_date=start_date,
            end_date=end_date,
            use_cache=True,
        )
        if df.empty:
            print(" no data  ✗")
            return None

        if strategy == "ny-range":
            df_4h = fetch_ohlcv(
                exchange_id=args.exchange, symbol=sym,
                timeframe="4h", start_date=start_date, end_date=end_date,
                use_cache=True,
            )
            if df_4h.empty:
                print(" no 4H data  ✗")
                return None
            signals = strategy_fn(df, df_4h, rr=args.rr, risk_percent=args.risk_percent)
        else:
            signals = strategy_fn(df, **params)

        if signals.empty:
            print(" no signals  ✗")
            return None

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
            print(f" {metrics['error']}  ✗")
            return None

        print(f" {metrics['total_trades']:>3d} trades, {metrics['total_return_pct']:>+7.2f}%  ✓")
        return {"symbol": sym, "metrics": metrics, "result": result}

    if multi:
        print(f"Backtesting {len(symbols)} symbols on {args.exchange} ({tf}, {strategy})\n")
        all_results = []
        for sym in symbols:
            r = run_one(sym)
            if r is not None:
                all_results.append(r)

        if not all_results:
            print("\nNo symbols produced valid results.")
            sys.exit(1)

        # ── Comparison table ──
        print("\n┌" + "─" * 105 + "┐")
        print(f"│ {'Symbol':<14s} {'Return %':>8s} {'CAGR %':>7s} {'Sharpe':>7s} "
              f"{'Max DD %':>8s} {'Win Rate':>8s} {'PF':>6s} {'Trades':>6s} │")
        print("├" + "─" * 105 + "┤")
        for r in sorted(all_results, key=lambda x: x["metrics"]["total_return_pct"], reverse=True):
            m = r["metrics"]
            print(f"│ {r['symbol']:<14s} {m['total_return_pct']:>+7.2f}% {m['cagr_pct']:>+6.2f}% "
                  f"{m['sharpe_ratio']:>7.3f} {m['max_drawdown_pct']:>7.2f}% "
                  f"{m['win_rate_pct']:>6.1f}% {m['profit_factor']:>6.2f} {m['total_trades']:>6d} │")
        print("└" + "─" * 105 + "┘")

    else:
        sym = symbols[0]
        print(f"\nFetching {sym} {tf} data...")
        result_data = run_one(sym)
        if result_data is None:
            sys.exit(1)

        metrics = result_data["metrics"]
        result = result_data["result"]

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
