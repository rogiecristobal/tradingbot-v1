import logging
from typing import Optional

from exchange.connector import build_exchange

logger = logging.getLogger(__name__)


class PaperExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.equity = config.get("capital", 10000.0)

    def place_market_entry(self, symbol: str, side: int, qty: float,
                           entry_price: float, sl: float, tp: float) -> dict:
        fee = entry_price * qty * 0.001
        self.equity -= fee
        logger.info(
            f"[PAPER] {symbol} ENTER {'LONG' if side == 1 else 'SHORT'} "
            f"qty={qty:.6f} @ {entry_price:.2f} "
            f"SL={sl:.2f} TP={tp:.2f} fee=${fee:.2f}"
        )
        return {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "fee": fee,
        }

    def place_market_close(self, symbol: str, side: int, qty: float,
                           exit_price: float) -> dict:
        fee = exit_price * qty * 0.001
        self.equity -= fee
        logger.info(
            f"[PAPER] {symbol} EXIT {'LONG' if side == 1 else 'SHORT'} "
            f"qty={qty:.6f} @ {exit_price:.2f} fee=${fee:.2f}"
        )
        return {"symbol": symbol, "side": side, "qty": qty, "price": exit_price, "fee": fee}


class LiveExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.equity = config.get("capital", 100.0)
        self.ex = build_exchange(
            config["exchange_id"],
            config.get("api_key", ""),
            config.get("api_secret", ""),
        )
        if self.ex is None:
            raise RuntimeError(f"Failed to build {config['exchange_id']} exchange")
        if config.get("api_key"):
            self.ex.load_markets()
        self._setup_derivatives()

    def _setup_derivatives(self):
        symbols = self.config.get("symbols", [])
        leverage = self.config.get("leverage", 1)
        for sym in symbols:
            try:
                self.ex.set_leverage(leverage, sym)
            except Exception:
                pass
            try:
                self.ex.set_margin_mode("cross", sym)
            except Exception:
                pass
        logger.info(f"[LIVE] Leverage {leverage}x, cross margin set for {len(symbols)} symbols")

    def place_market_entry(self, symbol: str, side: int, qty: float,
                           entry_price: float, sl: float, tp: float) -> dict:
        side_str = "buy" if side == 1 else "sell"
        params = {
            "positionIdx": 0,
            "stopLoss": {
                "triggerPrice": sl,
                "orderPrice": sl,
                "type": "Market",
            },
            "takeProfit": {
                "triggerPrice": tp,
                "orderPrice": tp,
                "type": "Market",
            },
        }
        order = self.ex.create_order(symbol, "market", side_str, qty, None, params)
        filled_price = order.get("average", order.get("price", entry_price))
        logger.info(
            f"[LIVE] {symbol} ENTER {side_str.upper()} qty={qty:.6f} @ {filled_price:.2f} "
            f"SL={sl:.2f} TP={tp:.2f}"
        )
        return order

    def place_market_close(self, symbol: str, side: int, qty: float,
                           exit_price: float) -> dict:
        side_str = "sell" if side == 1 else "buy"
        try:
            self.ex.cancel_all_orders(symbol)
        except Exception:
            pass
        order = self.ex.create_market_order(symbol, side_str, qty)
        logger.info(
            f"[LIVE] {symbol} EXIT {side_str.upper()} qty={qty:.6f} @ "
            f"{order.get('average', exit_price):.2f}"
        )
        return order


def build_executor(config: dict):
    mode = config.get("mode", "paper")
    if mode == "live":
        return LiveExecutor(config)
    return PaperExecutor(config)
