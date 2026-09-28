#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p /home/wrestling/.ssh
sudo chown -R wrestling:wrestling /home/wrestling /home/wrestling/.ssh
sudo chmod 700 /home/wrestling/.ssh

if ! sudo test -f /home/wrestling/.ssh/github_deploy; then
  sudo -u wrestling ssh-keygen -t ed25519 -f /home/wrestling/.ssh/github_deploy -N "" -C "wrestling-ec2-deploy"
fi

sudo tee /home/wrestling/.ssh/config >/dev/null <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile /home/wrestling/.ssh/github_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
sudo chown wrestling:wrestling /home/wrestling/.ssh/config
sudo chmod 600 /home/wrestling/.ssh/config /home/wrestling/.ssh/github_deploy
sudo chmod 644 /home/wrestling/.ssh/github_deploy.pub

# Prefer in-place convert: keep .env/venv/staticfiles, replace tree from bundle.
sudo test -f /opt/wrestling/.env
sudo test -d /opt/wrestling/venv

sudo rm -rf /tmp/wrestling-clone /tmp/wrestling-env.bak /tmp/wrestling-venv.bak /tmp/wrestling-static.bak
sudo cp /opt/wrestling/.env /tmp/wrestling-env.bak
sudo mv /opt/wrestling/venv /tmp/wrestling-venv.bak
if [ -d /opt/wrestling/staticfiles ]; then sudo mv /opt/wrestling/staticfiles /tmp/wrestling-static.bak; fi

# Bundle has no symbolic HEAD — always checkout main explicitly.
sudo -u wrestling git clone --branch main /tmp/wrestling.bundle /tmp/wrestling-clone

sudo rm -rf /opt/wrestling.old
sudo mv /opt/wrestling /opt/wrestling.old
sudo mv /tmp/wrestling-clone /opt/wrestling

cd /opt/wrestling
sudo -u wrestling git remote remove origin || true
sudo -u wrestling git remote add origin git@github.com:devgeektech/wrestling.git
sudo -u wrestling git branch --set-upstream-to=origin/main main 2>/dev/null || true
sudo mv /tmp/wrestling-env.bak /opt/wrestling/.env
sudo mv /tmp/wrestling-venv.bak /opt/wrestling/venv
if [ -d /tmp/wrestling-static.bak ]; then sudo mv /tmp/wrestling-static.bak /opt/wrestling/staticfiles; fi
sudo mkdir -p /opt/wrestling/deploy
sudo cp /tmp/server-update.sh /opt/wrestling/deploy/server-update.sh
sudo chmod +x /opt/wrestling/deploy/*.sh || true
sudo chown -R wrestling:wrestling /opt/wrestling

echo "=== DEPLOY PUBLIC KEY ==="
sudo cat /home/wrestling/.ssh/github_deploy.pub
echo "=== git status ==="
sudo -u wrestling bash -lc 'cd /opt/wrestling && git rev-parse --short HEAD && git remote -v && ls deploy/server-update.sh && test -f .env && test -d venv && echo PRESERVED'
sudo systemctl restart wrestling
sleep 2
sudo systemctl is-active wrestling
curl -sk -o /dev/null -w 'docs=%{http_code}\n' https://127.0.0.1/api/docs/ || true
echo WIRE_OK
