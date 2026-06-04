import json
from dataclasses import asdict
from pathlib import Path

from huntbot.config import STATE_DIR
from huntbot.models import StrategyConfig
from huntbot.strategy import CycleState


STRATEGY_PATH = STATE_DIR / "strategy.json"
CYCLE_PATH = STATE_DIR / "cycle.json"


def save_strategy(strategy: StrategyConfig, path: Path = STRATEGY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(strategy), indent=2), encoding="utf-8")


def load_strategy(path: Path = STRATEGY_PATH) -> StrategyConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return StrategyConfig(**data)


def save_cycle(cycle: CycleState, path: Path = CYCLE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cycle), indent=2), encoding="utf-8")


def load_cycle(path: Path = CYCLE_PATH) -> CycleState:
    if not path.exists():
        return CycleState(ready=True)
    data = json.loads(path.read_text(encoding="utf-8"))
    return CycleState(**data)
