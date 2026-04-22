# NEXUS — AWS EC2 Deployment Guide

One-VM production deployment of the full NEXUS stack (6 services) with free auto-renewing HTTPS via Caddy + `nip.io`. No custom domain required.

## What you get

- **https://<elastic-ip-with-dashes>.nip.io** — the dashboard, with a real Let's Encrypt certificate (green padlock, no browser warnings).
- All 6 services running under Docker Compose, inter-service traffic on an internal Docker network, only ports 22/80/443 open to the internet.
- Persistent SQLite across restarts via a named Docker volume.
- Auto-restart on VM reboot.

## Target architecture

```
     Browser  ──── HTTPS ───▶  https://<ip-with-dashes>.nip.io
                                      │
                             ┌────────▼────────┐
                             │   EC2 t3.small  │  (2 vCPU / 2 GB RAM / 20 GB gp3)
                             │                 │
                             │   Caddy :80/:443│  TLS + reverse proxy
                             │       │         │
                             │       ▼         │
                             │   Docker network│
                             │                 │
                             │  • backend :8000     → /api, /ws, /x402
                             │  • frontend :3000    → everything else
                             │  • twitter-service   (internal)
                             │  • defi-agent        (internal)
                             │  • dexscreener-agent (internal)
                             │  • security-agent    (internal)
                             └─────────────────┘
```

---

## 1. Create AWS resources

### EC2 instance
1. AWS Console → EC2 → **Launch instance**
2. Name: `nexus-prod`
3. AMI: **Amazon Linux 2023** (x86_64)
4. Instance type: **t3.small** (covered by the new-account 6-month free tier)
5. Key pair: **Create new key pair** → name `nexus-key` → `.pem` format → download
6. Network:
   - VPC: default
   - Auto-assign public IP: enable
   - Firewall (security group) → **Create new**:
     - `SSH (22)` from **My IP**
     - `HTTP (80)` from **Anywhere (0.0.0.0/0)**
     - `HTTPS (443)` from **Anywhere (0.0.0.0/0)**
7. Storage: **20 GiB gp3**
8. Launch.

### Elastic IP (mandatory)
1. EC2 Console → **Elastic IPs** → Allocate new → Allocate
2. Select it → **Actions** → Associate → choose `nexus-prod`
3. Note the IP. Example: `3.14.159.26`.

> The Elastic IP is what makes the `nip.io` hostname stable. If you skip this and let AWS rotate the IP on stop/start, the TLS cert and the frontend bundle will break.

### Set permissions on your key file (local machine)
```bash
chmod 400 nexus-key.pem
```

---

## 2. Prepare the VM (one time)

SSH in:
```bash
ssh -i nexus-key.pem ec2-user@3.14.159.26
```

Install Docker + git + Docker Compose plugin:
```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
exit
# re-SSH so docker group membership takes effect
ssh -i nexus-key.pem ec2-user@3.14.159.26

mkdir -p ~/.docker/cli-plugins
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

Add log rotation so container logs don't fill the disk:
```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

---

## 3. Deploy NEXUS

Clone and configure:
```bash
git clone <YOUR_REPO_URL> nexus
cd nexus
cp .env.prod.example .env.prod
```

Edit `.env.prod`:
```bash
nano .env.prod
```

Fill these values (replace `3.14.159.26` with YOUR Elastic IP, dots → dashes):
```
PUBLIC_HOST=3-14-159-26.nip.io
PUBLIC_URL=https://3-14-159-26.nip.io
PUBLIC_WS_URL=wss://3-14-159-26.nip.io
FRONTEND_URL=https://3-14-159-26.nip.io

GROQ_API_KEY=<your-real-groq-key>
DEPLOYER_PRIVATE_KEY=<your-testnet-private-key>
# ... all other secrets
```

The contract addresses in the example file are the already-deployed ones on Kite testnet — leave them as-is.

Build + launch (first build takes 8–12 minutes on t3.small):
```bash
docker compose --env-file .env.prod up -d --build
```

Watch first TLS issuance (wait ~30–60 seconds):
```bash
docker compose logs -f caddy
```
Look for `certificate obtained successfully` and `serving initial configuration`. Ctrl-C when you see it.

Visit `https://3-14-159-26.nip.io` in your browser. You should see the NEXUS dashboard with a valid HTTPS padlock.

---

## 4. Verification checklist

From your laptop:

```bash
# Backend reachable via HTTPS
curl -I https://3-14-159-26.nip.io/api/stats

# Capability registry populated
curl https://3-14-159-26.nip.io/api/capabilities | python -c "import sys,json;print('caps:', json.load(sys.stdin)['total_capabilities'])"

# Suggestion pills
curl https://3-14-159-26.nip.io/api/example_queries

# All 11 agents in catalog
curl https://3-14-159-26.nip.io/api/agents | python -c "import sys,json;print('agents:', json.load(sys.stdin)['total_agents'])"
```

On the VM:

```bash
docker compose ps      # all 7 services should be 'running' / 'healthy'
docker stats --no-stream   # memory per container; none should be near the limit
docker compose logs backend --tail 40    # look for "Application startup complete"
```

Submit a real query from the browser. A successful query should:
1. Show the Activity feed filling in (WebSocket events).
2. Return a final report with a `View on Kite Explorer` link.
3. Reputation score change on the next `/api/reputation` poll.

---

## 5. Day-2 operations

### Check a service's logs
```bash
docker compose logs -f backend
docker compose logs -f defi-agent
docker compose logs -f caddy
```

### Redeploy after a code change
```bash
cd ~/nexus
git pull
docker compose --env-file .env.prod up -d --build
```
Only services whose inputs changed are rebuilt. First line of defense: `docker compose ps` to confirm everything healthy.

### Back up the SQLite database (daily cron)
```bash
crontab -e
# Add this line (replace HOMEDIR if ec2-user differs):
0 3 * * * docker run --rm -v nexus_nexus_data:/data -v /home/ec2-user/backups:/backup alpine sh -c "cp /data/nexus.db /backup/nexus-$(date +\%F).db && find /backup -mtime +14 -delete"
```
(For off-site backup, install `aws-cli` and upload to an S3 bucket in the cron line.)

### Full stop / restart
```bash
docker compose down           # stop + remove containers (DB preserved in volume)
docker compose --env-file .env.prod up -d    # bring back up
```

### Rotate LLM keys
1. Edit `.env.prod`, save.
2. `docker compose --env-file .env.prod up -d` — containers pick up new env on restart.

### If the Elastic IP changes (it won't, but just in case)
1. Update `PUBLIC_HOST` / `PUBLIC_URL` / `PUBLIC_WS_URL` / `FRONTEND_URL` in `.env.prod`.
2. Rebuild frontend (env is baked at build time):
   ```bash
   docker compose --env-file .env.prod build frontend
   docker compose --env-file .env.prod up -d
   ```
3. Caddy auto-requests a fresh cert for the new hostname.

---

## 6. Cost

With your new-account 6-month free tier (t3.small, 20 GB gp3, 100 GB egress all included):
- **$0/month for the first 6 months** (as long as your 3 combined services stay under 750 hrs/month).
- After the free tier: ~**$18/month** (t3.small + 20GB EBS + small egress) in us-east-1.

Set an AWS Budget alert at $10/mo just in case. AWS Console → **Billing** → **Budgets** → Create monthly cost budget.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser can't reach `https://...nip.io` | Port 443 blocked in security group | Check SG inbound rules include 443 from 0.0.0.0/0 |
| Caddy log: `could not obtain certificate` | Port 80 blocked | Check SG inbound rules include 80 from 0.0.0.0/0 |
| `api.get_stats()` returns 404 / wrong host | Elastic IP changed OR `.env.prod` has wrong PUBLIC_HOST | Update .env.prod, rebuild frontend, restart |
| Frontend loads but API calls fail (mixed content) | Frontend was built with `http://` URLs | Rebuild with `PUBLIC_URL=https://...` set |
| `docker compose up` OOM-killed during frontend build | Memory pressure on t3.small | `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile` |
| Backend log: `Kite: Not connected` | RPC unreachable or wrong chain | Test from VM: `curl -X POST https://rpc-testnet.gokite.ai -d '{"jsonrpc":"2.0","method":"eth_chainId","id":1}' -H "Content-Type: application/json"` |
| `GRPC` / `ALTS` noise in backend logs | Harmless Google SDK boilerplate | Already suppressed by `GRPC_VERBOSITY=ERROR` in .env.prod |

---

## 8. What's NOT included

- **Multi-replica backend.** The deployer wallet's nonce serialization requires exactly one backend process. Don't scale this horizontally as-is.
- **Real notifications / alerts** — AlertAgent is deliberately deregistered (see repo README).
- **Custom domain** — plan assumes `<ip>.nip.io`. If you buy a domain later, point its A record at the Elastic IP and change `PUBLIC_HOST` in `.env.prod`.
- **Mainnet deployment** — everything points at Kite testnet. Moving to mainnet requires redeploying contracts, updating `.env.prod` addresses, and funding with real KITE.

---

## 9. Files this deployment relies on

- `docker-compose.yml` — orchestrates the 7 containers (Caddy + 6 services).
- `Caddyfile` — TLS + routing rules.
- `.env.prod` — secrets + public URLs (on the VM, never committed).
- `.env.prod.example` — template in the repo.
- `Dockerfile` — backend image.
- `frontend/Dockerfile` — frontend image.
- `example-agents/*/Dockerfile` — 3 external agent images.
- `twitter-service/Dockerfile` — Twitter microservice image.
