# EC2 deploy (Wrestling Guide / Vision Quest)

## Target

- Host: `16.16.113.6` (Elastic IP)
- User: `ubuntu`
- App: `/opt/wrestling`
- HTTPS: self-signed cert (browser warning expected)
- Media: S3 `vision-quest-ai-videos` / `eu-north-1` via IAM role `VisionQuestEC2S3Role`
- Git remote: `git@github.com:devgeektech/wrestling.git` (`main`)

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

This pushes `origin/main`, SSHs to EC2, runs `deploy/server-update.sh` (pull, pip, migrate, collectstatic, restart Gunicorn).  
Production `.env` on the server is **never** overwritten.

Optional env overrides:

- `WRESTLING_PEM` — path to `.pem`
- `WRESTLING_HOST` — Elastic IP / hostname
- `WRESTLING_SSH_USER` — default `ubuntu`

### On the server only

```bash
sudo /opt/wrestling/deploy/server-update.sh
```

## First-time git wire-up (already done once)

1. Push product code to GitHub `main`.
2. Create a **read-only deploy key** on the EC2 box (`/home/wrestling/.ssh/github_deploy`).
3. Add that public key in GitHub → repo **Settings → Deploy keys**.
4. Point `/opt/wrestling` at `origin/main` while keeping `.env` and `venv`.

## What must not be in git

`.env`, `venv/`, `media/`, `staticfiles/`, `*.pem`, Tailscale `*.ts.net.*` certs, Firebase JSON, `body.txt`, local junk.

## Manual SCP exclude list (legacy)

Do not copy: `.env`, `venv/`, `media/`, `body.txt`, `*.pem`, `*.ts.net.*`, Tailscale scripts, `__pycache__`.
