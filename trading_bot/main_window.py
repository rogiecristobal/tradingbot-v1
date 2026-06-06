from PyQt6.QtWidgets import QMainWindow, QTabWidget, QPushButton, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt
from state import AppState
from widgets.settings_panel import SettingsPanel
from widgets.backtest_panel import BacktestPanel
from widgets.statistics_panel import StatisticsPanel
from widgets.charts_panel import ChartsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        self.setWindowTitle("Crypto Trading Bot")
        self.resize(1400, 900)

        self.tabs = QTabWidget()

        self.backtest_panel = BacktestPanel(self.state, self)
        self.statistics_panel = StatisticsPanel(self.state, self)
        self.charts_panel = ChartsPanel(self.state, self)
        self.settings_panel = SettingsPanel(self.state, self)

        self.tabs.addTab(self.backtest_panel, "Backtest")
        self.tabs.addTab(self.statistics_panel, "Statistics")
        self.tabs.addTab(self.charts_panel, "Charts")
        self.tabs.addTab(self.settings_panel, "Settings")

        self.backtest_panel.backtest_completed.connect(self._on_backtest_completed)
        self.settings_panel.state_changed.connect(self._on_settings_changed)

        self.setCentralWidget(self.tabs)

        self.statusBar().showMessage("Ready")

    def _on_backtest_completed(self, result, metrics, signals, symbol, exchange):
        self.state.backtest_result = result
        self.state.backtest_metrics = metrics
        self.state.backtest_signals = signals
        self.state.backtest_symbol = symbol
        self.state.backtest_exchange = exchange
        self.statistics_panel.refresh()
        self.charts_panel.refresh()
        n_trades = len(result.trades) if result.trades else 0
        self.statusBar().showMessage(
            f"Backtest complete — {exchange}:{symbol} | {n_trades} trades | "
            f"Return: {metrics.get('total_return_pct', 0):+.2f}%"
        )

    def _on_settings_changed(self):
        self.backtest_panel.refresh_state()
