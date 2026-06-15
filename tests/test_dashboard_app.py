import importlib
from pathlib import Path

from huntbot.dashboard_app import (
    chart_domain,
    next_action_text,
    resolve_runtime_paths,
)


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
    assert '.venv\\Scripts\\python.exe' in script
    assert "codex-primary-runtime" not in script


def test_dashboard_uses_manual_refresh_and_combines_charts_with_performance():
    source = Path("huntbot/dashboard_app.py").read_text(encoding="utf-8")

    assert 'st.button("새로고침"' in source
    assert "run_every=" not in source
    assert '["거래 및 성과", "계산 기준"]' in source
    assert 'elif view == "차트"' not in source


def test_chart_domain_adds_padding_without_forcing_zero():
    assert chart_domain([118, 120, 122]) == (117.6, 122.4)
    assert chart_domain([100, 100]) == (99.0, 101.0)
    assert chart_domain([], fallback=(0, 1)) == (0, 1)


def test_price_chart_uses_candles_and_uniform_trade_points_with_tooltips():
    source = Path("huntbot/dashboard_app.py").read_text(encoding="utf-8")

    assert "mark_rule" in source
    assert "mark_bar" in source
    assert "mark_circle" in source
    assert "shape=alt.Shape" not in source
    assert '"매도 전 평단가:Q"' in source
    assert '"해당 매도 실현손익:Q"' in source
    assert 'curve["누적 실현손익"] = curve["누적 실현손익"].astype(float)' in source


def test_runtime_paths_prefer_complete_downloaded_aws_runtime(tmp_path):
    remote = tmp_path / "remote"
    state = remote / "state" / "auto-trading.json"
    log = remote / "logs" / "huntbot-auto.log"
    state.parent.mkdir(parents=True)
    log.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")
    log.write_text("", encoding="utf-8")

    paths = resolve_runtime_paths(
        remote_root=remote,
        local_state=tmp_path / "local-state.json",
        local_log=tmp_path / "local.log",
    )

    assert paths.source == "aws-download"
    assert paths.state_path == state
    assert paths.log_path == log
    assert paths.process_running is True


def test_runtime_paths_fall_back_when_remote_download_is_incomplete(tmp_path):
    remote = tmp_path / "remote"
    state = remote / "state" / "auto-trading.json"
    state.parent.mkdir(parents=True)
    state.write_text("{}", encoding="utf-8")
    local_state = tmp_path / "local-state.json"
    local_log = tmp_path / "local.log"

    paths = resolve_runtime_paths(
        remote_root=remote,
        local_state=local_state,
        local_log=local_log,
    )

    assert paths.source == "local"
    assert paths.state_path == local_state
    assert paths.log_path == local_log
    assert paths.process_running is None
