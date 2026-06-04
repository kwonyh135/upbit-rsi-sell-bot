from huntbot.models import StrategyConfig
from huntbot.state import load_cycle, load_strategy, save_cycle, save_strategy
from huntbot.strategy import CycleState


def test_strategy_round_trips_to_json(tmp_path):
    path = tmp_path / "strategy.json"
    strategy = StrategyConfig("KRW-HUNT", 60, 14, 75.0, 68.0)
    save_strategy(strategy, path)
    assert load_strategy(path) == strategy


def test_missing_cycle_defaults_to_ready(tmp_path):
    assert load_cycle(tmp_path / "missing.json") == CycleState(ready=True)


def test_cycle_round_trips_to_json(tmp_path):
    path = tmp_path / "cycle.json"
    save_cycle(CycleState(ready=False), path)
    assert load_cycle(path) == CycleState(ready=False)
