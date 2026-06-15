#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="/opt/huntbot"
APP_DIR="$INSTALL_ROOT/app"
VENV_DIR="$INSTALL_ROOT/venv"
SHARED_DIR="$INSTALL_ROOT/shared"
SERVICE_NAME="huntbot-auto.service"
SERVICE_SOURCE="deploy/systemd/$SERVICE_NAME"
SOURCE_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root: sudo bash deploy/install-ubuntu.sh"
  exit 1
fi

if [[ ! -f "$SOURCE_DIR/pyproject.toml" || ! -f "$SOURCE_DIR/$SERVICE_SOURCE" ]]; then
  echo "Source directory is not a huntbot checkout: $SOURCE_DIR"
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 \
  python3-venv \
  rsync

if ! id huntbot >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_ROOT" --shell /usr/sbin/nologin huntbot
fi

install -d -o huntbot -g huntbot -m 0750 \
  "$INSTALL_ROOT" \
  "$APP_DIR" \
  "$SHARED_DIR" \
  "$SHARED_DIR/data" \
  "$SHARED_DIR/data/state" \
  "$SHARED_DIR/logs"

rsync -a --delete \
  --exclude ".git/" \
  --exclude ".env" \
  --exclude ".venv/" \
  --exclude "data/" \
  --exclude "logs/" \
  "$SOURCE_DIR/" "$APP_DIR/"

install -d -o huntbot -g huntbot -m 0750 "$APP_DIR/data"
rm -rf "$APP_DIR/data/state" "$APP_DIR/logs"
ln -s "$SHARED_DIR/data/state" "$APP_DIR/data/state"
ln -s "$SHARED_DIR/logs" "$APP_DIR/logs"
rm -f "$APP_DIR/.env"
ln -s "$SHARED_DIR/.env" "$APP_DIR/.env"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install "$APP_DIR"

install -o root -g root -m 0644 \
  "$APP_DIR/$SERVICE_SOURCE" \
  "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload

chown -R huntbot:huntbot "$APP_DIR" "$VENV_DIR" "$SHARED_DIR"

if [[ ! -f "$SHARED_DIR/.env" ]]; then
  install -o huntbot -g huntbot -m 0600 \
    "$APP_DIR/.env.example" \
    "$SHARED_DIR/.env.example"
  echo "shared/.env is missing: create $SHARED_DIR/.env from .env.example"
  echo "The service was installed but was not enabled or started."
  exit 2
fi

chown huntbot:huntbot "$SHARED_DIR/.env"
chmod 600 "$SHARED_DIR/.env"

echo "Installation prepared. Live trading has NOT been enabled or started."
echo "Next: run the dry-run command from docs/aws-ec2-runbook.md."
