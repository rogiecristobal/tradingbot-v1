import importlib
from datetime import datetime, timedelta

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QLabel,
    QProgressBar, QGridLayout, QFrame, QLineEdit,
)
from PyQt6.QtCore import pyqtSignal, QObject, QThread, Qt

from state import AppState

POPULAR_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "DOT/USDT", "AVAX/USDT", "LINK/USDT",
    "MATIC/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "BCH/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT", "PEPE/USDT",
]

STRATEGIES = [
    "4H NY Range Re-Entry",
    "5M Trend Pullback",
    "ATR Trend-Breakout",
    "IBR (Institutional Breakout Retest)",
]


class BacktestWorker(QObject):
    progress = pyqtSignal(float, str)
    status = pyqtSignal(str)
    finished = pyqtSignal(object, object, object, str, str)
    error = pyqtSignal(str)

    def __init__(self, exchange_id, symbol, strategy_name, params, lookback_days, initial_capital):
        super().__init__()
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.params = params
        self.lookback_days = lookback_days
        self.initial_capital = initial_capital

    def run(self):
        try:
            from data.ohlcv import fetch_ohlcv
            from core.backtest_engine import run_backtest
            from core.metrics import calculate_metrics

            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

            # Use 4H data for the ATR breakout, 5M for everything else, 15M for IBR
            is_ny_range = self.strategy_name == "4H NY Range Re-Entry"
            is_atr = self.strategy_name == "ATR Trend-Breakout"
            is_ibr = self.strategy_name == "IBR (Institutional Breakout Retest)"
            if is_atr:
                tf, tf_label = "4h", "4-hour"
            elif is_ibr:
                tf, tf_label = "15m", "15-minute"
            else:
                tf, tf_label = "5m", "5-minute"

            self.status.emit(f"Fetching {self.symbol} {tf_label} data...")
            df_ohlcv = fetch_ohlcv(
                exchange_id=self.exchange_id,
                symbol=self.symbol,
                timeframe=tf,
                start_date=start_date,
                end_date=end_date,
                progress_callback=lambda f, t: self.progress.emit(f, t),
            )
            if df_ohlcv.empty:
                self.error.emit(f"No data for {self.symbol} on {self.exchange_id}")
                return
            self.status.emit(f"Retrieved {len(df_ohlcv):,} {tf_label} bars — running strategy...")

            params = self.params
            max_hold = 0
            if is_ny_range:
                from core.strategy import run_4h_ny_range_reentry
                self.status.emit(f"Fetching 4H data for NY range...")
                df_4h = fetch_ohlcv(
                    exchange_id=self.exchange_id,
                    symbol=self.symbol,
                    timeframe="4h",
                    start_date=start_date,
                    end_date=end_date,
                    progress_callback=lambda f, t: self.progress.emit(f, t),
                )
                if df_4h.empty:
                    self.error.emit(f"No 4H data for {self.symbol} on {self.exchange_id}")
                    return
                df_signals = run_4h_ny_range_reentry(
                    df_5m=df_ohlcv, df_4h=df_4h,
                    rr=params["rr"], risk_percent=params["risk_percent"]
                )
            elif self.strategy_name == "5M Trend Pullback":
                from core.strategy_trend_pullback import run_trend_pullback
                df_signals = run_trend_pullback(
                    df_ohlcv, rr=params["rr"], risk_percent=params["risk_percent"],
                    ema_length=params["ema_length"], rsi_length=params["rsi_length"],
                    rsi_buy=params["rsi_buy"], rsi_sell=params["rsi_sell"],
                    atr_period=params["atr_period"],
                )
            elif is_atr:
                from core.strategy_atr_breakout import run_atr_breakout
                df_signals = run_atr_breakout(
                    df_ohlcv,
                    risk_percent=params["risk_percent"],
                    ema_fast=params["ema_fast"],
                    ema_slow=params["ema_slow"],
                    donchian_period=params["donchian_period"],
                    atr_period=params["atr_period"],
                    volume_sma_period=params["volume_sma_period"],
                    volume_mult=params["volume_mult"],
                    atr_min_pct=params["atr_min_pct"],
                    atr_sl_mult=params["atr_sl_mult"],
                    rr=params["rr"],
                    trail_activation=params["trail_activation"],
                    trail_offset=params["trail_offset"],
                )
            elif is_ibr:
                from core.strategy_ibr import run_ibr
                df_signals = run_ibr(
                    df_ohlcv,
                    ema_length=params["ema_length"],
                    ema_slope_bars=params["ema_slope_bars"],
                    swing_window=params["swing_window"],
                    fib_min=params["fib_min"],
                    fib_max=params["fib_max"],
                    rr=params["rr"],
                    risk_percent=params["risk_percent"],
                    fee_rate=params.get("fee_rate", 0.001),
                )
            else:
                self.error.emit(f"Unknown strategy: {self.strategy_name}")
                return

            if df_signals.empty:
                self.error.emit("Strategy produced no results.")
                return

            signal_count = len(df_signals[df_signals["signal"] != 0])
            self.status.emit(f"Generated {signal_count} signals — running backtest...")

            fee_rate = params.get("fee_rate", 0.001)
            trail_act = params.get("trail_activation", 0.0)
            trail_off = params.get("trail_offset", 0.0)
            result = run_backtest(
                df_signals, initial_capital=self.initial_capital,
                risk_percent=params["risk_percent"], fee_rate=fee_rate,
                slippage=0.0, max_hold_bars=max_hold,
                trail_activation_atr=trail_act,
                trail_offset_atr=trail_off,
            )
            metrics = calculate_metrics(result)
            self.finished.emit(result, metrics, df_signals, self.symbol, self.exchange_id)

        except Exception as e:
            self.error.emit(str(e))


class BacktestPanel(QWidget):
    backtest_completed = pyqtSignal(object, object, object, str, str)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._thread = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        # ── Parameters ──
        params_box = QGroupBox("Parameters")
        params_layout = QGridLayout(params_box)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(STRATEGIES)
        params_layout.addWidget(QLabel("Strategy:"), 0, 0)
        params_layout.addWidget(self.strategy_combo, 0, 1)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(["Custom..."] + POPULAR_SYMBOLS)
        self.symbol_combo.setEditable(False)
        params_layout.addWidget(QLabel("Symbol:"), 0, 2)
        params_layout.addWidget(self.symbol_combo, 0, 3)

        self.custom_symbol_input = QLineEdit()
        self.custom_symbol_input.setPlaceholderText("e.g. ETH/USDT")
        self.custom_symbol_input.hide()
        params_layout.addWidget(self.custom_symbol_input, 0, 4)

        self.lookback_spin = QSpinBox()
        self.lookback_spin.setRange(7, 365)
        self.lookback_spin.setValue(90)
        self.lookback_spin.setSuffix(" days")
        params_layout.addWidget(QLabel("Lookback:"), 1, 0)
        params_layout.addWidget(self.lookback_spin, 1, 1)

        self.capital_spin = QDoubleSpinBox()
        self.capital_spin.setRange(1000, 10_000_000)
        self.capital_spin.setValue(10_000)
        self.capital_spin.setPrefix("$ ")
        self.capital_spin.setSingleStep(1000)
        params_layout.addWidget(QLabel("Capital:"), 1, 2)
        params_layout.addWidget(self.capital_spin, 1, 3)

        outer.addWidget(params_box)

        # ── Strategy-specific params ──
        self.strategy_params_box = QGroupBox("Strategy Parameters")
        self.strategy_params_layout = QFormLayout(self.strategy_params_box)
        outer.addWidget(self.strategy_params_box)
        self._strategy_param_widgets = {}

        # ── Run ──
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Backtest")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.clicked.connect(self._on_run)
        run_layout.addWidget(self.run_btn)
        outer.addLayout(run_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        outer.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        # ── Summary ──
        self.summary_box = QGroupBox("Quick Summary")
        self.summary_grid = QGridLayout(self.summary_box)
        self.summary_widgets = {}
        labels = [
            ("total_return", "Total Return"),
            ("final_capital", "Final Capital"),
            ("win_rate", "Win Rate"),
            ("profit_factor", "Profit Factor"),
            ("max_dd", "Max Drawdown"),
            ("extra", ""),
        ]
        for col, (key, text) in enumerate(labels):
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold; color: #888;")
            val = QLabel("—")
            val.setStyleSheet("font-size: 16px;")
            self.summary_grid.addWidget(lbl, 0, col)
            self.summary_grid.addWidget(val, 1, col)
            self.summary_widgets[key] = val
        self.summary_box.hide()
        outer.addWidget(self.summary_box)

        outer.addStretch()

        # ── Signals ──
        self.strategy_combo.currentTextChanged.connect(self._rebuild_strategy_params)
        self.symbol_combo.currentTextChanged.connect(self._on_symbol_changed)
        self.custom_symbol_input.textChanged.connect(self._on_custom_symbol)

        self._rebuild_strategy_params()

    def _on_symbol_changed(self, text):
        if text == "Custom...":
            self.custom_symbol_input.show()
        else:
            self.custom_symbol_input.hide()

    def _on_custom_symbol(self):
        pass

    def _clear_strategy_params(self):
        while self.strategy_params_layout.count():
            item = self.strategy_params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._strategy_param_widgets.clear()

    def _rebuild_strategy_params(self):
        self._clear_strategy_params()
        name = self.strategy_combo.currentText()

        if name == "4H NY Range Re-Entry":
            self._add_param("rr", "Risk:Reward", 2.0, 0.5, 10.0, 0.1)
            self._add_param("risk_percent", "Risk per trade (%)", 1.0, 0.1, 10.0, 0.1)
            self._add_param("fee_rate", "Fee rate (%)", self.state.fee_rate * 100, 0.0, 1.0, 0.01, 3)

        elif name == "5M Trend Pullback":
            self._add_param("ema_length", "EMA Length", 200, 20, 500, 1, is_int=True)
            self._add_param("rsi_length", "RSI Length", 14, 2, 50, 1, is_int=True)
            self._add_param("rsi_buy", "RSI Oversold (Buy)", 35, 10, 50, 1, is_int=True)
            self._add_param("rsi_sell", "RSI Overbought (Sell)", 65, 50, 90, 1, is_int=True)
            self._add_param("atr_period", "ATR Period", 14, 5, 50, 1, is_int=True)
            self._add_param("rr", "Risk:Reward", 2.0, 0.5, 10.0, 0.1)
            self._add_param("risk_percent", "Risk per trade (%)", 1.0, 0.1, 10.0, 0.1)
            self._add_param("fee_rate", "Fee rate (%)", self.state.fee_rate * 100, 0.0, 1.0, 0.01, 3)

        elif name == "ATR Trend-Breakout":
            self._add_param("ema_fast", "EMA Fast", 50, 10, 200, 1, is_int=True)
            self._add_param("ema_slow", "EMA Slow", 200, 50, 500, 1, is_int=True)
            self._add_param("donchian_period", "Donchian Period", 20, 5, 100, 1, is_int=True)
            self._add_param("atr_period", "ATR Period", 14, 5, 50, 1, is_int=True)
            self._add_param("volume_sma_period", "Volume SMA", 20, 5, 100, 1, is_int=True)
            self._add_param("volume_mult", "Volume Surge Min", 1.5, 1.0, 5.0, 0.1)
            self._add_param("atr_min_pct", "ATR Min % of Price", 2.0, 0.5, 5.0, 0.1)
            self._add_param("atr_sl_mult", "Initial SL (ATR)", 2.0, 1.0, 5.0, 0.1)
            self._add_param("rr", "Risk:Reward", 5.0, 0.5, 10.0, 0.1)
            self._add_param("trail_activation", "Trail Activation (ATR)", 2.0, 0.5, 5.0, 0.1)
            self._add_param("trail_offset", "Trail Offset (ATR)", 1.0, 0.5, 3.0, 0.1)
            self._add_param("risk_percent", "Risk per trade (%)", 3.0, 0.1, 10.0, 0.1)
            self._add_param("fee_rate", "Fee rate (%)", self.state.fee_rate * 100, 0.0, 1.0, 0.01, 3)

        elif name == "IBR (Institutional Breakout Retest)":
            self._add_param("ema_length", "EMA Length (4H)", 200, 50, 500, 1, is_int=True)
            self._add_param("ema_slope_bars", "EMA Slope Bars", 5, 2, 20, 1, is_int=True)
            self._add_param("swing_window", "Swing Window (1H)", 5, 2, 20, 1, is_int=True)
            self._add_param("fib_min", "Fib Retrace Min", 0.382, 0.236, 0.5, 0.01)
            self._add_param("fib_max", "Fib Retrace Max", 0.618, 0.5, 0.786, 0.01)
            self._add_param("rr", "Risk:Reward", 2.0, 1.0, 10.0, 0.1)
            self._add_param("risk_percent", "Risk per trade (%)", 1.0, 0.1, 10.0, 0.1)
            self._add_param("fee_rate", "Fee rate (%)", self.state.fee_rate * 100, 0.0, 1.0, 0.01, 3)

    def _add_param(self, key, label, default, min_val, max_val, step, decimals=None, is_int=False):
        if is_int:
            w = QSpinBox()
            w.setRange(int(min_val), int(max_val))
            w.setValue(int(default))
            w.setSingleStep(int(step))
        else:
            w = QDoubleSpinBox()
            w.setRange(min_val, max_val)
            w.setValue(default)
            w.setSingleStep(step)
            if decimals is not None:
                w.setDecimals(decimals)
            if "%" in label:
                w.setSuffix(" %")
        self.strategy_params_layout.addRow(f"{label}:", w)
        self._strategy_param_widgets[key] = w

    def _collect_params(self):
        params = {}
        for key, w in self._strategy_param_widgets.items():
            if isinstance(w, QSpinBox):
                params[key] = w.value()
            elif isinstance(w, QComboBox):
                params[key] = w.currentText()
            else:
                params[key] = w.value()
        return params

    def _on_run(self):
        try:
            if self._thread and self._thread.isRunning():
                return
        except RuntimeError:
            self._thread = None
            self._worker = None

        symbol = self.symbol_combo.currentText()
        if symbol == "Custom...":
            symbol = self.custom_symbol_input.text().strip().upper() or "BTC/USDT"

        self.summary_box.hide()
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_label.setText("Starting...")

        params = self._collect_params()
        if "fee_rate" in params:
            params["fee_rate"] = params["fee_rate"] / 100
        else:
            params["fee_rate"] = self.state.fee_rate

        self._thread = QThread()
        self._worker = BacktestWorker(
            exchange_id=self.state.exchange_id,
            symbol=symbol,
            strategy_name=self.strategy_combo.currentText(),
            params=params,
            lookback_days=self.lookback_spin.value(),
            initial_capital=self.capital_spin.value(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_progress(self, fraction, text):
        self.progress_bar.setValue(int(fraction * 100))
        self.status_label.setText(text)

    def _on_finished(self, result, metrics, signals, symbol, exchange):
        self.run_btn.setEnabled(True)
        self.progress_bar.hide()
        self.status_label.setText("Backtest complete!")

        # Update summary
        self.summary_box.show()
        is_error = "error" in metrics
        if not is_error:
            delta = result.total_return
            self.summary_widgets["total_return"].setText(
                f"${result.final_capital - result.initial_capital:,.2f} ({delta:+.2f}%)"
            )
            self.summary_widgets["total_return"].setStyleSheet(
                "font-size: 16px; color: #00FF88;" if delta >= 0 else "font-size: 16px; color: #FF4444;"
            )
            self.summary_widgets["final_capital"].setText(f"${result.final_capital:,.2f}")
            self.summary_widgets["win_rate"].setText(
                f"{metrics['win_rate_pct']:.1f}% ({metrics['winning_trades']}/{metrics['total_trades']})"
            )
            self.summary_widgets["profit_factor"].setText(f"{metrics['profit_factor']:.2f}")
            self.summary_widgets["max_dd"].setText(f"{metrics['max_drawdown_pct']:.2f}%")
        else:
            self.summary_widgets["total_return"].setText(metrics["error"])
            self.summary_widgets["total_return"].setStyleSheet("font-size: 16px; color: #FF4444;")

        self.backtest_completed.emit(result, metrics, signals, symbol, exchange)

    def _on_thread_finished(self):
        self._thread = None
        self._worker = None

    def _on_error(self, msg):
        self.run_btn.setEnabled(True)
        self.progress_bar.hide()
        self.status_label.setText(f"Error: {msg}")
        if self._thread:
            self._thread.quit()
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def refresh_state(self):
        pass
