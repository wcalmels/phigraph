# DonWeb closed-pilot runbook

Target: 1–3 external customers calling the PhiGraph API with per-tenant JWTs,
behind automatic HTTPS on `phigraph.phi47.cl`, with **shadow-only** execution
forced on.

Recommended DonWeb Cloud Server size for this pilot:

- 4 vCPU
- 8 GB RAM
- 40–60 GB SSD NVMe
- Ubuntu Server 24.04 LTS **minimal** (no hosting panel)
- Open ports: 22, 80, 443 only

Approximate budget: CLP $15–20k / month.

## 1. Provision the server

1. In DonWeb, create a Cloud Server with the size above.
2. Choose Ubuntu 24.04 without Ferozo/cPanel.
3. Save the root password / SSH key from the control panel.
4. Note the public IPv4 address.

## 2. DNS

In the DonWeb DNS zone for `phi47.cl` (or wherever `phi47.cl` is hosted):

| Type | Name | Value |
|------|------|-------|
| A | `phigraph` | `<VPS public IPv4>` |

Wait until `dig +short phigraph.phi47.cl` returns the VPS IP before bringing
Caddy up (Let's Encrypt needs a correct A record).

## 3. First login and bootstrap

```bash
ssh root@<VPS_IP>
curl -fsSL https://raw.githubusercontent.com/wcalmels/phigraph/main/scripts/deploy/bootstrap_donweb.sh \
  | bash
```

Or, after cloning manually:

```bash
cd /opt/phigraph
sudo bash scripts/deploy/bootstrap_donweb.sh
```

The script installs Docker, enables UFW (22/80/443), creates user `phigraph`,
clones the repo into `/opt/phigraph`, and copies `deploy/.env.prod.example`
to `.env` if missing.

## 4. Configure secrets

```bash
sudo -u phigraph nano /opt/phigraph/.env
```

Set at least:

- `PHIGRAPH_API_KEY` — admin key for `/config` and legacy shadow routes
- `PHIGRAPH_JWT_SECRET` — long random secret shared only with the minting script
- `PHIGRAPH_DOMAIN=phigraph.phi47.cl`
- `ACME_EMAIL=wcalmels@phi47.cl`

Generate secrets on the VPS:

```bash
openssl rand -hex 32   # API key
openssl rand -hex 48   # JWT secret
```

Leave these unchanged for the pilot:

```text
PHIGRAPH_SHADOW_ONLY=true
PHIGRAPH_REAL_CONNECTORS_ENABLED=false
```

## 5. Start the stack

```bash
cd /opt/phigraph
sudo -u phigraph docker compose -f docker-compose.prod.yml up -d --build
sudo -u phigraph docker compose -f docker-compose.prod.yml ps
curl -fsS https://phigraph.phi47.cl/health
```

Expected: JSON with `"shadow_only": true` and HTTPS certificate issued by
Let's Encrypt.

## 6. Mint one token per pilot customer

On a trusted machine (or the VPS) with the same JWT secret:

```bash
export PHIGRAPH_JWT_SECRET='...'   # same as .env

python scripts/mint_pilot_token.py \
  --subject acme-ops \
  --tenant tenant-acme \
  --project pilot \
  --role operator \
  --days 90
```

Give each customer **only** their Bearer token (never the JWT secret).

Customer smoke test:

```bash
curl -fsS https://phigraph.phi47.cl/v3/status \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: tenant-acme" \
  -H "X-Project-Id: pilot"
```

## 7. Update / redeploy

```bash
cd /opt/phigraph
sudo -u phigraph git pull --ff-only
sudo -u phigraph docker compose -f docker-compose.prod.yml up -d --build
```

## 8. Backups

Daily volume snapshot is enough for the pilot:

```bash
# example: copy SQLite ledger out of the named volume
sudo -u phigraph docker compose -f docker-compose.prod.yml exec api \
  python -c "import shutil; shutil.copy('/app/data/phigraph.db','/tmp/phigraph.db')"
```

Prefer DonWeb panel snapshots of the whole Cloud Server once a week until
Postgres is introduced.

## 9. What this pilot deliberately does **not** do

- Real external connectors / non-shadow execution
- Multi-instance Postgres HA
- OIDC / SSO (can be added later via existing Core validators)
- Public anonymous write access

## 10. Commercial handoff after a successful pilot

Once 1–3 customers are stable:

1. Capture a short case study (with permission).
2. Move ledger backend to Postgres (see `docs/deployment/PRODUCTION_CHECKLIST.md`).
3. Introduce paid Starter / Business tiers (hosted) while keeping MIT Core
   self-hostable.
4. Only then consider raising execution authority beyond shadow mode, under a
   separate security review.
