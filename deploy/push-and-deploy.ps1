# Push main to GitHub, then pull+restart on EC2.
# Usage (from repo root):
#   .\deploy\push-and-deploy.ps1
# Prerequisites: commits already on main, SSH key, EC2 wired to git.

$ErrorActionPreference = "Stop"

$Pem = if ($env:WRESTLING_PEM) { $env:WRESTLING_PEM } else { "C:\Users\GT49220\OneDrive\Desktop\Sushil-Projects\VisionQuestAI.pem" }
$HostName = if ($env:WRESTLING_HOST) { $env:WRESTLING_HOST } else { "16.16.113.6" }
$SshUser = if ($env:WRESTLING_SSH_USER) { $env:WRESTLING_SSH_USER } else { "ubuntu" }

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$status = git status --porcelain
if ($status) {
    Write-Host "Working tree has uncommitted changes:"
    git status -sb
    Write-Host ""
    Write-Host "Commit (or stash) locally first, then re-run this script."
    exit 1
}

Write-Host "==> Pushing origin main..."
git push origin main

Write-Host "==> Updating EC2 ($SshUser@$HostName)..."
ssh -i $Pem -o StrictHostKeyChecking=accept-new "${SshUser}@${HostName}" "sudo bash /opt/wrestling/deploy/server-update.sh"

Write-Host "==> Done. Smoke: https://$HostName/api/docs/"
