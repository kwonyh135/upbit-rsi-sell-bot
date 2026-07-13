from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "deploy" / "systemd" / "huntbot-auto.service"
BTC_PAPER_SERVICE_PATH = ROOT / "deploy" / "systemd" / "huntbot-btc-paper.service"
BTC_PAPER_TIMER_PATH = ROOT / "deploy" / "systemd" / "huntbot-btc-paper.timer"
INSTALL_PATH = ROOT / "deploy" / "install-ubuntu.sh"
RUNBOOK_PATH = ROOT / "docs" / "aws-ec2-runbook.md"
BTC_PAPER_DOC_PATH = ROOT / "docs" / "bitget-btc-paper-trading.md"
GIT_ATTRIBUTES_PATH = ROOT / ".gitattributes"


def test_linux_deployment_files_keep_lf_line_endings():
    text = GIT_ATTRIBUTES_PATH.read_text(encoding="utf-8")

    assert "*.sh text eol=lf" in text
    assert "*.service text eol=lf" in text
    assert "*.timer text eol=lf" in text


def test_systemd_service_runs_live_bot_as_unprivileged_user():
    text = SERVICE_PATH.read_text(encoding="utf-8")

    assert "After=network-online.target" in text
    assert "Wants=network-online.target" in text
    assert "User=huntbot" in text
    assert "Group=huntbot" in text
    assert "WorkingDirectory=/opt/huntbot/app" in text
    assert "EnvironmentFile=/opt/huntbot/shared/.env" in text
    assert (
        "ExecStart=/opt/huntbot/venv/bin/python -m huntbot "
        "run-auto-5m --live"
    ) in text
    assert "Restart=on-failure" in text
    assert "RestartSec=30" in text
    assert "UMask=0077" in text
    assert "NoNewPrivileges=true" in text
    assert "ReadWritePaths=/opt/huntbot/shared" in text


def test_ubuntu_installer_prepares_persistent_runtime_without_starting_live():
    text = INSTALL_PATH.read_text(encoding="utf-8")

    assert 'INSTALL_ROOT="/opt/huntbot"' in text
    assert 'useradd --system --home-dir "$INSTALL_ROOT"' in text
    assert '"$SHARED_DIR/data/state"' in text
    assert '"$SHARED_DIR/logs"' in text
    assert 'ln -s "$SHARED_DIR/data/state"' in text
    assert 'ln -s "$SHARED_DIR/logs"' in text
    assert 'ln -s "$SHARED_DIR/.env"' in text
    assert '"$VENV_DIR/bin/python" -m pip install "$APP_DIR"' in text
    assert "chmod 600" in text
    assert "systemctl daemon-reload" in text
    assert "huntbot-btc-paper.service" in text
    assert "huntbot-btc-paper.timer" in text
    assert "systemctl start huntbot-auto" not in text
    assert "systemctl enable --now huntbot-auto" not in text
    assert "systemctl enable --now huntbot-btc-paper.timer" not in text
    assert "rm -rf mybot" not in text
    assert "shared/.env is missing" in text


def test_btc_paper_systemd_timer_runs_hourly_without_live_credentials():
    service = BTC_PAPER_SERVICE_PATH.read_text(encoding="utf-8")
    timer = BTC_PAPER_TIMER_PATH.read_text(encoding="utf-8")

    assert "User=huntbot" in service
    assert "Group=huntbot" in service
    assert "WorkingDirectory=/opt/huntbot/app" in service
    assert "EnvironmentFile=" not in service
    assert (
        "ExecStart=/opt/huntbot/venv/bin/python -m huntbot "
        "run-bitget-btc-paper --once --lookback 40 --initial-equity 3000"
    ) in service
    assert "run-auto-5m --live" not in service
    assert "ReadWritePaths=/opt/huntbot/shared" in service
    assert "OnBootSec=5min" in timer
    assert "OnUnitActiveSec=1h" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer


def test_btc_paper_doc_covers_aws_timer_operations():
    text = BTC_PAPER_DOC_PATH.read_text(encoding="utf-8")

    for required in (
        "huntbot-btc-paper.timer",
        "sudo systemctl enable --now huntbot-btc-paper.timer",
        "sudo systemctl status huntbot-btc-paper.timer",
        "sudo systemctl list-timers huntbot-btc-paper.timer",
        "sudo journalctl -u huntbot-btc-paper.service",
        "/opt/huntbot/shared/data/state/bitget-btc-paper.json",
        "/opt/huntbot/shared/logs/bitget-btc-paper.log",
        "sudo systemctl disable --now huntbot-btc-paper.timer",
    ):
        assert required in text


def test_aws_runbook_covers_safe_cutover_and_elastic_ip():
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    for required in (
        "Elastic IP addresses",
        "Allocate Elastic IP address",
        "Associate Elastic IP address",
        "curl -4 https://checkip.amazonaws.com",
        "0.005",
        "--exclude=.env",
        "--exclude=.venv",
        "pgrep -af",
        "mybot-bitget-backup",
        "pending_order",
        "run-auto-5m --dry-run --once",
        "systemctl enable --now huntbot-auto",
        "systemctl status huntbot-auto",
        "journalctl -u huntbot-auto",
        "sync-aws-runtime.ps1",
        "systemctl disable --now huntbot-auto",
    ):
        assert required in text

    assert "출금 권한" in text
    assert "재부팅" in text
