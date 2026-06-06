import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QLineEdit, QPushButton, QLabel, QDoubleSpinBox,
    QMessageBox, QGridLayout,
)
from PyQt6.QtCore import pyqtSignal
from exchange.connector import get_exchange_names, validate_credentials
from state import AppState

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")


class SettingsPanel(QWidget):
    state_changed = pyqtSignal()

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self._load_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Exchange config ──
        exch_group = QGroupBox("Exchange Configuration")
        exch_layout = QFormLayout(exch_group)

        self.exchange_combo = QComboBox()
        self.exchange_combo.addItems(get_exchange_names())
        exch_layout.addRow("Exchange:", self.exchange_combo)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        exch_layout.addRow("API Key:", self.api_key_input)

        self.api_secret_input = QLineEdit()
        self.api_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        exch_layout.addRow("API Secret:", self.api_secret_input)

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        exch_layout.addRow("", btn_row)

        layout.addWidget(exch_group)

        # ── Backtest defaults ──
        defaults_group = QGroupBox("Backtest Defaults")
        defaults_layout = QFormLayout(defaults_group)

        self.risk_spin = QDoubleSpinBox()
        self.risk_spin.setRange(0.1, 10.0)
        self.risk_spin.setSuffix(" %")
        self.risk_spin.setDecimals(1)
        self.risk_spin.setSingleStep(0.1)
        defaults_layout.addRow("Risk per trade:", self.risk_spin)

        self.rr_spin = QDoubleSpinBox()
        self.rr_spin.setRange(0.5, 10.0)
        self.rr_spin.setSingleStep(0.1)
        self.rr_spin.setDecimals(1)
        defaults_layout.addRow("Risk:Reward:", self.rr_spin)

        self.fee_spin = QDoubleSpinBox()
        self.fee_spin.setRange(0.0, 1.0)
        self.fee_spin.setSingleStep(0.01)
        self.fee_spin.setDecimals(3)
        self.fee_spin.setSuffix(" %")
        defaults_layout.addRow("Fee rate:", self.fee_spin)

        layout.addWidget(defaults_group)

        # ── Cache ──
        cache_group = QGroupBox("Data Cache")
        cache_layout = QVBoxLayout(cache_group)

        self.cache_label = QLabel()
        cache_layout.addWidget(self.cache_label)

        self.clear_cache_btn = QPushButton("Clear Cache")
        self.clear_cache_btn.clicked.connect(self._clear_cache)
        cache_layout.addWidget(self.clear_cache_btn)

        layout.addWidget(cache_group)
        layout.addStretch()

    def _load_state(self):
        idx = self.exchange_combo.findText(self.state.exchange_id)
        if idx >= 0:
            self.exchange_combo.setCurrentIndex(idx)
        self.api_key_input.setText(self.state.api_key)
        self.api_secret_input.setText(self.state.api_secret)
        self.risk_spin.setValue(self.state.risk_percent)
        self.rr_spin.setValue(self.state.rr)
        self.fee_spin.setValue(self.state.fee_rate * 100)
        self._update_cache_label()

        self.exchange_combo.currentTextChanged.connect(self._on_change)
        self.api_key_input.textChanged.connect(self._on_change)
        self.api_secret_input.textChanged.connect(self._on_change)
        self.risk_spin.valueChanged.connect(self._on_change)
        self.rr_spin.valueChanged.connect(self._on_change)
        self.fee_spin.valueChanged.connect(self._on_change)

    def _on_change(self):
        self.state.exchange_id = self.exchange_combo.currentText()
        self.state.api_key = self.api_key_input.text()
        self.state.api_secret = self.api_secret_input.text()
        self.state.risk_percent = self.risk_spin.value()
        self.state.rr = self.rr_spin.value()
        self.state.fee_rate = self.fee_spin.value() / 100
        self.state_changed.emit()

    def _test_connection(self):
        ex = self.exchange_combo.currentText()
        key = self.api_key_input.text()
        secret = self.api_secret_input.text()
        if not key or not secret:
            QMessageBox.information(self, "Test Connection", "Enter API key and secret first.")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        valid = validate_credentials(ex, key, secret)
        if valid:
            QMessageBox.information(self, "Connection Test", "Connection successful!")
        else:
            QMessageBox.warning(self, "Connection Test", "Connection failed. Check your API keys and permissions.")
        self.test_btn.setText("Test Connection")
        self.test_btn.setEnabled(True)

    def _update_cache_label(self):
        total = 0
        if os.path.exists(CACHE_DIR):
            for fname in os.listdir(CACHE_DIR):
                fpath = os.path.join(CACHE_DIR, fname)
                if os.path.isfile(fpath):
                    total += os.path.getsize(fpath)
        self.cache_label.setText(f"Cache size: {total / 1024 / 1024:.2f} MB")

    def _clear_cache(self):
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        self._update_cache_label()
