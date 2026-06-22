# Deploying SAM for demos

The app is one FastAPI process that serves the **API + the built React SPA** on a
single origin. The only heavy piece is the **1 GB read-only `pilot.db`**, which is
never committed and never baked into the image — it's mounted, uploaded, or
downloaded-on-boot separately.

Paths supported:

- **A. Live tunnel** — run locally, expose a temporary HTTPS URL for a presented demo.
- **B. Railway (Hobby)** — the chosen durable link; container downloads `pilot.db` on boot.
- **C. Fly.io** — alternative durable PaaS (Render notes below).

A shared-password gate is active whenever `DEMO_PASSWORD` is set (any username;
set `DEMO_USER` to also fix the username). `/health` stays open for platform checks.

---

## A. Live tunnel (fastest — for a presented demo)

```bash
# 1. build the SPA once
npm run build

# 2. run the single process (serves SPA + API), gated by a password
DEMO_USER=masa DEMO_PASSWORD='choose-one' \
  .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
#   (POSIX venv: .venv/bin/python)

# 3. in another terminal, expose it (no account needed)
cloudflared tunnel --url http://localhost:8000
#   prints https://<random>.trycloudflare.com  ← share this; user/pass = above
```

Install cloudflared if needed: `winget install Cloudflare.cloudflared` (Windows) /
`brew install cloudflared` (mac). `pilot.db` and `app.db` are read from their local
paths (`./data/pilot.db`, `./app.db`) automatically — nothing to upload.

---

## B. Railway (Hobby — durable link) ← chosen

Needs a Railway account on the **Hobby** plan (~$5/mo; the free trial's 0.5 GB volume
can't hold the 1 GB DB). Railway has no file upload to volumes, so the container
**downloads `pilot.db` on first boot** from a URL you host. `railway.json` already
points the build at the `Dockerfile` and the healthcheck at `/health` (with a 600 s
timeout to cover that first download).

**Step 1 — host `pilot.db` at a download URL** (pick one):
- Cloudflare R2 / S3 / Backblaze B2 — a public or presigned object URL. No token (simplest).
- A **GitHub Release asset** on this (private) repo — set `PILOT_DB_BEARER` to a token
  with repo-read and use the API asset URL:
  `https://api.github.com/repos/makeroyd-masa/masa-sam-advocate/releases/assets/<ASSET_ID>`
  (the fetcher drops the token on the redirect to signed storage).

**Step 2 — create the service** (dashboard or CLI):
- New project → **Deploy from GitHub repo** → branch `build/sam-prototype`. Railway reads
  `railway.json` and builds the `Dockerfile`.
- Add a **Volume** mounted at **`/data`** (size ≥ 2 GB).
- Set **Variables**:
  ```
  DEMO_USER=masa
  DEMO_PASSWORD=<choose>
  PILOT_DB_PATH=/data/pilot.db
  APP_DB_PATH=/data/app.db
  PILOT_DB_URL=<your hosted URL>
  PILOT_DB_BEARER=<token>     # only if the URL needs auth
  ```
  (`PORT` is injected by Railway automatically.)
- **Deploy.** First boot streams the 1 GB DB to the volume (a few minutes); later deploys
  are fast since the volume persists. `app.db` also lives on `/data`, so cases persist.

**Step 3 — open** the Railway-provided URL and log in with `DEMO_USER` / `DEMO_PASSWORD`.

CLI equivalent (after `railway login` && `railway link`):
```bash
railway volume add --mount-path /data           # ≥ 2 GB
railway variables set DEMO_USER=masa DEMO_PASSWORD=... \
  PILOT_DB_PATH=/data/pilot.db APP_DB_PATH=/data/app.db PILOT_DB_URL=...
railway up
```

---

## C. Fly.io (alternative durable link)

Needs the Fly CLI + a Fly account (`flyctl auth login`). The image builds on Fly's
remote builder, so local Docker isn't required.

```bash
# 1. one-time: create the app + a volume for the 1 GB DB (edit `app` in fly.toml first)
fly apps create masa-sam-advocate
fly volume create samdata --size 2 --region iad

# 2. set the demo password (secret, not in fly.toml)
fly secrets set DEMO_PASSWORD='choose-one' DEMO_USER=masa

# 3. deploy the image (Dockerfile)
fly deploy

# 4. upload pilot.db to the volume (one time, ~1 GB)
fly ssh sftp shell
#   put data/pilot.db /data/pilot.db
#   bye
fly apps restart masa-sam-advocate     # reloads so /health goes green
```

Open `https://masa-sam-advocate.fly.dev`. `app.db` also lives on the volume, so
cases persist across restarts. `auto_stop_machines` scales to zero when idle (cheap).

### Render alternative (dashboard-driven)
- New **Web Service** from the repo, **Docker** runtime.
- Add a **Disk** mounted at `/data` (≥ 2 GB).
- Env: `DEMO_PASSWORD`, `DEMO_USER`, `PILOT_DB_PATH=/data/pilot.db`, `APP_DB_PATH=/data/app.db`.
- After first deploy, upload `pilot.db` to `/data` via the service **Shell**
  (or have the container pull it from object storage on boot).

---

## Local Docker (optional smoke test of the image)

```bash
docker build -t sam .
docker run --rm -p 8000:8000 \
  -e DEMO_PASSWORD=demo -e PORT=8000 \
  -v "$PWD/data:/data" -v "$PWD/app.db:/data/app.db" \
  sam
```

(Mounts the local `data/` so the container sees `pilot.db`.)

---

## Notes
- **No real PHI** in the demo — intake uses a dev-member fixture; `app.db` holds only
  what's entered in-session.
- Guardrails hold in every environment: `pilot.db` is read-only, NSA citations and
  appeal-letter generation are flag-gated **off**. Most CARC/RARC copy is unauthored
  (cards show the payer's cleaned official wording); 6 demo codes carry MASA-reviewed
  plain-English copy.
- `pilot.db` is regenerated by the separate `medical_billing_data` repo — copy the
  file from there; do not commit it.
