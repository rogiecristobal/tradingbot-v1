import logging
import os
import signal
import sys

from exchange.connector import build_exchange
from live.config import load_config, allocate_capital
from live.engine import LiveEngine

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "live", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log")),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("run")


def main():
    config = load_config()
    mode = config.get("mode", "paper")
    symbols = config.get("symbols", [])
    capital = config.get("capital", 100.0)

    has_keys = bool(config.get("api_key") and config.get("api_secret"))

    balance = None
    if has_keys:
        try:
            ex = build_exchange(
                config["exchange_id"],
                config.get("api_key", ""),
                config.get("api_secret", ""),
            )
            if ex:
                bal = ex.fetch_balance()
                usdt = bal.get("USDT", {})
                total = float(usdt.get("total", 0) or 0)
                if total > 0:
                    balance = total
        except Exception:
            pass

    display_capital = balance if balance is not None else capital
    allocations = allocate_capital(symbols, display_capital)

    print(f"┌──────────────────────────────────────────────┐")
    print(f"│  Crypto Trading Bot — ATR Trend-Breakout     │")
    print(f"│  Exchange: {config['exchange_id']:<29s}│")
    print(f"│  Mode:     {mode.upper():<29s}│")
    print(f"│  Keys:     {'Loaded from .env' if has_keys else 'Not set (public only)'}")
    print(f"│  On-chain Balance:  ${display_capital:>8.2f}               │")
    print(f"│  Symbols:  {len(symbols)} total                      │")
    print(f"│  Alloc:    ${display_capital/len(symbols):>7.2f} per symbol              │")
    print(f"├──────────────────────────────────────────────┤")
    for sym in symbols[:5]:
        alloc = allocations.get(sym, 0)
        print(f"│  {sym:<20s}  ${alloc:>7.2f}                 │")
    if len(symbols) > 5:
        print(f"│  ... and {len(symbols) - 5} more                         │")
    print(f"├──────────────────────────────────────────────┤")
    if mode == "paper":
        print(f"│  ⚠  PAPER MODE — no real orders will be placed │")
    else:
        print(f"│  ⚠  LIVE MODE — real money trading!          │")
    print(f"└──────────────────────────────────────────────┘")

    engine = LiveEngine(config)
    if display_capital > 0:
        engine.executor.equity = display_capital
        engine.peak_equity = display_capital
        engine.daily_start_equity = display_capital

    def shutdown(sig, frame):
        logger.info("Shutdown signal received, exiting...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    engine.start()


if __name__ == "__main__":
    main()
