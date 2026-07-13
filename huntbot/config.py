from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv


MARKET = "KRW-HUNT"
RSI_PERIOD = 14
INITIAL_BACKTEST_KRW = 3_000_000
MIN_HOLDING_VALUE_KRW = 500_000
DEFAULT_SERVER_URL = "https://api.upbit.com"
DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "cache"
STATE_DIR = DATA_DIR / "state"
LOG_DIR = Path("logs")
AUTO_STATE_PATH = STATE_DIR / "auto-trading.json"
AUTO_DRY_RUN_STATE_PATH = STATE_DIR / "auto-trading-dry-run.json"
AUTO_LOCK_PATH = STATE_DIR / "auto-trading.lock"
EMERGENCY_HIGH_DROP_PCT = Decimal("6")
EMERGENCY_AVG_LOSS_PCT = Decimal("12")
EMERGENCY_CONFIRMATIONS = 2
AUTO_POLL_SECONDS = 10
AUTO_RSI_HOLD_SECONDS = 30
AUTO_RSI_MAX_GAP_SECONDS = 20
SELL_RSI_1 = 56
SELL_RSI_2 = 61
BUY_RSI_1 = 45
BUY_RSI_2 = 40
EMERGENCY_FLOOR_PRICE_KRW = Decimal("114")


def load_environment() -> None:
    load_dotenv()
