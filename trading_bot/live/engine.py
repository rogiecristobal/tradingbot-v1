import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional, Dict

import pandas as pd
import pytz

from data.ohlcv import fetch_ohlcv
from exchange.connector import build_exchange
from live.config import load_config, save_config
from live.executor import build_executor
from live.position_manager import Position, check_exit, update_trail
from live.news_checker import check_news

logger = logging.getLogger(__name__)


def _compute_quantity(total_capital: float, entry: float, sl: float,
                      risk_percent: float, leverage: float = 1.0,
                      exchange=None, symbol=None) -> float:
    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0:
        return 0
    risk_amount = total_capital * (risk_percent / 100.0)
    qty = risk_amount / risk_per_unit
    max_notional = total_capital * leverage
    qty = min(qty, max_notional / entry)

    if exchange and symbol:
        try:
            market = exchange.market(symbol)
            limits = market.get("limits", {})
            min_qty = float(limits.get("amount", {}).get("min", 0) or 0)
            min_cost = float(limits.get("cost", {}).get("min", 0) or 0)
            notional = qty * entry
            if (min_qty and qty < min_qty) or (min_cost and notional < min_cost):
                logger.info(
                    f"{symbol}: qty {qty:.6f} (${notional:.2f}) below min "
                    f"(qty={min_qty}, cost=${min_cost}), skipping"
                )
                return 0
        except Exception:
            pass
    return qty


class LiveEngine:
    def __init__(self, config: dict, telegram=None):
        self.config = config
        self.executor = build_executor(config)
        self.telegram = telegram
        self.exchange = None
        if config.get("mode") == "live":
            self.exchange = build_exchange(
                config["exchange_id"],
                config.get("api_key", ""),
                config.get("api_secret", ""),
            )

        self.symbols: list = config.get("symbols", [])
        self.max_open_trades: int = config.get("max_open_trades", 3)

        self.positions: Dict[str, Optional[Position]] = {}
        self.last_candle_times: Dict[str, Optional[pd.Timestamp]] = {}
        positions_raw = config.get("positions", {})

        for sym in self.symbols:
            raw = positions_raw.get(sym) if isinstance(positions_raw, dict) else None
            self.positions[sym] = Position.from_dict(raw) if raw else None
            self.last_candle_times[sym] = None

        restored = sum(1 for p in self.positions.values() if p is not None)
        self.peak_equity = config.get("capital", 100.0)
        self.daily_start_equity = self.peak_equity
        self.last_check_date = date.today()
        self._tick_count = 0
        self._paused = False
        self._stopped = False
        self._telegram_heartbeat_count = 0
        logger.info(f"Restored {restored} open position(s) across {len(self.symbols)} symbols")

    def start(self):
        mode = self.config.get("mode", "paper")
        msg = (
            f"🤖 Bot started\n"
            f"Exchange: {self.config['exchange_id']}\n"
            f"Mode: {mode.upper()}\n"
            f"Symbols: {len(self.symbols)}\n"
            f"Capital: ${self.config.get('capital', 0):.2f}"
        )
        logger.info(
            f"Bot starting — {self.config['exchange_id']} "
            f"{len(self.symbols)} symbols "
            f"mode={mode.upper()}"
        )
        if self.telegram:
            self.telegram.send(msg)
        while True:
            if self._stopped:
                logger.info("Bot stopped via Telegram /stop command")
                if self.telegram:
                    self.telegram.send("🛑 Bot stopped.")
                break
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"Tick error: {e}")
                if self.telegram:
                    self.telegram.send(f"⚠️ Tick error: {e}")
            for _ in range(60):
                if self._stopped:
                    break
                time.sleep(1)

    def _current_price(self, symbol: str) -> Optional[float]:
        if self.exchange:
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                return ticker.get("last")
            except Exception:
                return None
        return None

    def _reconcile_position(self, symbol: str):
        pos = self.positions.get(symbol)
        if pos is None or self.exchange is None:
            return
        try:
            positions = self.exchange.fetch_positions([symbol])
            for p in positions:
                if p["symbol"] == symbol:
                    size = abs(float(p.get("size", p.get("contracts", 0)) or 0))
                    if size == 0:
                        logger.info(
                            f"[LIVE] {symbol} position closed on exchange — "
                            "clearing engine position"
                        )
                        self.positions[symbol] = None
                    return
        except Exception as e:
            logger.warning(f"[LIVE] {symbol} reconciliation failed: {e}")

    def _tick(self):
        if self._stopped:
            return
        mode = self.config.get("mode", "paper")

        # ── 1. Prices + reconcile (live mode) ──
        prices: Dict[str, Optional[float]] = {}
        if mode == "live" and self.exchange:
            for sym in self.symbols:
                p = self._current_price(sym)
                prices[sym] = p
                if p is None:
                    logger.warning(f"{sym}: could not fetch price")
                self._reconcile_position(sym)

        # ── 2. Heartbeat every 2 minutes ──
        self._tick_count += 1
        if self._tick_count % 2 == 0:
            open_count = sum(1 for p in self.positions.values() if p is not None)
            equity = self.executor.equity
            logger.info(
                f"Heartbeat — {len(self.symbols)} symbols, "
                f"{open_count} open, "
                f"equity=${equity:.2f}"
            )
            if self.telegram:
                self._telegram_heartbeat_count += 1
                if self._telegram_heartbeat_count >= 15:
                    self._telegram_heartbeat_count = 0
                    dd = (self.peak_equity - equity) / self.peak_equity * 100 if self.peak_equity > 0 else 0
                    daily = (self.daily_start_equity - equity) / self.daily_start_equity * 100 if self.daily_start_equity > 0 else 0
                    paused = " PAUSED" if self._paused else ""
                    hb_msg = (
                        f"📊 Heartbeat{paused}\n"
                        f"Symbols: {len(self.symbols)} | Open: {open_count}\n"
                        f"Equity: ${equity:.2f}\n"
                        f"DD: {dd:.1f}% | Daily: {daily:+.1f}%"
                    )
                    if self._paused:
                        hb_msg += "\n⏸ New entries paused"
                    self.telegram.send(hb_msg)

        # ── 3. Process each symbol ──
        for sym in self.symbols:
            self._process_symbol(sym, prices.get(sym) if mode == "live" else None)

        # ── 4. Safety checks ──
        self._check_safety()

        # ── 5. Save state ──
        self._save_state()

    def _process_symbol(self, symbol: str, current_price: Optional[float]):
        params = self.config.get("params", {})
        mode = self.config.get("mode", "paper")

        # ── Fetch OHLCV ──
        df = fetch_ohlcv(
            exchange_id=self.config["exchange_id"],
            symbol=symbol,
            timeframe="4h",
            start_date=(datetime.now(pytz.UTC) - timedelta(days=30)).strftime("%Y-%m-%d"),
            end_date=datetime.now(pytz.UTC).strftime("%Y-%m-%d"),
            use_cache=False,
        )
        if df.empty or len(df) < 2:
            return

        latest_bar = df.iloc[-1]
        latest_time = df.index[-1]
        pos = self.positions.get(symbol)
        candle_time = self.last_candle_times.get(symbol)

        # ── SL/TP/trail check on open position ──
        if pos is not None:
            if mode == "paper":
                high = latest_bar["high"]
                low = latest_bar["low"]
                close = latest_bar["close"]
            else:
                high = current_price if current_price else latest_bar["high"]
                low = current_price if current_price else latest_bar["low"]
                close = current_price if current_price else latest_bar["close"]

            reason, exit_price = check_exit(pos, high, low, close)
            if reason is None:
                update_trail(
                    pos, high, low,
                    params.get("trail_activation", 0),
                    params.get("trail_offset", 0),
                )

            if reason:
                qty = pos.quantity
                self.executor.place_market_close(symbol, pos.side, qty, exit_price)
                pnl = (exit_price - pos.entry_price) * qty * pos.side
                fee = exit_price * qty * 0.001
                self.executor.equity += pnl - fee
                logger.info(
                    f"{symbol} CLOSED {reason.upper()} "
                    f"PNL=${pnl:.2f} Equity=${self.executor.equity:.2f}"
                )
                if self.telegram:
                    side_str = "LONG" if pos.side == 1 else "SHORT"
                    emoji = "🔴" if pnl < 0 else "🟢"
                    self.telegram.send(
                        f"{emoji} {symbol} CLOSED ({reason})\n"
                        f"Side: {side_str}\n"
                        f"P&L: ${pnl:.2f}\n"
                        f"Equity: ${self.executor.equity:.2f}"
                    )
                self.positions[symbol] = None

        # ── Candle tracking ──
        if candle_time is None:
            self.last_candle_times[symbol] = latest_time
            logger.info(f"{symbol}: first candle seen {latest_time} — will not trade this one")
            return

        if latest_time <= candle_time:
            return

        self.last_candle_times[symbol] = latest_time
        logger.info(f"{symbol}: new 4H candle {latest_time}")

        # ── Run strategy ──
        from core.strategy_atr_breakout import run_atr_breakout
        sym_params = dict(params)
        sym_params.update(self.config.get("symbol_params", {}).get(symbol, {}))
        signals_df = run_atr_breakout(df, **sym_params)

        # ── Trade decision ──
        if signals_df.empty:
            logger.info(f"{symbol}: no trade this candle — strategy returned no data")
            return

        last_signal = signals_df.iloc[-1]
        sig = last_signal.get("signal", 0)

        if self.positions.get(symbol) is not None:
            logger.info(f"{symbol}: no trade this candle — already in position")
            return

        if sig == 0:
            logger.info(f"{symbol}: no trade this candle — no signal")
            return

        if self._paused:
            logger.info(f"{symbol}: no trade this candle — paused")
            return

        open_count = sum(1 for p in self.positions.values() if p is not None)
        if open_count >= self.max_open_trades:
            logger.info(f"{symbol}: no trade this candle — max open trades ({open_count})")
            return

        news_headlines = check_news(symbol)
        if news_headlines:
            logger.info(f"{symbol} news: {' | '.join(news_headlines[:3])}")
            if self.telegram:
                lines = "\n".join(f"• {h}" for h in news_headlines[:3])
                self.telegram.send(f"📰 {symbol} headlines:\n{lines}")

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

        total_cap = self.config.get("capital", 100.0)
        risk_pct = sym_params.get("risk_percent", 1.0)
        qty = _compute_quantity(
            total_cap, entry_price, sl_price, risk_pct,
            leverage=self.config.get("leverage", 1),
            exchange=self.exchange if mode == "live" else None,
            symbol=symbol if mode == "live" else None,
        )
        if qty <= 0:
            logger.info(f"{symbol}: no trade this candle — quantity below minimum")
            return

        atr_val = last_signal.get("atr", 0)
        if pd.isna(atr_val):
            atr_val = 0

        logger.info(
            f"{symbol} ENTERING {'LONG' if sig == 1 else 'SHORT'} "
            f"qty={qty:.6f} @ {entry_price:.2f} "
            f"SL={sl_price:.2f} TP={tp_price:.2f}"
        )

        self.executor.place_market_entry(symbol, sig, qty, entry_price, sl_price, tp_price)

        self.positions[symbol] = Position(
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
        if self.telegram:
            side_str = "LONG" if sig == 1 else "SHORT"
            self.telegram.send(
                f"🟢 {symbol} ENTER {side_str}\n"
                f"Entry: ${entry_price:.2f}\n"
                f"Qty: {qty:.6f}\n"
                f"SL: ${sl_price:.2f} | TP: ${tp_price:.2f}"
            )

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
            logger.warning(f"Max daily loss hit ({daily_loss:.1f}% >= {max_daily}%)")
            if self.telegram:
                self.telegram.send(
                    f"⚠️ Max daily loss triggered!\n"
                    f"Daily loss: {daily_loss:.1f}% (limit: {max_daily}%)"
                )
        max_dd = self.config.get("max_drawdown_pct", 20.0)
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd >= max_dd:
            logger.warning(f"Max drawdown hit ({dd:.1f}% >= {max_dd}%)")
            if self.telegram:
                self.telegram.send(
                    f"⚠️ Max drawdown triggered!\n"
                    f"Drawdown: {dd:.1f}% (limit: {max_dd}%)"
                )

    def _save_state(self):
        self.config["capital"] = round(self.executor.equity, 2)
        positions_raw = {}
        for sym in self.symbols:
            pos = self.positions.get(sym)
            positions_raw[sym] = pos.to_dict() if pos else None
        self.config["positions"] = positions_raw

        candle_times = {}
        for sym in self.symbols:
            t = self.last_candle_times.get(sym)
            candle_times[sym] = str(t) if t else None
        self.config["last_candle_times"] = candle_times
        save_config(self.config)
