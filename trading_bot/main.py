import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
import pyqtgraph as pg
from main_window import MainWindow

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

pg.setConfigOption("background", "#1e1e1e")
pg.setConfigOption("foreground", "#d0d0d0")
pg.setConfigOptions(antialias=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")

palette = QPalette()
palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
palette.setColor(QPalette.ColorRole.WindowText, QColor(208, 208, 208))
palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
palette.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(40, 40, 40))
palette.setColor(QPalette.ColorRole.ToolTipText, QColor(208, 208, 208))
palette.setColor(QPalette.ColorRole.Text, QColor(208, 208, 208))
palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
palette.setColor(QPalette.ColorRole.ButtonText, QColor(208, 208, 208))
palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 68, 68))
palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
app.setPalette(palette)

window = MainWindow()
window.show()
sys.exit(app.exec())
