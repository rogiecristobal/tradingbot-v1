import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QTimer

from core.backtest_engine import BacktestResult

GREEN = "#26A69A"
RED = "#EF5350"
CYAN = "#00BFFF"
ORANGE = "#FFA500"
WHITE = "#d0d0d0"


class ChartViewBox(pg.ViewBox):
    def wheelEvent(self, ev, axis=None):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(ev, axis=0)
        else:
            super().wheelEvent(ev, axis=1)


class Crosshair:
    def __init__(self, plot_widget):
        self.plot = plot_widget
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=QPen(QColor(WHITE), 0.5, Qt.PenStyle.DashLine))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=QPen(QColor(WHITE), 0.5, Qt.PenStyle.DashLine))
        self.label = pg.TextItem("", anchor=(0, 1))
        self.label.setFont(QFont("monospace", 9))
        self.label.setZValue(100)
        self.plot.addItem(self.vline, ignoreBounds=True)
        self.plot.addItem(self.hline, ignoreBounds=True)
        self.plot.addItem(self.label, ignoreBounds=True)
        QTimer.singleShot(0, self._connect)

    def _connect(self):
        scene = self.plot.scene()
        if scene is not None:
            try:
                scene.sigMouseMoved.connect(self._mouse_moved)
                return
            except Exception:
                pass
        QTimer.singleShot(200, self._connect)

    def _mouse_moved(self, pos):
        vb = self.plot.getViewBox()
        if vb is None:
            return
        mouse_point = vb.mapSceneToView(pos)
        self.vline.setPos(mouse_point.x())
        self.hline.setPos(mouse_point.y())
        x_str = f"{mouse_point.x():.2f}" if abs(mouse_point.x()) < 1e6 else f"{mouse_point.x():.0f}"
        self.label.setText(f"x={x_str}  y={mouse_point.y():.2f}")
        self.label.setPos(mouse_point.x(), mouse_point.y())
        self._show()

    def _show(self):
        self.vline.show()
        self.hline.show()
        self.label.show()

    def hide(self):
        self.vline.hide()
        self.hline.hide()
        self.label.hide()


def build_equity_curve(result: BacktestResult) -> pg.GraphicsLayoutWidget:
    w = pg.GraphicsLayoutWidget()
    w.setBackground("#1e1e1e")

    eq = result.equity_curve
    if eq.empty:
        return w

    p1 = w.addPlot(row=0, col=0, title="Equity Curve", viewBox=ChartViewBox())
    p2 = w.addPlot(row=1, col=0, title="Drawdown", viewBox=ChartViewBox())
    p1.setXLink(p2)
    p1.showGrid(x=True, y=True, alpha=0.2)
    p2.showGrid(x=True, y=True, alpha=0.2)
    p1.addLegend()

    x = eq.index.astype("int64").values / 10**9
    y = eq.values.astype(float)
    p1.plot(x, y, pen=QPen(QColor(CYAN), 1.5), name="Equity")
    p1.setLabel("left", "Equity", units="$")

    peak = np.maximum.accumulate(y)
    drawdown = (y - peak) / peak * 100
    p2.plot(x, drawdown, pen=QPen(QColor(RED), 1.5), fillLevel=0,
            brush=QBrush(QColor(255, 68, 68, 40)))
    p2.setLabel("left", "Drawdown", units="%")

    p1.showButtons()
    p2.showButtons()
    Crosshair(p1)
    Crosshair(p2)
    return w


def build_trade_histogram(trades: list) -> pg.PlotWidget:
    w = pg.PlotWidget()
    w.setBackground("#1e1e1e")
    w.setTitle("Trade P&L Distribution")
    w.showGrid(x=True, y=True, alpha=0.2)
    w.setLabel("left", "Count")
    w.setLabel("bottom", "P&L ($)")

    if not trades:
        return w
    pnls = [t.pnl for t in trades if t.pnl is not None]
    if not pnls:
        return w
    counts, edges = np.histogram(pnls, bins=30)
    x = (edges[:-1] + edges[1:]) / 2
    w.addItem(pg.BarGraphItem(x=x, height=counts, width=(edges[1] - edges[0]) * 0.8,
                               pen=QPen(QColor(CYAN), 0.5), brush=QBrush(QColor(0, 191, 255, 120))))
    w.addLine(y=0, pen=QPen(QColor(WHITE), 0.5, Qt.PenStyle.DashLine))
    Crosshair(w)
    return w


def build_trade_scatter(trades: list) -> pg.PlotWidget:
    w = pg.PlotWidget()
    w.setBackground("#1e1e1e")
    w.setTitle("Trade Duration vs P&L")
    w.showGrid(x=True, y=True, alpha=0.2)
    w.setLabel("left", "P&L ($)")
    w.setLabel("bottom", "Duration (hours)")

    if not trades:
        return w
    durations_h = []
    pnls = []
    colors = []
    for t in trades:
        if t.duration is None or t.pnl is None:
            continue
        durations_h.append(t.duration.total_seconds() / 3600)
        pnls.append(t.pnl)
        colors.append(QColor(GREEN) if t.pnl > 0 else QColor(RED))

    if not durations_h:
        return w
    scatter = pg.ScatterPlotItem(
        x=np.array(durations_h), y=np.array(pnls),
        size=8, brush=colors, pen=QPen(QColor(WHITE), 0.5),
    )
    w.addItem(scatter)
    w.addLine(y=0, pen=QPen(QColor(WHITE), 0.5, Qt.PenStyle.DashLine))
    Crosshair(w)
    return w
