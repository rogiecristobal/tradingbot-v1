import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

from data.ohlcv import fetch_ohlcv
from exchange.connector import build_exchange
from live.config import load_config, save_config
from live.executor import build_executor
from live.position_manager import Position, check_exit, update_trail

logger = logging.getLogger(__name__)


def _compute_quantity(equity: float, entry: float, sl: float,
                      risk_percent: float) -> float:
    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0:
        return 0
    risk_amount = equity * (risk_percent / 100.0)
    return risk_amount / risk_per_unit


class LiveEngine:
    def __init__(self, config: dict):
        self.config = config
        self.executor = build_executor(config)
        self.exchange = None
        if config.get("mode") == "live":
            self.exchange = build_exchange(
                config["exchange_id"],
                config.get("api_key", ""),
                config.get("api_secret", ""),
            )
        pos_data = config.get("position")
        self.position: Optional[Position] = (
            Position.from_dict(pos_data) if pos_data else None
        )
        self.last_candle_time: Optional[pd.Timestamp] = None
        self.peak_equity = config.get("capital", 10000.0)
        self.daily_start_equity = self.peak_equity
        self.last_check_date = date.today()

    def start(self):
        logger.info(
            f"Bot starting — {self.config['exchange_id']} "
            f"{self.config['symbol']} "
            f"mode={self.config['mode'].upper()}"
        )
        while True:
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"Tick error: {e}")
            time.sleep(60)

    def _current_price(self) -> Optional[float]:
        if self.exchange:
            try:
                ticker = self.exchange.fetch_ticker(self.config["symbol"])
                return ticker.get("last")
            except Exception:
                return None
        return None

    def _tick(self):
        symbol = self.config["symbol"]
        params = self.config["params"]
        mode = self.config.get("mode", "paper")

        # ── 1. Current price ──
        if mode == "live" and self.exchange:
            current_price = self._current_price()
            if current_price is None:
                logger.warning("Could not fetch current price, skipping tick")
                return
        else:
            current_price = None

        # ── 2. Fetch 4H OHLCV (no cache) ──
        df = fetch_ohlcv(
            exchange_id=self.config["exchange_id"],
            symbol=symbol,
            timeframe="4h",
            start_date=(datetime.now(pytz.UTC) - timedelta(days=30)).strftime("%Y-%m-%d"),
            end_date=datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
            use_cache=False,
        )
        if df.empty or len(df) < 2:
            logger.debug("Not enough 4H data yet")
            return

        latest_bar = df.iloc[-1]
        latest_time = df.index[-1]

        # ── 3. If in position, check SL/TP/trail ──
        if self.position is not None:
            if mode == "paper":
                high = latest_bar["high"]
                low = latest_bar["low"]
                close = latest_bar["close"]
            else:
                high = current_price if current_price else latest_bar["high"]
                low = current_price if current_price else latest_bar["low"]
                close = current_price if current_price else latest_bar["close"]

            reason, exit_price = check_exit(self.position, high, low, close)
            if reason is None:
                new_sl = update_trail(
                    self.position, high, low,
                    params.get("trail_activation", 0),
                    params.get("trail_offset", 0),
                )

            if reason:
                qty = self.position.quantity
                self.executor.place_market_close(
                    self.position.side, qty, exit_price
                )
                pnl = (exit_price - self.position.entry_price) * qty * self.position.side
                fee = exit_price * qty * 0.001
                self.executor.equity += pnl - fee
                logger.info(
                    f"CLOSED {reason.upper()} "
                    f"PNL=${pnl:.2f} "
                    f"Equity=${self.executor.equity:.2f}"
                )
                self.position = None
                self._save_state()

        # ── 4. Check new 4H candle ──
        if self.last_candle_time is None:
            self.last_candle_time = latest_time
            logger.info(f"First candle seen: {latest_time} — will not trade this one")
            self._save_state()
            return

        if latest_time <= self.last_candle_time:
            self._save_state()
            return

        self.last_candle_time = latest_time
        logger.info(f"New 4H candle: {latest_time}")

        # ── 5. Run strategy on the last completed candle ──
        from core.strategy_atr_breakout import run_atr_breakout
        signals_df = run_atr_breakout(df, **params)
        if signals_df.empty:
            logger.debug("Strategy returned empty")
            self._save_state()
            return

        last_signal = signals_df.iloc[-1]
        sig = last_signal.get("signal", 0)

        if sig != 0 and self.position is None:
            # Entry at the current available price
            prev_entry = last_signal["entry_price"]
            prev_sl = last_signal["sl_price"]
            prev_tp = last_signal["tp_price"]

            if mode == "live" and current_price is not None:
                entry_price = current_price
            else:
                entry_price = latest_bar["close"]

            diff = entry_price - prev_entry
            sl_price = prev_sl + diff
            tp_price = prev_tp + diff

            equity = self.executor.equity
            qty = _compute_quantity(equity, entry_price, sl_price,
                                    params.get("risk_percent", 1.0))
            if qty <= 0:
                logger.warning("Computed zero quantity, skipping entry")
                self._save_state()
                return

            atr_val = last_signal.get("atr", 0)
            if pd.isna(atr_val):
                atr_val = 0

            self.executor.place_market_entry(
                sig, qty, entry_price, sl_price, tp_price
            )

            self.position = Position(
                side=sig,
                entry_time=str(latest_time),
                entry_price=entry_price,
                quantity=qty,
                sl_price=sl_price,
                tp_price=tp_price,
                atr_at_entry=atr_val,
                highest_price=entry_price,
                lowest_price=entry_price,
            )
            logger.info(
                f"ENTERED {'LONG' if sig == 1 else 'SHORT'} "
                f"qty={qty:.6f} @ {entry_price:.2f} "
                f"SL={sl_price:.2f} TP={tp_price:.2f}"
            )

        # ── 6. Safety checks ──
        self._check_safety()

        # ── 7. Save state ──
        self._save_state()

    def _check_safety(self):
        equity = self.executor.equity
        if equity > self.peak_equity:
            self.peak_equity = equity

        today = date.today()
        if today != self.last_check_date:
            self.daily_start_equity = equity
            self.last_check_date = today

        max_daily = self.config.get("max_daily_loss_pct", 10.0)
        daily_loss = (self.daily_start_equity - equity) / self.daily_start_equity * 100
        if daily_loss >= max_daily:
            logger.warning(
                f"Max daily loss hit ({daily_loss:.1f}% >= {max_daily}%)"
            )

        max_dd = self.config.get("max_drawdown_pct", 20.0)
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd >= max_dd:
            logger.warning(
                f"Max drawdown hit ({dd:.1f}% >= {max_dd}%)"
            )

    def _save_state(self):
        self.config["capital"] = round(self.executor.equity, 2)
        if self.position is not None:
            self.config["position"] = self.position.to_dict()
        else:
            self.config["position"] = None
        save_config(self.config)
