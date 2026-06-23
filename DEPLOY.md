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

## B. Railway (Hobby — durable link) ← chosen, LIVE

Currently deployed at **https://masa-sam-advocate-production-2d4f.up.railway.app**
(login `masa` / `sam-demo-2026`). The notes below are the as-built recipe.

Needs a Railway account on the **Hobby** plan (~$5/mo; the free trial's 0.5 GB volume
can't hold the 1 GB DB). Railway has no file upload to volumes, so the container
**downloads `pilot.db` on first boot** from a URL you host. `railway.json` already
points the build at the `Dockerfile` and the healthcheck at `/health` (with a 600 s
timeout to cover that first download).

**Step 1 — host `pilot.db` at a download URL.** We use a **GitHub Release asset on this
(private) repo**, served behind a read-only token (chosen over R2/S3 to keep the DB
private with no extra infra). To (re)create it:
```bash
# gh CLI must be authenticated. On Windows, gh's default secure storage (keyring) is
# NOT readable from non-interactive/background shells — log in with --insecure-storage
# so the token lands in %APPDATA%\GitHub CLI\hosts.yml and every shell can see it:
gh auth login --hostname github.com --git-protocol https --web --insecure-storage

gh release create pilot-db data/pilot.db --repo makeroyd-masa/masa-sam-advocate \
  --title "pilot.db (reference DB)" --notes "Read-only Medicare reference DB for SAM deploys."
# get the asset id for the download URL:
gh api repos/makeroyd-masa/masa-sam-advocate/releases/tags/pilot-db --jq '.assets[] | {name,id,size}'
```
The live asset is **id `455933508`**, so the URL is
`https://api.github.com/repos/makeroyd-masa/masa-sam-advocate/releases/assets/455933508`.
The fetcher (`scripts/fetch_pilot_db.py`) sends `Authorization: Bearer <PILOT_DB_BEARER>`
+ `Accept: application/octet-stream` and **drops the token on the 302 redirect to signed
storage**. `PILOT_DB_BEARER` is a **fine-grained PAT scoped to this repo, `Contents: Read`
only** (release assets are part of Contents). If you set an expiry on that PAT, the
first-boot fetch starts 401'ing after that date — only matters on a fresh volume.
> Alternative host: a public R2/S3/B2 object URL needs no token (drop `PILOT_DB_BEARER`),
> but then the 1 GB reference DB is publicly downloadable.

**Step 2 — create the service** (dashboard):
- New project → **Deploy from GitHub repo** → pick `masa-sam-advocate`. If it's not listed,
  **Configure GitHub App** and grant Railway access to the `makeroyd-masa` org first.
- **Settings → Source:** set the deploy **branch to `build/sam-prototype`** (Railway defaults
  to `main`). Railway reads `railway.json` and builds the `Dockerfile`.
- Add a **Volume** mounted at **`/data`** (size ≥ 2 GB).
- Set **Variables** (Raw Editor → **paste, then Save** — an unsaved editor is the #1 gotcha):
  ```
  DEMO_USER=masa
  DEMO_PASSWORD=<choose>
  PILOT_DB_PATH=/data/pilot.db
  APP_DB_PATH=/data/app.db
  PILOT_DB_URL=https://api.github.com/repos/makeroyd-masa/masa-sam-advocate/releases/assets/455933508
  PILOT_DB_BEARER=<read-only PAT>     # only if the URL needs auth
  ```
  (`PORT` is injected by Railway automatically.)
  **Set these BEFORE the first deploy.** If the container boots with `PILOT_DB_URL` unset it
  logs `WARNING: pilot.db not found ... and PILOT_DB_URL unset`, skips the download, and comes
  up degraded (`/health` still returns 200 — it reports degraded in the body, so the
  healthcheck passes). Fix: set the vars, then **Redeploy**; the next boot fetches the DB.
- **Deploy.** First boot streams the 1 GB DB to the volume (a few minutes); later deploys
  are fast since the volume persists and the fetch self-skips. `app.db` also lives on `/data`,
  so cases persist. **Settings → Networking → Generate Domain** for the public URL.

**Step 3 — verify & open.** Confirm `GET /health` shows `"status":"ok"` with
`pilot_db.connected: true` and a non-zero `carc_codes` count (the live deploy reads 308),
and that `GET /` returns **401** unauthenticated (the password gate is active). Then open the
URL and log in with `DEMO_USER` / `DEMO_PASSWORD`.

> **Don't delete the `pilot-db` release** — a fresh volume can't rebuild without it.
> To ship app updates, push to `build/sam-prototype`; Railway auto-redeploys and the DB stays
> on the volume untouched.

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
