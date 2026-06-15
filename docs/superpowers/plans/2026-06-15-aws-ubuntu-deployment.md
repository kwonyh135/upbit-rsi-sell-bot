# AWS Ubuntu Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the existing Upbit bot for reliable operation on the existing AWS EC2 Ubuntu instance while keeping the dashboard local and on demand.

**Architecture:** Add operating-system-specific file locking behind the existing `SingleInstanceLock` interface, package a hardened `systemd` unit and an idempotent Ubuntu preparation script, and add a Windows SCP sync script for downloading only runtime state and logs. The local dashboard selects downloaded AWS runtime files when present while continuing to query Upbit directly for balances and market data.

**Tech Stack:** Python 3.11+, pytest, Bash, systemd, PowerShell, OpenSSH/SCP, Streamlit.

---

### Task 1: Cross-Platform Single-Instance Lock

**Files:**
- Modify: `huntbot/auto_service.py`
- Modify: `tests/test_auto_service.py`

- [ ] Add failing tests that inject a fake lock backend, verify lock release, and verify that POSIX locking requests `LOCK_EX | LOCK_NB`.
- [ ] Run `python -m pytest tests/test_auto_service.py -v` and confirm the new tests fail because the backend interface does not exist.
- [ ] Add Windows and POSIX lock backends selected at runtime without importing `fcntl` on Windows.
- [ ] Run `python -m pytest tests/test_auto_service.py -v` and confirm all tests pass.

### Task 2: Ubuntu systemd Service

**Files:**
- Create: `deploy/systemd/huntbot-auto.service`
- Create: `tests/test_linux_deployment.py`

- [ ] Add failing service-unit tests for the dedicated user, working directory, environment file, live command, network dependency, restart policy, and hardening settings.
- [ ] Run `python -m pytest tests/test_linux_deployment.py -v` and confirm failure because the unit does not exist.
- [ ] Add `huntbot-auto.service` with `Restart=on-failure`, `RestartSec=30`, `UMask=0077`, and restricted privileges.
- [ ] Run the deployment tests and confirm they pass.

### Task 3: Safe Ubuntu Preparation Script

**Files:**
- Create: `deploy/install-ubuntu.sh`
- Modify: `tests/test_linux_deployment.py`

- [ ] Add failing tests that require persistent directories, state/log symlinks, `.env` permission enforcement, virtual-environment installation, service installation, and no automatic live start.
- [ ] Run the deployment tests and confirm the new assertions fail.
- [ ] Add an idempotent root-run script that prepares `/opt/huntbot`, installs but does not start the service, and refuses to overwrite a missing secret file silently.
- [ ] Run the deployment tests and confirm they pass.

### Task 4: Local AWS Runtime Download

**Files:**
- Create: `scripts/sync-aws-runtime.ps1`
- Modify: `.gitignore`
- Create: `tests/test_aws_runtime_sync.py`

- [ ] Add failing tests that require SSH key/host parameters, temporary download staging, allowlisted state/log paths, preservation on failure, and exclusion of `.env`.
- [ ] Run `python -m pytest tests/test_aws_runtime_sync.py -v` and confirm failure because the script does not exist.
- [ ] Add the PowerShell SCP script and ignore `data/remote-runtime/`.
- [ ] Run the sync-script tests and confirm they pass.

### Task 5: Local Dashboard Remote Runtime Selection

**Files:**
- Modify: `huntbot/dashboard_app.py`
- Modify: `huntbot/dashboard_collector.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `tests/test_dashboard_collector.py`

- [ ] Add failing tests that select downloaded AWS state/log files when present and do not require a local live process for remote health display.
- [ ] Run the dashboard tests and confirm the new behavior fails.
- [ ] Add a small runtime-source resolver and pass `process_running=None` only for local runtime; downloaded AWS runtime health is based on heartbeat freshness.
- [ ] Run the dashboard tests and confirm they pass.

### Task 6: Operator Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/aws-ec2-runbook.md`
- Modify: `tests/test_linux_deployment.py`

- [ ] Add failing documentation assertions covering old Bitget shutdown, state validation, dry-run, explicit live start, Elastic IP registration, reboot verification, log inspection, local sync, and rollback.
- [ ] Run the deployment tests and confirm the documentation assertions fail.
- [ ] Add exact Ubuntu and Windows commands without embedding secrets or starting live trading from the installer.
- [ ] Run the deployment tests and confirm they pass.

### Task 7: Final Verification

**Files:**
- Verify all modified files.

- [ ] Run `python -m pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Confirm `.env`, `data/state`, `data/dashboard`, `data/remote-runtime`, and logs are not tracked.
- [ ] Confirm the currently running live bot remains on its existing process and state throughout implementation.
- [ ] Review the diff against `docs/superpowers/specs/2026-06-14-aws-ubuntu-deployment-design.md`.
