#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu 24.04 DonWeb Cloud Server for the PhiGraph closed pilot.
# Run as root (or with sudo) on the VPS after first SSH login.
set -euo pipefail

APP_USER="${APP_USER:-phigraph}"
APP_DIR="${APP_DIR:-/opt/phigraph}"
REPO_URL="${REPO_URL:-https://github.com/wcalmels/phigraph.git}"
BRANCH="${BRANCH:-main}"

echo "==> Updating system packages"
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl git ufw fail2ban

echo "==> Installing Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Creating app user and directory"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$APP_USER"
fi
usermod -aG docker "$APP_USER"
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Configuring firewall (22/80/443 only)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Cloning repository (if missing)"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
fi

if [ ! -f "$APP_DIR/.env" ]; then
  sudo -u "$APP_USER" cp "$APP_DIR/deploy/.env.prod.example" "$APP_DIR/.env"
  echo
  echo "Created $APP_DIR/.env from the example template."
  echo "Edit secrets before starting the stack:"
  echo "  sudo -u $APP_USER nano $APP_DIR/.env"
fi

echo
echo "Bootstrap complete."
echo "Next:"
echo "  1. Point DNS A record for phigraph.phi47.cl to this VPS public IP"
echo "  2. Edit $APP_DIR/.env (API key + JWT secret + domain)"
echo "  3. cd $APP_DIR && docker compose -f docker-compose.prod.yml up -d --build"
echo "  4. Mint client tokens with scripts/mint_pilot_token.py"
