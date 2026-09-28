#!/usr/bin/env bash
# Bootstrap Ubuntu EC2 for Wrestling Guide API (idempotent-ish).
set -euo pipefail

APP_DIR=/opt/wrestling
APP_USER=wrestling

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  build-essential libpq-dev \
  nginx postgresql postgresql-contrib \
  ffmpeg \
  git curl openssl

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"

install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
install -d -m 755 /etc/ssl/wrestling

# Self-signed cert for Elastic IP (SAN includes IP)
if [[ ! -f /etc/ssl/wrestling/fullchain.pem ]]; then
  ELASTIC_IP="${ELASTIC_IP:-16.16.113.6}"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout /etc/ssl/wrestling/privkey.pem \
    -out /etc/ssl/wrestling/fullchain.pem \
    -subj "/CN=${ELASTIC_IP}" \
    -addext "subjectAltName=IP:${ELASTIC_IP}"
  chmod 640 /etc/ssl/wrestling/privkey.pem
  chmod 644 /etc/ssl/wrestling/fullchain.pem
fi

# Postgres role + DB (password from env DB_PASSWORD)
DB_NAME="${DB_NAME:-wrestling_db}"
DB_USER="${DB_USER:-wrestling}"
DB_PASSWORD="${DB_PASSWORD:?Set DB_PASSWORD}"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "setup-ec2.sh finished."
