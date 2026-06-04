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


def load_environment() -> None:
    load_dotenv()
