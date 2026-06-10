import importlib
from pathlib import Path

from huntbot.dashboard_app import next_action_text


def test_dashboard_module_import_has_no_runtime_side_effects():
    module = importlib.import_module("huntbot.dashboard_app")
    assert callable(module.main)


def test_next_action_text_matches_strategy_phase():
    assert "RSI 45" in next_action_text("buy_1")
    assert "RSI 40" in next_action_text("buy_2")
    assert "RSI 60" in next_action_text("buy_2")
    assert "RSI 65" in next_action_text("sell_2")
    assert "중단" in next_action_text("emergency_halt")


def test_dashboard_source_has_no_trading_or_state_mutation_calls():
    source = Path("huntbot/dashboard_app.py").read_text(encoding="utf-8")
    for forbidden in (
        "market_buy(",
        "market_sell(",
        "save_auto_state(",
        "unlock_emergency(",
        "run_auto_service(",
    ):
        assert forbidden not in source


def test_dashboard_launcher_is_localhost_only():
    script = Path("scripts/start-dashboard.ps1").read_text(encoding="utf-8")
    assert "--server.address 127.0.0.1" in script
    assert "--server.headless true" in script
