import argparse
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from huntbot.backtest import run_buyback_candidate_search, run_candidate_search, run_split_buyback_backtest, run_split_buyback_candidate_search
from huntbot.crash_backtest import run_crash_study
from huntbot.crash_reporting import render_crash_study_markdown, study_to_json
from huntbot.auto_service import SingleInstanceLock, run_auto_service, unlock_emergency
from huntbot.auto_state import AUTO_STATE_PATH
from huntbot.config import MARKET, RSI_PERIOD, load_environment
from huntbot.indicators import rsi
from huntbot.market_data import fetch_recent_candles, load_candle_snapshot, prepare_study_candles, save_candle_snapshot
from huntbot.models import StrategyConfig
from huntbot.reporting import render_split_buyback_report
from huntbot.state import load_strategy, save_strategy
from huntbot.trader import (
    BUY_CONFIRMATION,
    BUYBACK_BUY_RSI_1,
    BUYBACK_BUY_RSI_2,
    BUYBACK_SELL_RSI_1,
    BUYBACK_SELL_RSI_2,
    LIVE_CONFIRMATION,
    load_buyback_state,
    required_buyback_confirmation,
    run_buyback_watch_once,
    run_watch_once,
    sync_buyback_state,
)
from huntbot.upbit_client import UpbitClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huntbot")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backtest")
    subparsers.add_parser("backtest-buyback")
    subparsers.add_parser("backtest-split-buyback")
    subparsers.add_parser("report-split-5m")
    crash_backtest = subparsers.add_parser("backtest-crash-5m")
    crash_backtest.add_argument("--snapshot")
    subparsers.add_parser("sync-buyback-state")
    run_auto = subparsers.add_parser("run-auto-5m")
    auto_mode = run_auto.add_mutually_exclusive_group(required=True)
    auto_mode.add_argument("--dry-run", action="store_true")
    auto_mode.add_argument("--live", action="store_true")
    run_auto.add_argument("--once", action="store_true")
    subparsers.add_parser("unlock-emergency")

    select = subparsers.add_parser("select")
    select.add_argument("--unit", type=int, required=True)
    select.add_argument("--sell-rsi", type=float, required=True)
    select.add_argument("--reset-rsi", type=float, required=True)

    watch = subparsers.add_parser("watch")
    mode = watch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    watch.add_argument("--loop", action="store_true")

    watch_buyback = subparsers.add_parser("watch-buyback-5m")
    buyback_mode = watch_buyback.add_mutually_exclusive_group(required=True)
    buyback_mode.add_argument("--dry-run", action="store_true")
    buyback_mode.add_argument("--live", action="store_true")
    watch_buyback.add_argument("--loop", action="store_true")
    return parser


def main() -> int:
    load_environment()
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        return run_backtest_command()
    if args.command == "backtest-buyback":
        return run_buyback_backtest_command()
    if args.command == "backtest-split-buyback":
        return run_split_buyback_backtest_command()
    if args.command == "report-split-5m":
        return run_split_5m_report_command()
    if args.command == "backtest-crash-5m":
        return run_crash_5m_command(snapshot=args.snapshot)
    if args.command == "sync-buyback-state":
        return run_sync_buyback_state_command()
    if args.command == "run-auto-5m":
        if args.live and args.once:
            parser.error("--once is available only with --dry-run")
        with SingleInstanceLock():
            return run_auto_service(client=UpbitClient(), live=args.live, once=args.once)
    if args.command == "unlock-emergency":
        print("Emergency unlock confirmation required. Type exactly: UNLOCK KRW-HUNT")
        state = unlock_emergency(state_path=AUTO_STATE_PATH, confirmation=input("> ").strip())
        print(f"Emergency halt cleared. phase={state.phase}")
        return 0
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
    if args.command == "watch":
        return run_watch_command(live=args.live, loop=args.loop)
    if args.command == "watch-buyback-5m":
        return run_buyback_watch_command(live=args.live, loop=args.loop)
    raise RuntimeError(f"unsupported command: {args.command}")


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


def run_buyback_backtest_command() -> int:
    client = UpbitClient()
    pages_by_unit = {60: 22, 15: 88, 5: 264}
    candles_by_unit = {
        unit: fetch_recent_candles(client, MARKET, unit=unit, pages=pages)
        for unit, pages in pages_by_unit.items()
    }
    results = run_buyback_candidate_search(candles_by_unit)
    print("unit sell_rsi buy_rsi return_pct final_value sells buys cash remaining_hunt max_dd")
    for result in results[:30]:
        print(
            f"{result.unit} {result.sell_rsi:.1f} {result.buy_rsi:.1f} "
            f"{result.final_return_pct:.2f} {result.final_total_value.quantize(Decimal('1'))} "
            f"{result.sell_count} {result.buy_count} {result.cash.quantize(Decimal('1'))} "
            f"{result.remaining_quantity:.8f} {result.max_drawdown_pct:.2f}"
        )
    print("")
    print("best_by_unit")
    print("unit sell_rsi buy_rsi return_pct final_value sells buys cash remaining_hunt max_dd")
    for unit in [60, 15, 5]:
        best = next(result for result in results if result.unit == unit)
        print(
            f"{best.unit} {best.sell_rsi:.1f} {best.buy_rsi:.1f} "
            f"{best.final_return_pct:.2f} {best.final_total_value.quantize(Decimal('1'))} "
            f"{best.sell_count} {best.buy_count} {best.cash.quantize(Decimal('1'))} "
            f"{best.remaining_quantity:.8f} {best.max_drawdown_pct:.2f}"
        )
    return 0


def run_split_buyback_backtest_command() -> int:
    client = UpbitClient()
    pages_by_unit = {60: 22, 15: 88, 5: 264}
    end_at_utc = "2026-06-07T14:59:59"
    candles_by_unit = {
        unit: fetch_recent_candles(client, MARKET, unit=unit, pages=pages, to=end_at_utc)
        for unit, pages in pages_by_unit.items()
    }
    results = run_split_buyback_candidate_search(candles_by_unit)
    print("fee_rate 0.0005")
    print("slippage_rate 0.0005")
    print("data_through_kst 2026-06-07 23:59:59")
    print("unit sell1 sell2 buy1 buy2 return_pct final_value sells buys cash remaining_hunt max_dd")
    for result in results[:30]:
        print(
            f"{result.unit} {result.sell_rsi_1:.1f} {result.sell_rsi_2:.1f} "
            f"{result.buy_rsi_1:.1f} {result.buy_rsi_2:.1f} "
            f"{result.final_return_pct:.2f} {result.final_total_value.quantize(Decimal('1'))} "
            f"{result.sell_count} {result.buy_count} {result.cash.quantize(Decimal('1'))} "
            f"{result.remaining_quantity:.8f} {result.max_drawdown_pct:.2f}"
        )
    print("")
    print("best_by_unit")
    print("unit sell1 sell2 buy1 buy2 return_pct final_value sells buys cash remaining_hunt max_dd")
    for unit in [60, 15, 5]:
        best = next(result for result in results if result.unit == unit)
        print(
            f"{best.unit} {best.sell_rsi_1:.1f} {best.sell_rsi_2:.1f} "
            f"{best.buy_rsi_1:.1f} {best.buy_rsi_2:.1f} "
            f"{best.final_return_pct:.2f} {best.final_total_value.quantize(Decimal('1'))} "
            f"{best.sell_count} {best.buy_count} {best.cash.quantize(Decimal('1'))} "
            f"{best.remaining_quantity:.8f} {best.max_drawdown_pct:.2f}"
        )
    return 0


def run_split_5m_report_command() -> int:
    client = UpbitClient()
    end_at_utc = "2026-06-07T14:59:59"
    candles = fetch_recent_candles(client, MARKET, unit=5, pages=264, to=end_at_utc)
    result = run_split_buyback_backtest(
        candles,
        sell_rsi_1=60.0,
        sell_rsi_2=65.0,
        buy_rsi_1=45.0,
        buy_rsi_2=40.0,
    )
    output_path = Path("docs/split-buyback-events-5m.html")
    render_split_buyback_report(
        result=result,
        output_path=output_path,
        data_through_kst="2026-06-07 23:59:59",
        fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"),
        recent_days=90,
    )
    print(f"Wrote {output_path}")
    print(
        f"summary unit=5 sell=60/65 buy=45/40 return={result.final_return_pct:.2f}% "
        f"final_value={result.final_total_value.quantize(Decimal('1'))} events={len(result.events)}"
    )
    return 0


def run_sync_buyback_state_command() -> int:
    client = UpbitClient()
    before = load_buyback_state()
    result = sync_buyback_state(client=client)
    after = load_buyback_state()
    print(
        f"mode=5m_buyback_sync phase_before={before.phase} phase_after={after.phase} "
        f"action={result.action} available_hunt={result.available_quantity} "
        f"amount={result.sell_quantity} order_uuid={result.order_uuid}"
    )
    return 0


def run_crash_5m_command(*, snapshot: str | None) -> int:
    now = datetime.now(timezone.utc)
    if snapshot:
        candles = load_candle_snapshot(Path(snapshot))
    else:
        print("Downloading public KRW-HUNT five-minute candles...")
        candles = fetch_recent_candles(UpbitClient(), MARKET, unit=5, pages=264)
    candles = prepare_study_candles(candles, now=now, preserve_snapshot=bool(snapshot))
    if len(candles) < 15:
        raise RuntimeError("not enough completed candles for crash backtest")

    snapshot_path = Path("data/backtests/krw-hunt-5m-latest.csv")
    result_path = Path("data/backtests/crash-study-latest.json")
    report_path = Path("docs/crash-protection-backtest-latest.md")
    save_candle_snapshot(candles, snapshot_path)
    metadata = {
        "market": MARKET,
        "first_candle": candles[0].timestamp.isoformat(),
        "last_candle": candles[-1].timestamp.isoformat(),
        "candle_count": len(candles),
        "missing_intervals": _missing_intervals(candles),
        "downloaded_at": now.isoformat(),
    }
    study = run_crash_study(candles, progress=lambda message: print(f"[study] {message}"))
    report_path.write_text(render_crash_study_markdown(study, metadata), encoding="utf-8", newline="\n")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(study_to_json(study, metadata), encoding="utf-8", newline="\n")
    print(f"Snapshot: {snapshot_path}")
    print(f"Results: {result_path}")
    print(f"Report: {report_path}")
    return 0


def _missing_intervals(candles) -> int:
    missing = 0
    for previous, current in zip(candles, candles[1:]):
        elapsed = int((current.timestamp - previous.timestamp).total_seconds() // 300)
        missing += max(0, elapsed - 1)
    return missing


def run_watch_command(*, live: bool, loop: bool) -> int:
    client = UpbitClient()
    while True:
        strategy = load_strategy()
        candles = fetch_recent_candles(client, strategy.market, unit=strategy.unit, pages=1)
        current_rsi = rsi([float(candle.close) for candle in candles], period=strategy.rsi_period)[-1]
        current_price = candles[-1].close
        confirm_phrase = None
        if live:
            print(f"Live order confirmation required. Type exactly: {LIVE_CONFIRMATION}")
            confirm_phrase = input("> ").strip()
        result = run_watch_once(
            client=client,
            strategy=strategy,
            rsi_value=current_rsi,
            current_price=current_price,
            live=live,
            confirm_phrase=confirm_phrase,
        )
        print(
            f"action={result.action} rsi={result.rsi_value} "
            f"holding_value={result.holding_value.quantize(Decimal('1'))} "
            f"available_hunt={result.available_quantity} sell_quantity={result.sell_quantity} "
            f"order_uuid={result.order_uuid}"
        )
        if not loop:
            return 0
        time.sleep(60)


def run_buyback_watch_command(*, live: bool, loop: bool) -> int:
    client = UpbitClient()
    while True:
        candles = fetch_recent_candles(client, MARKET, unit=5, pages=1)
        current_rsi = rsi([float(candle.close) for candle in candles], period=RSI_PERIOD)[-1]
        current_price = candles[-1].close
        state = load_buyback_state()
        accounts = client.get_accounts() if live else None
        confirm_phrase = None
        if live:
            required = required_buyback_confirmation(state, accounts or [], rsi_value=current_rsi)
            if required:
                print(f"Live order confirmation required. Type exactly: {required}")
                confirm_phrase = input("> ").strip()
        result = run_buyback_watch_once(
            client=client,
            rsi_value=current_rsi,
            current_price=current_price,
            live=live,
            confirm_phrase=confirm_phrase,
            state=state,
            accounts=accounts,
        )
        print(
            f"mode=5m_buyback sell_rsi={BUYBACK_SELL_RSI_1:.0f}/{BUYBACK_SELL_RSI_2:.0f} "
            f"buy_rsi={BUYBACK_BUY_RSI_1:.0f}/{BUYBACK_BUY_RSI_2:.0f} "
            f"phase={state.phase} action={result.action} rsi={result.rsi_value} "
            f"price={current_price} holding_value={result.holding_value.quantize(Decimal('1'))} "
            f"available_hunt={result.available_quantity} amount={result.sell_quantity} "
            f"order_uuid={result.order_uuid}"
        )
        if not loop:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
