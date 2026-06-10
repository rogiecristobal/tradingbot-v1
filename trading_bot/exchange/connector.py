import logging
import time

logger = logging.getLogger(__name__)


def get_exchange_names():
    import ccxt
    return sorted(ccxt.exchanges)


def build_exchange(exchange_id: str, api_key: str = "", api_secret: str = "", retries: int = 3):
    import ccxt
    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        logger.error(f"Unknown exchange: {exchange_id}")
        return None
    config = {"enableRateLimit": True}
    if api_key:
        config["apiKey"] = api_key
    if api_secret:
        config["secret"] = api_secret
    for attempt in range(1, retries + 1):
        try:
            ex = exchange_class(config)
            if not api_key:
                ex.load_markets()
            return ex
        except Exception as e:
            if attempt < retries:
                logger.warning(f"Failed to init {exchange_id} (attempt {attempt}/{retries}): {e}")
                time.sleep(2)
            else:
                logger.error(f"Failed to initialize {exchange_id} after {retries} attempts: {e}")
                return None


def validate_credentials(exchange_id: str, api_key: str, api_secret: str) -> bool:
    if not api_key or not api_secret:
        return False
    try:
        ex = build_exchange(exchange_id, api_key, api_secret)
        if ex is None:
            return False
        ex.fetch_balance()
        return True
    except Exception:
        return False


def get_markets(exchange_id: str, api_key: str = "", api_secret: str = ""):
    ex = build_exchange(exchange_id, api_key, api_secret)
    if ex is None:
        return []
    try:
        ex.load_markets()
        symbols = [s for s in ex.symbols if "/" in s and ("USDT" in s or "USD" in s)]
        return sorted(symbols)
    except Exception:
        return sorted(ex.symbols) if hasattr(ex, "symbols") else []
