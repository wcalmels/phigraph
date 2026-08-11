#!/usr/bin/env bash
# VPS preflight for GRDI RC7→RC8 staging provisioning (read-only).
# Does NOT install packages, mutate firewall rules, or connect to production.
#
# Usage:
#   deploy/staging/preflight.sh [--repo-root PATH] [--env-file PATH] [--artifact-sha256 PATH=sha256 ...]
#
# Exit codes: 0 = all checks passed or NOT_EVALUATED noted; 1 = precondition failed.

set -u
set -o pipefail

REPO_ROOT=""
ENV_FILE=""
declare -A ARTIFACT_SHA256=()

usage() {
  cat <<'EOF'
Usage: preflight.sh [--repo-root PATH] [--env-file PATH] [--artifact-sha256 PATH=sha256 ...]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --artifact-sha256)
      IFS='=' read -r path digest <<< "${2:-}"
      if [[ -n "${path:-}" && -n "${digest:-}" ]]; then
        ARTIFACT_SHA256["$path"]="$digest"
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi

if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="${REPO_ROOT}/deploy/staging/.env.staging"
fi

PASS=0
FAIL=0
NOTE=0

pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*"; FAIL=$((FAIL + 1)); }
note() { echo "NOTE: $*"; NOTE=$((NOTE + 1)); }

require_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    pass "command available: $1"
  else
    fail "missing command: $1"
  fi
}

# --- OS / resources ---
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]]; then
    pass "OS Ubuntu 24.04 LTS detected (${PRETTY_NAME:-ubuntu})"
  else
    fail "expected Ubuntu 24.04 LTS, found ID=${ID:-unknown} VERSION_ID=${VERSION_ID:-unknown}"
  fi
else
  fail "/etc/os-release not readable"
fi

if command -v nproc >/dev/null 2>&1; then
  cpus="$(nproc)"
  if [[ "$cpus" -ge 2 ]]; then
    pass "CPU cores >= 2 ($cpus)"
  else
    fail "CPU cores < 2 ($cpus)"
  fi
else
  note "nproc unavailable; CPU check NOT_EVALUATED"
fi

if [[ -r /proc/meminfo ]]; then
  mem_kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  mem_gb=$((mem_kb / 1024 / 1024))
  if [[ "$mem_gb" -ge 4 ]]; then
    pass "RAM >= 4 GiB (~${mem_gb} GiB reported)"
  else
    fail "RAM < 4 GiB (~${mem_gb} GiB reported)"
  fi
else
  note "meminfo unavailable; RAM check NOT_EVALUATED"
fi

if command -v df >/dev/null 2>&1; then
  root_avail="$(df -BG / | awk 'NR==2 {gsub(/G/,"",$4); print $4}')"
  if [[ "${root_avail:-0}" -ge 40 ]]; then
    pass "root filesystem free >= 40 GiB (${root_avail} GiB)"
  else
    fail "root filesystem free < 40 GiB (${root_avail:-unknown} GiB)"
  fi
else
  note "df unavailable; disk check NOT_EVALUATED"
fi

# --- Toolchain ---
require_cmd docker
if docker compose version >/dev/null 2>&1; then
  pass "docker compose plugin available"
else
  fail "docker compose plugin missing"
fi

if command -v python3.12 >/dev/null 2>&1; then
  pass "python3.12 available"
else
  fail "python3.12 missing"
fi

for tool in psql pg_dump pg_restore; do
  require_cmd "$tool"
done

# --- Ports / exposure ---
if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq '(:|\.)5432$'; then
    public_bind="$(ss -ltn 2>/dev/null | awk '{print $4}' | grep -E '5432$' || true)"
    if echo "$public_bind" | grep -q '0.0.0.0:5432\|\[::\]:5432'; then
      fail "PostgreSQL appears bound on all interfaces: $public_bind"
    else
      pass "port 5432 not bound on 0.0.0.0 (local binds only or none)"
    fi
  else
    pass "port 5432 not listening (expected before compose up or with internal-only network)"
  fi
else
  note "ss unavailable; port exposure check NOT_EVALUATED"
fi

# --- UFW ---
if command -v ufw >/dev/null 2>&1; then
  ufw_status="$(ufw status 2>/dev/null || true)"
  if echo "$ufw_status" | grep -qi 'Status: active'; then
    pass "UFW active"
  else
    note "UFW not active (expected before hardening step)"
  fi
else
  note "ufw not installed; firewall check NOT_EVALUATED"
fi

# --- Directory layout (non-destructive) ---
STAGING_ROOT="${REPO_ROOT}/deploy/staging"
BACKUP_ROOT="${REPO_ROOT}/../backups/grdi-rc8-staging"
EVIDENCE_ROOT="${REPO_ROOT}/../evidence/grdi-rc8-staging"

for dir in "$STAGING_ROOT" "$BACKUP_ROOT" "$EVIDENCE_ROOT"; do
  if [[ -d "$dir" ]]; then
    if [[ -r "$dir" && -w "$dir" ]]; then
      pass "directory writable: $dir"
    else
      fail "directory not writable: $dir"
    fi
  else
    note "directory absent (create during provisioning): $dir"
  fi
done

# --- Secrets / env file ---
COMPOSE_FILE="${STAGING_ROOT}/docker-compose.grdi-cutover.yml"
if [[ -f "$COMPOSE_FILE" ]]; then
  pass "compose file present: $COMPOSE_FILE"
else
  fail "compose file missing: $COMPOSE_FILE"
fi

if [[ -f "$ENV_FILE" ]]; then
  if [[ "$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%OLp' "$ENV_FILE" 2>/dev/null)" == "600" ]]; then
    pass "env file permissions 600: $ENV_FILE"
  else
    fail "env file should be chmod 600: $ENV_FILE"
  fi
  if grep -qE 'REPLACE_WITH_|postgresql://REPLACE' "$ENV_FILE"; then
    fail "env file still contains placeholders"
  else
    pass "env file placeholders replaced"
  fi
  if grep -qE '^(POSTGRES_PASSWORD|PHIGRAPH_RECEIPT_SIGNING_KEY)=' "$ENV_FILE"; then
    pass "required secret keys present in env file (values not printed)"
  else
    fail "env file missing required secret keys"
  fi
else
  note "env file absent: $ENV_FILE (copy from .env.staging.example)"
fi

# --- Compose policy checks (static) ---
if [[ -f "$COMPOSE_FILE" ]]; then
  if grep -qE '0\.0\.0\.0:5432|\[::\]:5432|"5432:5432"' "$COMPOSE_FILE"; then
    fail "compose publishes PostgreSQL on all interfaces"
  else
    pass "compose does not publish 5432 on 0.0.0.0"
  fi
  if grep -q ':latest' "$COMPOSE_FILE"; then
    fail "compose references :latest image tag"
  else
    pass "compose avoids :latest"
  fi
fi

# --- Artifact checksums (optional) ---
for path in "${!ARTIFACT_SHA256[@]}"; do
  expected="${ARTIFACT_SHA256[$path]}"
  if [[ -f "$path" ]]; then
    if command -v sha256sum >/dev/null 2>&1; then
      actual="$(sha256sum "$path" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
      actual="$(shasum -a 256 "$path" | awk '{print $1}')"
    else
      note "sha256 tool missing; checksum for $path NOT_EVALUATED"
      continue
    fi
    if [[ "$actual" == "$expected" ]]; then
      pass "checksum ok: $path"
    else
      fail "checksum mismatch: $path"
    fi
  else
    fail "artifact missing for checksum: $path"
  fi
done

echo "--- summary: pass=$PASS fail=$FAIL note=$NOTE ---"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
