# Session: PyQt6 + PyQtGraph Migration

## Changes made

### New files
- `trading_bot/main.py` — Entry point: QApplication + dark Fusion theme
- `trading_bot/main_window.py` — QMainWindow with QTabWidget (Backtest, Statistics, Charts, Settings)
- `trading_bot/state.py` — `AppState` dataclass replacing `st.session_state`
- `trading_bot/widgets/__init__.py`
- `trading_bot/widgets/comp/__init__.py`
- `trading_bot/widgets/settings_panel.py` — Exchange config, API keys, backtest defaults, cache mgmt
- `trading_bot/widgets/backtest_panel.py` — Strategy params, Run button, QThread-based backtest, summary
- `trading_bot/widgets/statistics_panel.py` — QTableWidget metrics, monthly returns, trade log + CSV export
- `trading_bot/widgets/charts_panel.py` — QTabWidget with 4 chart tabs
- `trading_bot/widgets/chart_widgets.py` — PyQtGraph plot builders (equity curve, histogram, scatter, candlestick price chart)
- `trading_bot/widgets/comp/candlestick.py` — Custom `CandlestickItem` (QPainterPath-based)

### Modified files
- `Pipfile` — Replaced `streamlit`/`plotly` with `pyqt6`/`pyqtgraph`
- `exchange/connector.py` — Stripped `streamlit` dependency, uses `logging` instead
- `data/ohlcv.py` — Stripped `streamlit`, added `progress_callback` parameter

### Unchanged (business logic)
- `core/strategy.py`, `core/strategy_trend_pullback.py`, `core/strategy_trend_pullback_v2.py`
- `core/backtest_engine.py`, `core/metrics.py`
- `exchange/__init__.py`, `data/__init__.py`, `core/__init__.py`

### Obsolete (still on disk, not imported)
- `app.py`, all `pages/`, `components/`

## Run command
```
pipenv run python main.py
```

## Key decisions
- QThread-based backtest keeps UI responsive during data fetch / strategy execution
- Crosshair connected deferred via QTimer (scene availability)
- PyQtGraph symbols: `"t"` (triangle up), `"t1"` (triangle down), `"x"` (cross)
- Dark Fusion theme via QPalette + pyqtgraph config
