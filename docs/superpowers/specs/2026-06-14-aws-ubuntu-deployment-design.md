# AWS Ubuntu Deployment Design

## Goal

Run the existing Upbit `KRW-HUNT` unattended trading bot on the existing AWS
EC2 Ubuntu instance that currently hosts the Bitget bot. Keep the trading
process running across SSH disconnects, crashes, and EC2 reboots without
running the Streamlit dashboard on AWS.

The dashboard remains a local, on-demand tool. When needed, the operator
downloads the latest runtime state and logs from AWS and starts Streamlit on
the local Windows PC.

## Scope

This change covers:

- Cross-platform single-instance locking for Windows and Linux.
- A `systemd` service for the live Upbit trader.
- An Ubuntu deployment script and service installation instructions.
- Safe replacement of the old Bitget process on the existing EC2 instance.
- Persistent state and log handling.
- A Windows PowerShell script that downloads AWS runtime files for the local
  dashboard.
- Dashboard support for a downloaded remote state and log location.
- Dry-run, reboot, recovery, and rollback verification.

This change does not:

- Change the RSI strategy, emergency thresholds, order sizing, or market.
- Run Streamlit or expose a dashboard port on AWS.
- Delete the existing Bitget bot directory.
- Copy API secrets into source control or dashboard data.
- Automatically execute live orders during deployment.

## Target Architecture

### AWS EC2

The existing Ubuntu EC2 instance runs one live trading service:

```text
/opt/huntbot/
├── app/                         checked-out application
├── venv/                        Python virtual environment
├── shared/.env                  Upbit and Telegram secrets
├── shared/data/state/           persistent trading state
└── shared/logs/                 persistent rotating logs
```

The application paths `data/state` and `logs` are symbolic links to the
corresponding directories under `/opt/huntbot/shared`. Deploying a new
application version therefore does not overwrite live state or logs.

`huntbot-auto.service` runs:

```text
/opt/huntbot/venv/bin/python -m huntbot run-auto-5m --live
```

The service:

- Starts after networking is available.
- Uses `/opt/huntbot/app` as its working directory.
- Loads secrets from `/opt/huntbot/shared/.env`.
- Restarts after an unexpected failure.
- Does not restart after a deliberate `systemctl stop`.
- Runs as a dedicated unprivileged `huntbot` user.
- Writes application logs to the existing rotating log file and service
  lifecycle output to the system journal.

Only one live process may hold the application lock.

### Local Windows PC

The repository remains the dashboard application. An on-demand PowerShell
script downloads:

- `auto-trading.json`
- `huntbot-auto.log` and available rotated log files

The files are stored under:

```text
data/remote-runtime/state/auto-trading.json
data/remote-runtime/logs/huntbot-auto.log
```

The local dashboard uses these downloaded files to display remote process
state and recent logs. It continues to query Upbit directly for balances,
orders, candles, and current prices, using the local `.env`. Its SQLite
database remains local at `data/dashboard/huntbot-dashboard.sqlite3`.

No `.env`, API key, Telegram token, or private key is downloaded by the sync
script.

## Cross-Platform Locking

The current lock uses Windows-only `msvcrt`. The lock implementation will
select the native mechanism at runtime:

- Windows: `msvcrt.locking`
- Linux: `fcntl.flock`

Both implementations use the same context-manager contract and hold an
exclusive, non-blocking lock for the process lifetime. A second process fails
before entering the auto-trading service.

The lock file remains under `data/state`, which resolves to persistent
storage on AWS. The existence of the file alone does not indicate a running
process; the operating-system lock does.

## Deployment Flow

### Preparation

1. Confirm Bitget has no position and no open order.
2. Record the existing Bitget process ID and deployment directory.
3. Stop the Bitget process and verify it no longer exists.
4. Rename the existing `mybot` directory to a timestamped backup instead of
   deleting it.
5. Create the `huntbot` system user and `/opt/huntbot` directories.
6. Install Python 3.11 or newer, `venv`, Git, and required OS packages.

### Application Installation

1. Copy or clone the approved Upbit bot revision into `/opt/huntbot/app`.
2. Create `/opt/huntbot/venv` and install the package.
3. Create `/opt/huntbot/shared/.env` manually with Upbit and Telegram values.
4. Set secret permissions to owner-read/write only.
5. Create persistent state and log directories.
6. Link the application state and log paths to shared storage.
7. Install and enable the `systemd` service.

### Validation Before Live Mode

1. Run the full automated test suite.
2. Run `python -m huntbot run-auto-5m --dry-run --once`.
3. Confirm Upbit balance, orderbook price, RSI, phase, and Telegram startup
   notification.
4. Confirm no order was submitted.
5. Confirm the EC2 static public IPv4 is registered on the Upbit API key.
6. Verify only the required Upbit permissions are enabled and withdrawal
   permission is disabled.

### Live Cutover

1. Copy the latest verified local live state to AWS only when it represents
   the desired starting phase.
2. Start `huntbot-auto.service`.
3. Verify one process, a healthy journal entry, the rotating application log,
   and the Telegram startup message.
4. Reboot EC2 once and verify automatic recovery before leaving the service
   unattended.

Live startup is a deliberate operator action. Deployment scripts do not start
live trading until validation has completed.

## State Migration

The current local live state is meaningful because it records the next phase,
the last completed candle, and any pending order.

Before copying it:

- `pending_order` must be null.
- The local state must match actual Upbit HUNT and KRW balances.
- The intended next phase must be reviewed.
- The source file is backed up with a timestamp.

If these checks are not satisfied, deployment stops rather than inventing a
new phase. The bot's order identifiers allow completed orders to be reconciled
from Upbit, but the starting phase must not be guessed during deployment.

## Error Handling And Recovery

- `systemd` restarts the process after unexpected exit.
- The application retries trading cycles after transient API errors.
- Pending order metadata is written before order submission and reconciled
  after restart.
- Telegram reports startup, shutdown, order, emergency, error, and recovery
  events.
- Application logs rotate by size using the existing Python logging setup.
- The journal is retained according to the EC2 system policy.
- Failure to download dashboard data does not affect the AWS trader.
- Failure of the local dashboard does not affect the AWS trader.

## Security

- The EC2 instance uses a static public IPv4 registered with Upbit.
- Upbit API withdrawal permission remains disabled.
- `/opt/huntbot/shared/.env` is owned by `huntbot` with mode `600`.
- The service runs without root privileges.
- SSH ingress is restricted to the operator's public IP when practical.
- No Streamlit port is opened.
- The local sync script uses SSH key authentication and downloads only an
  allowlisted set of state and log files.
- Runtime state, logs, SQLite files, `.env`, and private keys remain ignored
  by Git.

## Local Dashboard Workflow

The operator runs a PowerShell command with the EC2 host and SSH key path.
The script:

1. Creates the local remote-runtime directories.
2. Downloads the allowlisted state and log files.
3. Preserves the previous local download if transfer fails.
4. Reports the timestamp of the downloaded state.
5. Does not start Streamlit automatically.

The operator then starts the existing local dashboard. The dashboard displays
the downloaded AWS runtime state while collecting current account and market
data directly from Upbit.

This split avoids an AWS web service, public dashboard authentication, and
additional EC2 memory use.

## Rollback

If the Upbit service cannot be validated:

1. Stop and disable `huntbot-auto.service`.
2. Verify the Upbit process is absent.
3. Leave Upbit positions and open orders under explicit operator control.
4. Restore the timestamped Bitget directory only if the operator chooses to
   resume that bot.
5. Recheck Bitget positions and open orders before restarting it.

Rollback never starts both bots together.

## Testing

Automated tests will cover:

- Linux locking uses an exclusive non-blocking lock.
- A second lock holder is rejected.
- Windows locking behavior remains supported.
- The service unit uses the expected unprivileged user, working directory,
  environment file, live command, and restart policy.
- The deployment script creates persistent directories and does not start
  live trading automatically.
- The local sync script downloads only state and logs.
- Dashboard runtime inspection can use downloaded remote paths.
- Existing trading and dashboard tests remain green.

Manual AWS verification will cover:

- One-cycle dry-run.
- Static IP and API permissions.
- Service startup and single-instance behavior.
- EC2 reboot recovery.
- Telegram notifications.
- Local runtime download and dashboard display.

## Success Criteria

- The old Bitget process is stopped and preserved for rollback.
- Exactly one Upbit live process runs on AWS.
- The bot survives SSH disconnect and EC2 reboot.
- Unexpected process failure triggers automatic restart.
- Trading state and logs survive application redeployment.
- No dashboard port is exposed on AWS.
- Local dashboard use requires only an explicit download and local launch.
- No secret is committed or downloaded from AWS.
- Dry-run and automated tests pass before live startup.
