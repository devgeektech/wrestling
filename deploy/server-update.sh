#!/usr/bin/env bash
# Run on EC2 as root or via: sudo /opt/wrestling/deploy/server-update.sh
# Pulls origin/main, installs deps, migrates, collectstatic, restarts Gunicorn.
# Never overwrites /opt/wrestling/.env
set -euo pipefail

APP_DIR=/opt/wrestling
APP_USER=wrestling
BRANCH="${DEPLOY_BRANCH:-main}"

cd "$APP_DIR"

if [[ ! -d .git ]]; then
  echo "ERROR: $APP_DIR is not a git repository. Complete first-time git wire-up first."
  exit 1
fi

echo "==> Fetching $BRANCH..."
sudo -u "$APP_USER" git fetch --prune origin
sudo -u "$APP_USER" git checkout "$BRANCH"
sudo -u "$APP_USER" git reset --hard "origin/$BRANCH"

echo "==> Installing Python dependencies..."
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && ./venv/bin/pip install -r requirements.txt"

echo "==> migrate + collectstatic..."
sudo -u "$APP_USER" bash -lc "cd '$APP_DIR' && set -a && source .env && set +a && export DJANGO_SETTINGS_MODULE=config.settings.production && ./venv/bin/python manage.py migrate --noinput && ./venv/bin/python manage.py collectstatic --noinput"

echo "==> Restarting wrestling.service..."
systemctl restart wrestling
systemctl is-active wrestling

echo "==> Deploy complete ($(sudo -u "$APP_USER" git rev-parse --short HEAD))"
