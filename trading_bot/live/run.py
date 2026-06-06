import logging
import os
import signal
import sys

from live.config import load_config
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
    print(f"┌──────────────────────────────────────────────┐")
    print(f"│  Crypto Trading Bot — ATR Trend-Breakout     │")
    print(f"│  Exchange: {config['exchange_id']:<29s}│")
    print(f"│  Symbol:   {config['symbol']:<29s}│")
    print(f"│  Mode:     {mode.upper():<29s}│")
    print(f"│  Capital:  ${config.get('capital', 10000):>8.2f}            │")
    if mode == "paper":
        print(f"│  ⚠  PAPER MODE — no real orders will be placed │")
    else:
        print(f"│  ⚠  LIVE MODE — real money trading!          │")
    print(f"└──────────────────────────────────────────────┘")

    engine = LiveEngine(config)

    def shutdown(sig, frame):
        logger.info("Shutdown signal received, exiting...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    engine.start()


if __name__ == "__main__":
    main()
