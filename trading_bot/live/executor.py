import logging
from typing import Optional

from exchange.connector import build_exchange

logger = logging.getLogger(__name__)


class PaperExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.equity = config.get("capital", 10000.0)

    def place_market_entry(self, side: int, qty: float,
                           entry_price: float, sl: float, tp: float) -> dict:
        fee = entry_price * qty * 0.001
        self.equity -= fee
        logger.info(
            f"[PAPER] ENTER {'LONG' if side == 1 else 'SHORT'} "
            f"qty={qty:.6f} @ {entry_price:.2f} "
            f"SL={sl:.2f} TP={tp:.2f} fee=${fee:.2f}"
        )
        return {
            "side": side,
            "qty": qty,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "fee": fee,
        }

    def place_market_close(self, side: int, qty: float,
                           exit_price: float) -> dict:
        fee = exit_price * qty * 0.001
        self.equity -= fee
        logger.info(
            f"[PAPER] EXIT {'LONG' if side == 1 else 'SHORT'} "
            f"qty={qty:.6f} @ {exit_price:.2f} fee=${fee:.2f}"
        )
        return {"side": side, "qty": qty, "price": exit_price, "fee": fee}


class LiveExecutor:
    def __init__(self, config: dict):
        self.config = config
        self.ex = build_exchange(
            config["exchange_id"],
            config.get("api_key", ""),
            config.get("api_secret", ""),
        )
        if self.ex is None:
            raise RuntimeError(f"Failed to build {config['exchange_id']} exchange")
        if config.get("api_key"):
            self.ex.load_markets()

    def place_market_entry(self, side: int, qty: float,
                           entry_price: float, sl: float, tp: float) -> dict:
        symbol = self.config["symbol"]
        side_str = "buy" if side == 1 else "sell"
        order = self.ex.create_market_order(symbol, side_str, qty)
        filled_price = order.get("average", order.get("price", entry_price))
        logger.info(
            f"[LIVE] ENTER {side_str.upper()} qty={qty:.6f} @ {filled_price:.2f} "
            f"SL={sl:.2f} TP={tp:.2f}"
        )
        return order

    def place_market_close(self, side: int, qty: float,
                           exit_price: float) -> dict:
        symbol = self.config["symbol"]
        side_str = "sell" if side == 1 else "buy"
        order = self.ex.create_market_order(symbol, side_str, qty)
        logger.info(
            f"[LIVE] EXIT {side_str.upper()} qty={qty:.6f} @ "
            f"{order.get('average', exit_price):.2f}"
        )
        return order


def build_executor(config: dict):
    mode = config.get("mode", "paper")
    if mode == "live":
        return LiveExecutor(config)
    return PaperExecutor(config)
