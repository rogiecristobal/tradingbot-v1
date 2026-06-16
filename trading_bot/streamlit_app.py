import streamlit as st
st.set_page_config(page_title="Crypto Backtest", layout="wide")

from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.ohlcv import fetch_ohlcv
from dataclasses import dataclass
from core.backtest_engine import run_backtest, Trade, BacktestResult
from core.metrics import calculate_metrics

POPULAR_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "ADA/USDT", "DOGE/USDT", "DOT/USDT",
    "AVAX/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT",
    "LTC/USDT", "BCH/USDT", "APT/USDT", "ARB/USDT",
    "OP/USDT", "SUI/USDT",
]

STRATEGIES = {
    "ATR Trend-Breakout": {
        "tf": "4h", "module": "core.strategy_atr_breakout", "func": "run_atr_breakout",
        "params": {
            "ema_fast": {"label": "EMA Fast", "default": 50, "min": 10, "max": 200, "int": True},
            "ema_slow": {"label": "EMA Slow", "default": 200, "min": 50, "max": 500, "int": True},
            "donchian_period": {"label": "Donchian Period", "default": 20, "min": 5, "max": 100, "int": True},
            "atr_period": {"label": "ATR Period", "default": 14, "min": 5, "max": 50, "int": True},
            "volume_sma_period": {"label": "Volume SMA", "default": 20, "min": 5, "max": 100, "int": True},
            "volume_mult": {"label": "Volume Surge Min", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1},
            "atr_min_pct": {"label": "ATR Min % of Price", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
            "atr_sl_mult": {"label": "Initial SL (ATR)", "default": 2.0, "min": 1.0, "max": 5.0, "step": 0.1},
            "trail_activation": {"label": "Trail Activation (ATR)", "default": 2.0, "min": 0.5, "max": 5.0, "step": 0.1},
            "trail_offset": {"label": "Trail Offset (ATR)", "default": 1.0, "min": 0.5, "max": 3.0, "step": 0.1},
        },
        "has_trail": True,
    },
    "5M Trend Pullback": {
        "tf": "5m", "module": "core.strategy_trend_pullback", "func": "run_trend_pullback",
        "params": {
            "ema_length": {"label": "EMA Length", "default": 200, "min": 20, "max": 500, "int": True},
            "rsi_length": {"label": "RSI Length", "default": 14, "min": 2, "max": 50, "int": True},
            "rsi_buy": {"label": "RSI Oversold (Buy)", "default": 35, "min": 10, "max": 50, "int": True},
            "rsi_sell": {"label": "RSI Overbought (Sell)", "default": 65, "min": 50, "max": 90, "int": True},
            "atr_period": {"label": "ATR Period", "default": 14, "min": 5, "max": 50, "int": True},
        },
        "has_trail": False,
    },
    "4H NY Range Re-Entry": {
        "tf": "5m", "extra_tf": "4h", "module": "core.strategy", "func": "run_4h_ny_range_reentry",
        "params": {},
        "has_trail": False,
        "max_hold": 288,
    },
    "IBR (Institutional Breakout Retest)": {
        "tf": "15m", "module": "core.strategy_ibr", "func": "run_ibr",
        "params": {
            "ema_length": {"label": "EMA Length (4H)", "default": 200, "min": 50, "max": 500, "int": True},
            "ema_slope_bars": {"label": "EMA Slope Bars", "default": 5, "min": 2, "max": 20, "int": True},
            "swing_window": {"label": "Swing Window (1H)", "default": 5, "min": 2, "max": 20, "int": True},
            "fib_min": {"label": "Fib Retrace Min", "default": 0.382, "min": 0.236, "max": 0.5, "step": 0.01},
            "fib_max": {"label": "Fib Retrace Max", "default": 0.618, "min": 0.5, "max": 0.786, "step": 0.01},
        },
        "has_trail": False,
    },
    "SLC (Structure-Level-Confirmation)": {
        "tf": "15m", "module": "core.strategy_slc", "func": "run_slc",
        "params": {
            "ema_length": {"label": "EMA Length (4H)", "default": 200, "min": 50, "max": 500, "int": True},
            "ema_slope_bars": {"label": "EMA Slope Bars", "default": 5, "min": 2, "max": 20, "int": True},
            "swing_window": {"label": "Swing Window (15M)", "default": 5, "min": 2, "max": 20, "int": True},
            "atr_period": {"label": "ATR Period", "default": 14, "min": 5, "max": 50, "int": True},
            "impulse_mult": {"label": "Impulse ATR Multiplier", "default": 1.5, "min": 1.0, "max": 5.0, "step": 0.1},
            "zone_buffer_atr": {"label": "Zone Buffer (ATR)", "default": 0.3, "min": 0.1, "max": 1.0, "step": 0.1},
        },
        "has_trail": False,
    },
}


def _strategy_params_ui(spec):
    p = {}
    for key, cfg in spec["params"].items():
        if cfg.get("int", False):
            p[key] = st.number_input(cfg["label"], min_value=cfg["min"], max_value=cfg["max"],
                                      value=cfg["default"], step=1, key=key)
        else:
            p[key] = st.number_input(cfg["label"], min_value=cfg["min"], max_value=cfg["max"],
                                      value=cfg["default"], step=cfg.get("step", 0.1), format="%.2f", key=key)
    return p


def _plot_equity_curve(result):
    eq = result.equity_curve
    if eq.empty:
        return None
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3],
                        vertical_spacing=0.05)
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, mode="lines",
                             name="Equity", line=dict(color="#00ff88")), row=1, col=1)
    peak = eq.cummax()
    dd = (eq - peak) / peak * 100
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines",
                             name="Drawdown %", fill="tozeroy",
                             line=dict(color="#ff4444")), row=2, col=1)
    fig.update_layout(height=500, margin=dict(l=0, r=0, t=20, b=0),
                      template="plotly_dark", showlegend=False)
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="DD %", row=2, col=1)
    return fig


def _metric_card(label, value, color=None):
    css = f"color: {color};" if color else ""
    st.markdown(f"<div style='background:#1e1e1e;padding:10px;border-radius:6px;{css}'"
                f"<div style='font-size:12px;color:#888'>{label}</div>"
                f"<div style='font-size:22px;font-weight:700'>{value}</div></div>",
                unsafe_allow_html=True)


@dataclass
class _PortfolioTrade(Trade):
    symbol: str = ""
    entry_bar_idx: int = 0


def _portfolio_backtest(signal_dfs, capital, risk_pct, fee_rate, max_hold_bars,
                        trail_act, trail_off, max_concurrent=999):
    # Align all symbol DataFrames to the union of all timestamps
    all_ts = sorted(set.union(*(set(df.index) for df in signal_dfs.values())))
    reindexed = {}
    for sym, df in signal_dfs.items():
        ohlc = df[["open", "high", "low", "close"]].reindex(all_ts).ffill()
        extra = pd.DataFrame(index=all_ts)
        for col in ["signal", "entry_price", "sl_price", "tp_price", "atr"]:
            if col in df.columns:
                extra[col] = df[col].reindex(all_ts)
        merged = pd.concat([ohlc, extra], axis=1)
        merged["signal"] = merged["signal"].fillna(0).astype(int)
        reindexed[sym] = merged

    pool = float(capital)
    positions = {}
    all_trades = []
    equity_curve = []

    for i in range(len(all_ts)):
        t = all_ts[i]

        # ── Check SL/TP for all open positions ──
        for sym in list(positions.keys()):
            pos = positions[sym]
            bar = reindexed[sym].iloc[i]
            low, high, close = bar["low"], bar["high"], bar["close"]

            is_long = pos.side == 1
            sl, tp = pos.sl_price, pos.tp_price
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
                bars_in = i - pos.entry_bar_idx + 1
                if bars_in >= max_hold_bars:
                    exit_price = close
                    exit_reason = "max_hold"

            if exit_price is None and pos.atr_at_entry > 0 and trail_act > 0:
                atr_val = pos.atr_at_entry
                if is_long:
                    if high > pos.highest_price:
                        pos.highest_price = high
                    if not pos.trail_activated:
                        if high - pos.entry_price >= trail_act * atr_val:
                            pos.trail_activated = True
                    if pos.trail_activated:
                        new_sl = pos.highest_price - trail_off * atr_val
                        if new_sl > pos.sl_price:
                            pos.sl_price = new_sl
                            sl = new_sl
                            if low <= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"
                else:
                    if low < pos.lowest_price:
                        pos.lowest_price = low
                    if not pos.trail_activated:
                        if pos.entry_price - low >= trail_act * atr_val:
                            pos.trail_activated = True
                    if pos.trail_activated:
                        new_sl = pos.lowest_price + trail_off * atr_val
                        if new_sl < pos.sl_price:
                            pos.sl_price = new_sl
                            sl = new_sl
                            if high >= new_sl:
                                exit_price = new_sl
                                exit_reason = "trail"

            if exit_price is not None:
                pos.exit_time = t
                pos.exit_price = exit_price
                pnl = (exit_price - pos.entry_price) * pos.quantity * pos.side
                pnl -= pos.entry_price * pos.quantity * fee_rate
                pnl -= exit_price * pos.quantity * fee_rate
                pos.pnl = pnl
                pos.pnl_pct = (pnl / (pos.entry_price * pos.quantity) * 100) if pos.quantity > 0 else 0
                pos.duration = t - pos.entry_time
                pos.exit_reason = exit_reason
                all_trades.append(pos)
                pool += pnl
                del positions[sym]

        # ── Compute current portfolio equity (including unrealized P&L) ──
        current_eq = pool + sum(
            (reindexed[sym].iloc[i]["close"] - pos.entry_price) * pos.quantity * pos.side
            for sym, pos in positions.items()
        )

        # ── Enter new trades from previous bar ──
        if i > 0 and len(positions) < max_concurrent:
            for sym in reindexed:
                if sym in positions:
                    continue
                prev = reindexed[sym].iloc[i - 1]
                if prev["signal"] != 0 and not pd.isna(prev["entry_price"]) and not pd.isna(prev["sl_price"]):
                    curr = reindexed[sym].iloc[i]
                    entry_price = curr["open"]
                    diff = entry_price - prev["entry_price"]
                    sl = prev["sl_price"] + diff
                    tp = prev["tp_price"] + diff
                    risk_per_unit = abs(entry_price - sl)
                    if risk_per_unit > 0 and current_eq > 0:
                        risk_amount = current_eq * (risk_pct / 100.0)
                        quantity = risk_amount / risk_per_unit
                    else:
                        quantity = 0

                    pos = _PortfolioTrade(
                        symbol=sym,
                        entry_time=t,
                        exit_time=None,
                        side=int(prev["signal"]),
                        entry_price=entry_price,
                        exit_price=None,
                        quantity=quantity,
                        sl_price=sl,
                        tp_price=tp,
                        exit_reason="",
                        entry_bar_idx=i,
                    )
                    if "atr" in reindexed[sym].columns:
                        atr_val = reindexed[sym].iloc[i - 1]["atr"]
                        if not pd.isna(atr_val):
                            pos.atr_at_entry = atr_val
                            pos.highest_price = entry_price
                            pos.lowest_price = entry_price
                    positions[sym] = pos

        # ── Record equity ──
        unrealized = sum(
            (reindexed[sym].iloc[i]["close"] - pos.entry_price) * pos.quantity * pos.side
            for sym, pos in positions.items()
        )
        equity_curve.append({"time": t, "equity": pool + unrealized})

    # ── Force-close remaining positions ──
    for sym, pos in list(positions.items()):
        last_idx = all_ts[-1]
        last_bar = reindexed[sym].iloc[-1]
        close_price = last_bar["close"]
        pnl = (close_price - pos.entry_price) * pos.quantity * pos.side
        pnl -= pos.entry_price * pos.quantity * fee_rate
        pnl -= close_price * pos.quantity * fee_rate
        pos.exit_time = last_idx
        pos.exit_price = close_price
        pos.pnl = pnl
        pos.pnl_pct = (pnl / (pos.entry_price * pos.quantity) * 100) if pos.quantity > 0 else 0
        pos.duration = last_idx - pos.entry_time
        pos.exit_reason = "end_of_data"
        all_trades.append(pos)
        pool += pnl

    eq_df = pd.DataFrame(equity_curve)
    eq_series = (
        pd.Series(eq_df["equity"].values, index=pd.to_datetime(eq_df["time"]))
        if not eq_df.empty
        else pd.Series(dtype=float)
    )

    # ── Per-symbol stats ──
    per_symbol = {}
    for sym in signal_dfs:
        sym_trades = [t for t in all_trades if t.symbol == sym and t.pnl is not None]
        if not sym_trades:
            continue
        wins = [t for t in sym_trades if t.pnl > 0]
        gross_pnl = sum(t.pnl for t in sym_trades)
        per_symbol[sym] = {
            "trades": len(sym_trades),
            "gross_pnl": gross_pnl,
            "win_rate": len(wins) / len(sym_trades) * 100 if sym_trades else 0,
            "avg_pnl": gross_pnl / len(sym_trades) if sym_trades else 0,
        }

    result = BacktestResult(
        trades=all_trades,
        equity_curve=eq_series,
        initial_capital=float(capital),
        final_capital=pool,
        total_return=((pool - float(capital)) / float(capital)) * 100,
    )
    return result, per_symbol


def _render_single_result(result, metrics):
    delta = result.total_return
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        _metric_card("Total Return", f"{delta:+.2f}%",
                     "#00ff88" if delta >= 0 else "#ff4444")
    with col2:
        _metric_card("Final Capital", f"${result.final_capital:,.2f}")
    with col3:
        _metric_card("Win Rate",
                     f"{metrics['win_rate_pct']:.1f}% ({metrics['winning_trades']}/{metrics['total_trades']})")
    with col4:
        _metric_card("Profit Factor", f"{metrics['profit_factor']:.2f}")
    with col5:
        _metric_card("Max Drawdown", f"{metrics['max_drawdown_pct']:.2f}%", "#ff4444")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        _metric_card("Sharpe", f"{metrics['sharpe_ratio']:.3f}")
    with col2:
        _metric_card("Sortino", f"{metrics['sortino_ratio']:.3f}")
    with col3:
        _metric_card("CAGR", f"{metrics['cagr_pct']:+.2f}%",
                     "#00ff88" if metrics['cagr_pct'] >= 0 else "#ff4444")
    with col4:
        _metric_card("Calmar", f"{metrics['calmar_ratio']:.3f}")
    with col5:
        _metric_card("Expectancy", f"${metrics['expectancy']:+.2f}")

    fig = _plot_equity_curve(result)
    if fig:
        st.plotly_chart(fig, width="stretch")

    # Trade log
    if result.trades:
        with st.expander("Trade Log", expanded=False):
            rows = []
            for t in result.trades:
                rows.append({
                    "Side": "LONG" if t.side == 1 else "SHORT",
                    "Entry": t.entry_time.strftime("%m-%d %H:%M"),
                    "Exit": t.exit_time.strftime("%m-%d %H:%M") if t.exit_time else "—",
                    "Entry $": f"{t.entry_price:.2f}",
                    "Exit $": f"{t.exit_price:.2f}" if t.exit_price else "—",
                    "PnL": f"${t.pnl:+.2f}" if t.pnl is not None else "—",
                    "Reason": t.exit_reason,
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # Monthly returns
    if "monthly_returns" in metrics and not metrics["monthly_returns"].empty:
        with st.expander("Monthly Returns", expanded=False):
            mr = metrics["monthly_returns"].copy()
            mr["color"] = mr["return_pct"].apply(
                lambda v: "#00ff88" if v >= 0 else "#ff4444"
            )
            fig_m = go.Figure()
            fig_m.add_trace(go.Bar(
                x=mr.index, y=mr["return_pct"],
                marker_color=mr["color"],
            ))
            fig_m.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                                template="plotly_dark",
                                xaxis_title="", yaxis_title="Return %")
            st.plotly_chart(fig_m, width="stretch")

    # Detailed stats
    with st.expander("Detailed Statistics", expanded=False):
        detail_keys = [
            ("Total Trades", metrics["total_trades"]),
            ("Winning Trades", metrics["winning_trades"]),
            ("Losing Trades", metrics["losing_trades"]),
            ("Gross Profit", f"${metrics['gross_profit']:.2f}"),
            ("Gross Loss", f"${metrics['gross_loss']:.2f}"),
            ("Avg PnL", f"${metrics['avg_pnl']:.2f}"),
            ("Median PnL", f"${metrics['median_pnl']:.2f}"),
            ("Std PnL", f"${metrics['std_pnl']:.2f}"),
            ("Best Trade", f"${metrics['best_trade_pnl']:.2f}"),
            ("Worst Trade", f"${metrics['worst_trade_pnl']:.2f}"),
            ("Avg Win", f"${metrics['avg_win_pnl']:.2f}"),
            ("Avg Loss", f"${metrics['avg_loss_pnl']:.2f}"),
            ("Avg Duration", metrics["avg_duration"]),
            ("Avg Win Duration", metrics["avg_win_duration"]),
            ("Avg Loss Duration", metrics["avg_loss_duration"]),
            ("Max Drawdown Duration", f"{metrics['max_drawdown_duration']} bars"),
            ("Recovery Factor", f"{metrics['recovery_factor']:.2f}"),
        ]
        cols = st.columns(3)
        for i, (label, value) in enumerate(detail_keys):
            cols[i % 3].metric(label, value)


def main():
    st.title("Crypto Trading Bot — Backtest")

    with st.sidebar:
        st.header("Settings")
        exchange = st.text_input("Exchange", value="bybit")
        compare_mode = st.checkbox("Compare Multiple Symbols", value=False)
        if compare_mode:
            selected_symbols = st.multiselect("Symbols", POPULAR_SYMBOLS, default=POPULAR_SYMBOLS)
            max_concurrent = st.slider("Max Concurrent Trades", min_value=1, max_value=len(POPULAR_SYMBOLS), value=len(POPULAR_SYMBOLS))
            symbol = selected_symbols[0] if selected_symbols else ""
        else:
            symbol_idx = st.selectbox("Symbol", ["BTC/USDT"] + [s for s in POPULAR_SYMBOLS if s != "BTC/USDT"] + ["Custom..."], index=0)
            custom_symbol = ""
            if symbol_idx == "Custom...":
                custom_symbol = st.text_input("Custom Symbol", value="", placeholder="e.g. FTM/USDT")
            symbol = custom_symbol if symbol_idx == "Custom..." else symbol_idx
            selected_symbols = [symbol]
        lookback = st.number_input("Lookback (days)", min_value=7, max_value=365, value=90, step=1)
        capital = st.number_input("Initial Capital ($)", min_value=100, max_value=10_000_000,
                                   value=10_000, step=1000, format="%d")
        rr = st.number_input("Risk:Reward", min_value=0.5, max_value=10.0, value=5.0, step=0.1)
        risk_pct = st.number_input("Risk per Trade (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
        fee = st.number_input("Fee Rate (%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01, format="%.2f")

        st.divider()
        strategy_name = st.selectbox("Strategy", list(STRATEGIES.keys()))
        spec = STRATEGIES[strategy_name]
        st.caption(f"Timeframe: {spec['tf']}")
        strat_params = _strategy_params_ui(spec)
        run_label = f"Run Comparison ({len(selected_symbols)} symbols)" if compare_mode else "Run Backtest"
        run = st.button(run_label, type="primary", width="stretch")

    if not run:
        st.info("Configure settings in the sidebar and click **Run Backtest**.")
        return

    strat_params.update(rr=rr, risk_percent=risk_pct, fee_rate=fee / 100)
    strategy_fn_name = spec["func"]
    module_path = spec["module"]
    tf = spec["tf"]
    max_hold = spec.get("max_hold", 0)
    has_trail = spec.get("has_trail", False)
    trail_act = strat_params.pop("trail_activation", 0) if has_trail else 0
    trail_off = strat_params.pop("trail_offset", 0) if has_trail else 0

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback)).strftime("%Y-%m-%d")

    try:
        import importlib
        mod = importlib.import_module(module_path)
        strategy_fn = getattr(mod, strategy_fn_name)
    except Exception as e:
        st.error(f"Failed to load strategy: {e}")
        return

    if compare_mode:
        if not selected_symbols:
            st.error("Select at least one symbol.")
            return

        signal_dfs = {}
        total = len(selected_symbols)
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, sym in enumerate(selected_symbols):
            status_text.info(f"[{i+1}/{total}] Fetching {sym} {tf} data...")
            df = fetch_ohlcv(
                exchange, sym, tf, start_date, end_date,
                progress_callback=lambda f, t: None,
            )
            if df.empty:
                st.warning(f"⚠️ {sym}: no data — skipping")
                progress_bar.progress((i + 1) / total)
                continue

            if "extra_tf" in spec:
                status_text.info(f"[{i+1}/{total}] Fetching {spec['extra_tf']} for {sym}...")
                df_extra = fetch_ohlcv(
                    exchange, sym, spec["extra_tf"], start_date, end_date,
                    progress_callback=lambda f, t: None,
                )
                if df_extra.empty:
                    st.warning(f"⚠️ {sym}: no {spec['extra_tf']} data — skipping")
                    progress_bar.progress((i + 1) / total)
                    continue
                df_signals = strategy_fn(df, df_extra, rr=rr, risk_percent=risk_pct)
            else:
                df_signals = strategy_fn(df, **strat_params)

            if df_signals.empty:
                st.warning(f"⚠️ {sym}: no signals — skipping")
                progress_bar.progress((i + 1) / total)
                continue

            signal_dfs[sym] = df_signals
            progress_bar.progress((i + 1) / total)

        progress_bar.empty()
        status_text.empty()

        if not signal_dfs:
            st.error("No symbols produced valid signals.")
            return

        result, per_symbol = _portfolio_backtest(
            signal_dfs, capital=capital, risk_pct=risk_pct,
            fee_rate=fee / 100, max_hold_bars=max_hold,
            trail_act=trail_act, trail_off=trail_off,
            max_concurrent=max_concurrent,
        )
        metrics = calculate_metrics(result)

        if "error" in metrics:
            st.error(metrics["error"])
            return

        # ── Portfolio Summary ──
        st.subheader("Portfolio Summary")
        delta = result.total_return
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            _metric_card("Portfolio Return", f"{delta:+.2f}%",
                         "#00ff88" if delta >= 0 else "#ff4444")
        with col2:
            _metric_card("Final Value", f"${result.final_capital:,.2f}")
        with col3:
            _metric_card("Win Rate",
                         f"{metrics['win_rate_pct']:.1f}% ({metrics['winning_trades']}/{metrics['total_trades']})")
        with col4:
            _metric_card("Profit Factor", f"{metrics['profit_factor']:.2f}")
        with col5:
            _metric_card("Max Drawdown", f"{metrics['max_drawdown_pct']:.2f}%", "#ff4444")

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            _metric_card("Sharpe", f"{metrics['sharpe_ratio']:.3f}")
        with col2:
            _metric_card("Sortino", f"{metrics['sortino_ratio']:.3f}")
        with col3:
            _metric_card("CAGR", f"{metrics['cagr_pct']:+.2f}%",
                         "#00ff88" if metrics['cagr_pct'] >= 0 else "#ff4444")
        with col4:
            _metric_card("Calmar", f"{metrics['calmar_ratio']:.3f}")
        with col5:
            _metric_card("Expectancy", f"${metrics['expectancy']:+.2f}")

        # ── Combined equity curve ──
        fig = _plot_equity_curve(result)
        if fig:
            fig.update_layout(title="Portfolio Equity Curve")
            st.plotly_chart(fig, width="stretch")

        # ── Per-symbol breakdown ──
        st.subheader("Per-Symbol Breakdown")
        sym_rows = []
        for sym, ps in sorted(per_symbol.items(), key=lambda x: x[1]["gross_pnl"], reverse=True):
            sym_rows.append({
                "Symbol": sym,
                "Trades": ps["trades"],
                "Gross P&L": f"${ps['gross_pnl']:+.2f}",
                "Win Rate": f"{ps['win_rate']:.1f}%",
                "Avg P&L": f"${ps['avg_pnl']:+.2f}",
            })
        if sym_rows:
            st.dataframe(pd.DataFrame(sym_rows), width="stretch", hide_index=True)

        # ── Trade log ──
        if result.trades:
            with st.expander("Trade Log", expanded=False):
                rows = []
                for t in result.trades:
                    rows.append({
                        "Symbol": t.symbol,
                        "Side": "LONG" if t.side == 1 else "SHORT",
                        "Entry": t.entry_time.strftime("%m-%d %H:%M"),
                        "Exit": t.exit_time.strftime("%m-%d %H:%M") if t.exit_time else "—",
                        "Entry $": f"{t.entry_price:.2f}",
                        "Exit $": f"{t.exit_price:.2f}" if t.exit_price else "—",
                        "PnL": f"${t.pnl:+.2f}" if t.pnl is not None else "—",
                        "Reason": t.exit_reason,
                    })
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        # Monthly returns
        if "monthly_returns" in metrics and not metrics["monthly_returns"].empty:
            with st.expander("Monthly Returns", expanded=False):
                mr = metrics["monthly_returns"].copy()
                mr["color"] = mr["return_pct"].apply(
                    lambda v: "#00ff88" if v >= 0 else "#ff4444"
                )
                fig_m = go.Figure()
                fig_m.add_trace(go.Bar(
                    x=mr.index, y=mr["return_pct"],
                    marker_color=mr["color"],
                ))
                fig_m.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                                    template="plotly_dark",
                                    xaxis_title="", yaxis_title="Return %")
                st.plotly_chart(fig_m, width="stretch")

        # ── Detailed stats ──
        with st.expander("Detailed Statistics", expanded=False):
            detail_keys = [
                ("Total Trades", metrics["total_trades"]),
                ("Winning Trades", metrics["winning_trades"]),
                ("Losing Trades", metrics["losing_trades"]),
                ("Gross Profit", f"${metrics['gross_profit']:.2f}"),
                ("Gross Loss", f"${metrics['gross_loss']:.2f}"),
                ("Avg PnL", f"${metrics['avg_pnl']:.2f}"),
                ("Best Trade", f"${metrics['best_trade_pnl']:.2f}"),
                ("Worst Trade", f"${metrics['worst_trade_pnl']:.2f}"),
                ("Avg Win", f"${metrics['avg_win_pnl']:.2f}"),
                ("Avg Loss", f"${metrics['avg_loss_pnl']:.2f}"),
                ("Avg Duration", metrics["avg_duration"]),
                ("Max Drawdown Duration", f"{metrics['max_drawdown_duration']} bars"),
                ("Recovery Factor", f"{metrics['recovery_factor']:.2f}"),
            ]
            cols = st.columns(3)
            for i, (label, value) in enumerate(detail_keys):
                cols[i % 3].metric(label, value)

    else:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()

        def prog(f, t):
            progress_bar.progress(f)
            progress_text.text(t)

        status_text.info(f"Fetching {symbol} {tf} data...")
        df = fetch_ohlcv(exchange, symbol, tf, start_date, end_date, progress_callback=prog)
        if df.empty:
            st.error("No data fetched.")
            return

        if "extra_tf" in spec:
            status_text.info(f"Fetching {spec['extra_tf']} data for range calculation...")
            df_extra = fetch_ohlcv(exchange, symbol, spec["extra_tf"], start_date, end_date, progress_callback=prog)
            if df_extra.empty:
                st.error("No extra timeframe data.")
                return
            df_signals = strategy_fn(df, df_extra, rr=rr, risk_percent=risk_pct)
        else:
            df_signals = strategy_fn(df, **strat_params)

        if df_signals.empty:
            st.error("Strategy produced no signals.")
            return

        sig_count = len(df_signals[df_signals["signal"] != 0])
        status_text.success(f"Generated {sig_count} signals — running backtest...")

        result = run_backtest(
            df_signals, initial_capital=capital,
            risk_percent=risk_pct, fee_rate=fee / 100,
            max_hold_bars=max_hold,
            trail_activation_atr=trail_act,
            trail_offset_atr=trail_off,
        )
        metrics = calculate_metrics(result)

        if "error" in metrics:
            st.error(metrics["error"])
            return

        progress_bar.empty()
        progress_text.empty()
        status_text.empty()

        # ── Results ──
        st.subheader("Results")
        _render_single_result(result, metrics)


if __name__ == "__main__":
    main()
