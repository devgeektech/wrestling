# EC2 deploy (Wrestling Guide / Vision Quest)

## Target

- Host: `16.16.113.6` (Elastic IP)
- User: `ubuntu`
- App: `/opt/wrestling` (git checkout of `origin/main`)
- HTTPS: self-signed cert (browser warning expected)
- Media: S3 `vision-quest-ai-videos` / `eu-north-1` via IAM role `VisionQuestEC2S3Role`
- Git remote on EC2: `git@github.com:devgeektech/wrestling.git` (`main`)

## Flutter / clients

Base URL: `https://16.16.113.6/api/v1/`  
Swagger: `https://16.16.113.6/api/docs/`

Allow self-signed TLS in debug HTTP clients until you add a real domain.

## Git-based updates (preferred)

### Day-to-day (from your PC)

1. Commit your changes on `main`.
2. Run:

```powershell
.\deploy\push-and-deploy.ps1
```

This pushes `origin/main`, SSHs to EC2, runs `deploy/server-update.sh` (fetch, hard-reset to `origin/main`, pip, migrate, collectstatic, restart Gunicorn).  
Production `.env` on the server is **never** overwritten.

Optional env overrides:

- `WRESTLING_PEM` — path to `.pem`
- `WRESTLING_HOST` — Elastic IP / hostname
- `WRESTLING_SSH_USER` — default `ubuntu`

### On the server only

```bash
sudo /opt/wrestling/deploy/server-update.sh
```

## First-time git wire-up

Already done on EC2: `/opt/wrestling` is a git repo on `main`, `.env` + `venv` preserved, SSH deploy key at `/home/wrestling/.ssh/github_deploy`.

### Add the read-only deploy key on GitHub (required once)

1. Open: https://github.com/devgeektech/wrestling/settings/keys  
2. **Add deploy key** → title `wrestling-ec2` → allow **read-only** (do not enable write).
3. Paste this public key:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKtcmHhNNoanAvM3Jsu7cyDjCCb1ctqjWL3/ewpOTJB/ wrestling-ec2-deploy
```

Or with GitHub CLI (after `gh auth login`):

```powershell
gh repo deploy-key add -R devgeektech/wrestling -t wrestling-ec2 -k "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKtcmHhNNoanAvM3Jsu7cyDjCCb1ctqjWL3/ewpOTJB/ wrestling-ec2-deploy"
```

4. Verify from EC2:

```bash
sudo -u wrestling ssh -T git@github.com
# expect: Hi devgeektech/wrestling! You've successfully authenticated...
sudo /opt/wrestling/deploy/server-update.sh
```

One-time helper scripts (if re-wiring a fresh box):

- `deploy/wire-ec2-git.sh` — clone from a `wrestling.bundle`, restore `.env`/`venv`, set SSH remote
- Upload bundle + scripts, then: `bash /tmp/wire-ec2-git.sh`

## What must not be in git

`.env`, `venv/`, `media/`, `staticfiles/`, `*.pem`, `*.bundle`, Tailscale `*.ts.net.*` certs, Firebase JSON, `body.txt`, local junk.

## Manual SCP exclude list (legacy)

Do not copy: `.env`, `venv/`, `media/`, `body.txt`, `*.pem`, `*.ts.net.*`, Tailscale scripts, `__pycache__`.
