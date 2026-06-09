from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_configures_live_task_and_restart_policy():
    text = (ROOT / "scripts" / "install-auto-task.ps1").read_text(encoding="utf-8")
    assert "HuntBot-Auto-5m" in text
    assert "run-auto-5m --live" in text
    assert "MultipleInstances" in text
    assert "RestartCount" in text
    assert "RestartInterval" in text
    assert "codex-primary-runtime" in text


def test_remove_script_targets_only_huntbot_task():
    text = (ROOT / "scripts" / "remove-auto-task.ps1").read_text(encoding="utf-8")
    assert 'Unregister-ScheduledTask -TaskName "HuntBot-Auto-5m"' in text
