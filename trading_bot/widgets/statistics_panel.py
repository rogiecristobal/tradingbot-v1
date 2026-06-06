import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QFileDialog, QHBoxLayout, QLabel,
    QGroupBox, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from state import AppState


class StatisticsPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Metrics tables grouped ──
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_performance_tab(), "Performance")
        self.tabs.addTab(self._build_trade_stats_tab(), "Trade Stats")
        self.tabs.addTab(self._build_pnl_tab(), "P&L Stats")
        self.tabs.addTab(self._build_durations_tab(), "Durations")
        layout.addWidget(self.tabs)

        # ── Monthly returns ──
        self.monthly_group = QGroupBox("Monthly Returns")
        self.monthly_table = QTableWidget()
        self.monthly_layout_inner = QVBoxLayout(self.monthly_group)
        self.monthly_layout_inner.addWidget(self.monthly_table)
        layout.addWidget(self.monthly_group)

        # ── Trade log ──
        self.trade_group = QGroupBox("Trade Log")
        trade_layout = QVBoxLayout(self.trade_group)

        btn_row = QHBoxLayout()
        self.csv_btn = QPushButton("Download Trade Log (CSV)")
        self.csv_btn.clicked.connect(self._export_csv)
        btn_row.addStretch()
        btn_row.addWidget(self.csv_btn)
        trade_layout.addLayout(btn_row)

        self.trade_table = QTableWidget()
        self.trade_table.setAlternatingRowColors(True)
        trade_layout.addWidget(self.trade_table)
        layout.addWidget(self.trade_group)

    def _make_table(self, data_dict):
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.setRowCount(len(data_dict))
        for i, (k, v) in enumerate(data_dict.items()):
            table.setItem(i, 0, QTableWidgetItem(str(k)))
            table.setItem(i, 1, QTableWidgetItem(str(v)))
            table.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.item(i, 1).setFlags(Qt.ItemFlag.ItemIsEnabled)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        return table

    def _build_performance_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.perf_table = QTableWidget()
        layout.addWidget(self.perf_table)
        return w

    def _build_trade_stats_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.trade_stats_table = QTableWidget()
        layout.addWidget(self.trade_stats_table)
        return w

    def _build_pnl_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.pnl_table = QTableWidget()
        layout.addWidget(self.pnl_table)
        return w

    def _build_durations_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        self.duration_table = QTableWidget()
        layout.addWidget(self.duration_table)
        return w

    def _fill_table(self, table, data_dict):
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.setRowCount(len(data_dict))
        for i, (k, v) in enumerate(data_dict.items()):
            table.setItem(i, 0, QTableWidgetItem(str(k)))
            item = QTableWidgetItem(str(v))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 1, item)
            table.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.item(i, 1).setFlags(Qt.ItemFlag.ItemIsEnabled)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()

    def refresh(self):
        m = self.state.backtest_metrics
        r = self.state.backtest_result
        if not m or "error" in m:
            return

        self._fill_table(self.perf_table, {
            "Total Return": f"{m['total_return_pct']:.2f}%",
            "CAGR": f"{m['cagr_pct']:.2f}%",
            "Sharpe Ratio": f"{m['sharpe_ratio']:.3f}",
            "Sortino Ratio": f"{m['sortino_ratio']:.3f}",
            "Calmar Ratio": f"{m['calmar_ratio']:.3f}",
            "Recovery Factor": f"{m['recovery_factor']:.2f}",
            "Max Drawdown": f"{m['max_drawdown_pct']:.2f}%",
            "Max Drawdown Duration": f"{m['max_drawdown_duration']} bars",
        })

        self._fill_table(self.trade_stats_table, {
            "Total Trades": f"{m['total_trades']}",
            "Winning Trades": f"{m['winning_trades']}",
            "Losing Trades": f"{m['losing_trades']}",
            "Win Rate": f"{m['win_rate_pct']:.2f}%",
            "Profit Factor": f"{m['profit_factor']:.3f}",
            "Expectancy": f"${m['expectancy']:.2f}",
            "Gross Profit": f"${m['gross_profit']:,.2f}",
            "Gross Loss": f"${m['gross_loss']:,.2f}",
        })

        self._fill_table(self.pnl_table, {
            "Average P&L": f"${m['avg_pnl']:.2f}",
            "Median P&L": f"${m['median_pnl']:.2f}",
            "Std Dev P&L": f"${m['std_pnl']:.2f}",
            "Best Trade": f"${m['best_trade_pnl']:,.2f}",
            "Worst Trade": f"${m['worst_trade_pnl']:,.2f}",
            "Avg Winning Trade": f"${m['avg_win_pnl']:.2f}",
            "Avg Losing Trade": f"${m['avg_loss_pnl']:.2f}",
        })

        self._fill_table(self.duration_table, {
            "Avg Trade Duration": f"{m['avg_duration']}",
            "Avg Win Duration": f"{m['avg_win_duration']}",
            "Avg Loss Duration": f"{m['avg_loss_duration']}",
            "Initial Capital": f"${m['initial_capital']:,.2f}",
            "Final Capital": f"${m['final_capital']:,.2f}",
        })

        # Monthly returns table
        monthly = m.get("monthly_returns")
        if monthly is not None and not monthly.empty:
            self.monthly_table.setColumnCount(2)
            self.monthly_table.setHorizontalHeaderLabels(["Month", "Return %"])
            self.monthly_table.setRowCount(len(monthly))
            for i, (idx, row) in enumerate(monthly.iterrows()):
                val = row["return_pct"]
                self.monthly_table.setItem(i, 0, QTableWidgetItem(str(idx)))
                item = QTableWidgetItem(f"{val:+.2f}%")
                if val > 0:
                    item.setForeground(QBrush(QColor("#00FF88")))
                elif val < 0:
                    item.setForeground(QBrush(QColor("#FF4444")))
                self.monthly_table.setItem(i, 1, item)
                self.monthly_table.item(i, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.monthly_table.item(i, 1).setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.monthly_table.horizontalHeader().setStretchLastSection(True)
            self.monthly_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.monthly_table.verticalHeader().hide()
            self.monthly_group.show()
        else:
            self.monthly_group.hide()

        # Trade log
        if r and r.trades:
            cols = [
                "Entry Time", "Exit Time", "Side", "Entry Price", "Exit Price",
                "Quantity", "P&L", "P&L %", "Exit Reason", "Duration",
            ]
            self.trade_table.setColumnCount(len(cols))
            self.trade_table.setHorizontalHeaderLabels(cols)
            self.trade_table.setRowCount(len(r.trades))
            for i, t in enumerate(r.trades):
                self.trade_table.setItem(i, 0, QTableWidgetItem(
                    t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else ""))
                self.trade_table.setItem(i, 1, QTableWidgetItem(
                    t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else ""))
                self.trade_table.setItem(i, 2, QTableWidgetItem("Long" if t.side == 1 else "Short"))
                self.trade_table.setItem(i, 3, QTableWidgetItem(
                    f"${t.entry_price:.2f}" if t.entry_price else ""))
                self.trade_table.setItem(i, 4, QTableWidgetItem(
                    f"${t.exit_price:.2f}" if t.exit_price else ""))
                self.trade_table.setItem(i, 5, QTableWidgetItem(f"{t.quantity:.6f}"))
                pnl_item = QTableWidgetItem(
                    f"${t.pnl:.2f}" if t.pnl else "")
                if t.pnl is not None:
                    pnl_item.setForeground(QBrush(
                        QColor("#00FF88") if t.pnl > 0 else QColor("#FF4444")))
                self.trade_table.setItem(i, 6, pnl_item)
                self.trade_table.setItem(i, 7, QTableWidgetItem(
                    f"{t.pnl_pct:.2f}%" if t.pnl_pct else ""))
                self.trade_table.setItem(i, 8, QTableWidgetItem(t.exit_reason or ""))
                self.trade_table.setItem(i, 9, QTableWidgetItem(
                    str(t.duration).split(".")[0] if t.duration else ""))

                for c in range(len(cols)):
                    self.trade_table.item(i, c).setFlags(Qt.ItemFlag.ItemIsEnabled)

            self.trade_table.horizontalHeader().setStretchLastSection(True)
            self.trade_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
            self.trade_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.trade_table.verticalHeader().hide()
            self.trade_group.show()
        else:
            self.trade_group.hide()

    def _export_csv(self):
        if not self.state.backtest_result or not self.state.backtest_result.trades:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Trade Log", "trade_log.csv", "CSV Files (*.csv)")
        if not path:
            return
        rows = []
        for t in self.state.backtest_result.trades:
            rows.append({
                "Entry Time": t.entry_time.strftime("%Y-%m-%d %H:%M") if t.entry_time else "",
                "Exit Time": t.exit_time.strftime("%Y-%m-%d %H:%M") if t.exit_time else "",
                "Side": "Long" if t.side == 1 else "Short",
                "Entry Price": f"{t.entry_price:.2f}" if t.entry_price else "",
                "Exit Price": f"{t.exit_price:.2f}" if t.exit_price else "",
                "Quantity": f"{t.quantity:.6f}",
                "P&L": f"{t.pnl:.2f}" if t.pnl else "",
                "P&L %": f"{t.pnl_pct:.2f}" if t.pnl_pct else "",
                "Exit Reason": t.exit_reason or "",
                "Duration": str(t.duration).split(".")[0] if t.duration else "",
            })
        df = pd.DataFrame(rows)
        df.to_csv(path, index=False)
