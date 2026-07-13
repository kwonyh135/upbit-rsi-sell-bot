from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "sync-aws-runtime.ps1"


def test_sync_script_downloads_only_allowlisted_runtime_files():
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]" in text
    assert "$HostName" in text
    assert "$KeyPath" in text
    assert "/data/state/auto-trading.json" in text
    assert "/logs/huntbot-auto.log*" in text
    assert "data\\remote-runtime" in text
    assert "scp" in text
    assert "LASTEXITCODE" in text
    assert ".staging-" in text
    assert "Move-Item" in text
    assert "shared/.env" not in text


def test_remote_runtime_directory_is_git_ignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/remote-runtime/" in text
