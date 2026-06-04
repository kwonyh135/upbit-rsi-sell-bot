import argparse
from decimal import Decimal

from huntbot.backtest import run_candidate_search
from huntbot.config import MARKET, RSI_PERIOD, load_environment
from huntbot.market_data import fetch_recent_candles
from huntbot.models import StrategyConfig
from huntbot.state import save_strategy
from huntbot.upbit_client import UpbitClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huntbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backtest")

    select = subparsers.add_parser("select")
    select.add_argument("--unit", type=int, required=True)
    select.add_argument("--sell-rsi", type=float, required=True)
    select.add_argument("--reset-rsi", type=float, required=True)

    watch = subparsers.add_parser("watch")
    mode = watch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    watch.add_argument("--loop", action="store_true")
    return parser


def main() -> int:
    load_environment()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        return run_backtest_command()
    if args.command == "select":
        strategy = StrategyConfig(
            market=MARKET,
            unit=args.unit,
            rsi_period=RSI_PERIOD,
            sell_rsi=args.sell_rsi,
            reset_rsi=args.reset_rsi,
        )
        save_strategy(strategy)
        print(f"Saved strategy: unit={args.unit}, sell_rsi={args.sell_rsi}, reset_rsi={args.reset_rsi}")
        return 0
    print("watch command will be implemented in the trader task")
    return 0


def run_backtest_command() -> int:
    client = UpbitClient()
    pages_by_unit = {60: 22, 15: 88, 5: 264}
    candles_by_unit = {
        unit: fetch_recent_candles(client, MARKET, unit=unit, pages=pages)
        for unit, pages in pages_by_unit.items()
    }
    results = run_candidate_search(candles_by_unit)
    print("unit sell_rsi reset_rsi return_pct final_value sells cash remaining_hunt max_dd")
    for result in results[:20]:
        print(
            f"{result.unit} {result.sell_rsi:.1f} {result.reset_rsi:.1f} "
            f"{result.final_return_pct:.2f} {result.final_total_value.quantize(Decimal('1'))} "
            f"{result.sell_count} {result.cash.quantize(Decimal('1'))} "
            f"{result.remaining_quantity:.8f} {result.max_drawdown_pct:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
