"""
Test server-side SL/TP with a small real order on Bybit.
Usage: pipenv run python test_server_sl_tp.py
"""
import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

with open("config.json") as f:
    config = json.load(f)

symbol = "DOGE/USDT:USDT"
usd_amount = 1.0
sl_pct = 0.005
tp_pct = 0.005

from exchange.connector import build_exchange

ex = build_exchange(
    config["exchange_id"],
    config.get("api_key", ""),
    config.get("api_secret", ""),
)
if ex is None:
    logger.error("Failed to build exchange")
    sys.exit(1)

ex.load_markets()
market = ex.market(symbol)
logger.info(f"Market loaded for {symbol}")

min_qty = market["limits"]["amount"]["min"]
min_cost = market["limits"]["cost"]["min"] if market["limits"]["cost"] else 0
step = market["precision"]["amount"]
logger.info(f"Min qty: {min_qty}, Min cost: {min_cost}, Step: {step}")

ticker = ex.fetch_ticker(symbol)
price = ticker["last"]
logger.info(f"Current {symbol} price: {price}")

qty = usd_amount / price
logger.info(f"Raw qty for ${usd_amount}: {qty:.8f}")

if min_cost and usd_amount < min_cost:
    logger.warning(f"${usd_amount} is below min cost ${min_cost}")
    viable_amount = min_cost * 1.1
    qty = viable_amount / price
    logger.info(f"Using viable amount ${viable_amount:.2f} -> qty {qty:.8f}")

qty = float(ex.amount_to_precision(symbol, qty))

if qty < min_qty:
    logger.error(f"qty {qty} below minimum {min_qty}, cannot proceed")
    sys.exit(1)

logger.info(f"Final qty: {qty}")

logger.info("Setting leverage=1, margin=cross")
try:
    ex.set_leverage(1, symbol)
except Exception:
    logger.warning("Leverage set failed (may already be set)")
try:
    ex.set_margin_mode("cross", symbol)
except Exception as e:
    logger.warning(f"Margin mode set failed: {e}")

entry_price = float(ex.price_to_precision(symbol, price))
sl_price = float(ex.price_to_precision(symbol, price * (1 - sl_pct)))
tp_price = float(ex.price_to_precision(symbol, price * (1 + tp_pct)))
logger.info(f"Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")

print(f"\n{'='*60}")
print(f"ABOUT TO PLACE REAL ORDER ON BYBIT")
print(f"Symbol: {symbol}")
print(f"Side: BUY")
print(f"Qty: {qty}")
print(f"Entry ~${entry_price}")
print(f"SL: ${sl_price} ({sl_pct*100:.1f}% below)")
print(f"TP: ${tp_price} ({tp_pct*100:.1f}% above)")
print(f"Estimated cost: ${qty * entry_price:.2f}")
print(f"{'='*60}")

params = {
    "positionIdx": 0,
    "stopLoss": {
        "triggerPrice": sl_price,
        "orderPrice": sl_price,
        "type": "Market",
    },
    "takeProfit": {
        "triggerPrice": tp_price,
        "orderPrice": tp_price,
        "type": "Market",
    },
}

try:
    order = ex.create_order(symbol, "market", "buy", qty, None, params)
    logger.info(f"Order placed: {json.dumps(order, indent=2, default=str)}")
except Exception as e:
    logger.error(f"Order failed: {e}", exc_info=True)
    sys.exit(1)

time.sleep(3)
try:
    positions = ex.fetch_positions([symbol])
    for p in positions:
        info = {
            "symbol": p["symbol"],
            "side": p["side"],
            "contracts": p["contracts"],
            "unrealizedPnl": p["unrealizedPnl"],
            "entryPrice": p["entryPrice"],
            "liquidationPrice": p["liquidationPrice"],
        }
        logger.info(f"Position: {json.dumps(info, indent=2, default=str)}")
except Exception as e:
    logger.warning(f"Could not fetch position: {e}")

logger.info("Closing position in 5 seconds...")
time.sleep(5)

logger.info("Cancelling stale orders and closing...")
try:
    ex.cancel_all_orders(symbol)
except Exception:
    pass

try:
    close_order = ex.create_market_order(symbol, "sell", qty)
    logger.info(f"Close order: {json.dumps(close_order, indent=2, default=str)}")
except Exception as e:
    logger.error(f"Close failed: {e}")

logger.info("Done.")
