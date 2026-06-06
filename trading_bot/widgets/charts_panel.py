import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from state import AppState
from widgets.chart_widgets import (
    build_equity_curve,
    build_trade_histogram,
    build_trade_scatter,
)


class ChartsPanel(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_equity_tab(), "Equity & Drawdown")
        self.tabs.addTab(self._build_monthly_tab(), "Monthly Returns")
        self.tabs.addTab(self._build_trade_tab(), "Trade Analysis")
        layout.addWidget(self.tabs)

    def _build_equity_tab(self):
        w = QWidget()
        self.equity_layout = QVBoxLayout(w)
        self.equity_chart_container = QWidget()
        self.equity_layout.addWidget(self.equity_chart_container)
        return w

    def _build_monthly_tab(self):
        w = QWidget()
        self.monthly_layout = QVBoxLayout(w)
        self.monthly_table = QTableWidget()
        self.monthly_layout.addWidget(self.monthly_table)
        return w

    def _build_trade_tab(self):
        w = QWidget()
        self.trade_layout = QVBoxLayout(w)
        self.trade_inner = QHBoxLayout()
        self.hist_container = QWidget()
        self.scatter_container = QWidget()
        self.trade_inner.addWidget(self.hist_container, 1)
        self.trade_inner.addWidget(self.scatter_container, 1)
        self.trade_layout.addLayout(self.trade_inner)
        return w

    def refresh(self):
        m = self.state.backtest_metrics
        r = self.state.backtest_result

        if not r:
            return

        self._clear_layout(self.equity_layout)
        self._clear_layout(self.hist_container)
        self._clear_layout(self.scatter_container)

        eq_w = build_equity_curve(r)
        self.equity_layout.addWidget(eq_w)

        self._rebuild_monthly_table(m)

        h_w = build_trade_histogram(r.trades if r.trades else [])
        if self.hist_container.layout() is None:
            self.hist_container.setLayout(QHBoxLayout())
        self.hist_container.layout().addWidget(h_w)

        s_w = build_trade_scatter(r.trades if r.trades else [])
        if self.scatter_container.layout() is None:
            self.scatter_container.setLayout(QHBoxLayout())
        self.scatter_container.layout().addWidget(s_w)

    def _rebuild_monthly_table(self, metrics):
        self.monthly_table.clear()
        monthly = metrics.get("monthly_returns") if metrics else None
        if monthly is None or monthly.empty:
            self.monthly_table.setRowCount(0)
            self.monthly_table.setColumnCount(0)
            return

        data = monthly.copy()
        data["year"] = data.index.str[:4]
        data["month"] = data.index.str[5:7].astype(int)

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        years = sorted(data["year"].unique())

        self.monthly_table.setColumnCount(13)
        self.monthly_table.setHorizontalHeaderLabels([""] + months)
        self.monthly_table.setRowCount(len(years))
        self.monthly_table.verticalHeader().hide()
        self.monthly_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for ri, y in enumerate(years):
            self.monthly_table.setItem(ri, 0, QTableWidgetItem(y))
            self.monthly_table.item(ri, 0).setFlags(Qt.ItemFlag.ItemIsEnabled)
            for mi in range(1, 13):
                ym = f"{y}-{mi:02d}"
                row = data[data.index == ym]
                item = QTableWidgetItem()
                if not row.empty:
                    val = row["return_pct"].values[0]
                    item.setText(f"{val:+.2f}%")
                    if val > 0:
                        item.setBackground(QBrush(QColor(0, 255, 136, 60)))
                        item.setForeground(QBrush(QColor("#00FF88")))
                    elif val < 0:
                        item.setBackground(QBrush(QColor(255, 68, 68, 60)))
                        item.setForeground(QBrush(QColor("#FF4444")))
                    else:
                        item.setForeground(QBrush(QColor("#888888")))
                else:
                    item.setText("")
                    item.setBackground(QBrush(QColor(40, 40, 40)))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.monthly_table.setItem(ri, mi, item)

        self.monthly_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)

    def _clear_layout(self, layout_or_widget):
        if layout_or_widget is None:
            return
        if isinstance(layout_or_widget, QWidget):
            w = layout_or_widget
            old = w.layout()
            if old is not None:
                while old.count():
                    item = old.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
            return
        while layout_or_widget.count():
            item = layout_or_widget.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
