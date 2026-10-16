# Quickstart — Validate the Platform Locally

This brings every service up and lets you click through the end-to-end borrower
journey: signup → KYC → bank link → apply → pipeline → offer → accept → loan
detail → repay.

## Option A — One-shot via Docker Compose (recommended)

Everything (Postgres, Redis, backend, ML service, frontend, Celery worker, Celery
beat) is wired in `docker-compose.yml`. First build takes a few minutes.

```bash
cd ~/sharp-sharp
cp .env.example backend/.env       # only needed once
docker compose up -d --build
```

Once everything is healthy, open these in a browser:

| What                | URL                              |
| ------------------- | -------------------------------- |
| **Borrower app**    | http://localhost:3000            |
| Backend Swagger     | http://localhost:8000/docs       |
| Backend ReDoc       | http://localhost:8000/redoc      |
| Backend health      | http://localhost:8000/health     |
| ML scoring service  | http://localhost:8001/docs       |
| ML service health   | http://localhost:8001/health     |
| Postgres            | localhost:5432 (sharpsharp/sharpsharp_dev)   |

### Shut down
```bash
docker compose down               # stops + removes containers, keeps volume
docker compose down -v            # also drops Postgres volume (full reset)
```

### Tail logs
```bash
docker compose logs -f backend
docker compose logs -f ml-service
docker compose logs -f frontend
```

## Option B — Hybrid (faster iteration)

Run only Postgres + Redis in Docker; run app services on the host so reloads are
instant.

```bash
# Terminal 0 — infra
docker compose up -d postgres redis

# Terminal 1 — ML service
cd ~/sharp-sharp/ml-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/train_baseline.py             # one-time: trains 5 PD models
uvicorn app.main:app --reload --port 8001

# Terminal 2 — backend
cd ~/sharp-sharp/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 3 — frontend
cd ~/sharp-sharp/frontend
npm install                                  # one-time
npm run dev                                  # http://localhost:3000
```

Tables are created automatically on first run (`AUTO_CREATE_TABLES=true`). When
Alembic migrations land, set `AUTO_CREATE_TABLES=false` and use them instead.

## End-to-end demo path

1. Open http://localhost:3000.
2. Click **Get Started** → sign up with phone + password.
3. Land on dashboard. Click **Apply for Loan** — you'll be redirected to
   `/onboarding/bank` because no bank is linked.
4. **Bank link** — Mono keys not configured? You'll see the dev stub. Click
   "Link with Mono" to attach a stub account. (To use the real Mono Connect
   widget: set `MONO_PUBLIC_KEY` + `MONO_SECRET_KEY` in `backend/.env` and
   `docker compose restart backend`.)
5. **Apply** — enter amount + tenure + disbursement bank details.
6. **Status tracker** — `/applications/{id}` polls every 2s and walks through
   the 14-step pipeline. With trained ML models in place, step 9 is a real
   LightGBM inference.
7. **Offer** — auto-redirected when generated. Tick the T&Cs and accept.
8. **Loan detail** — schedule, progress, payment history. Click **Pay now** to
   try the (stubbed) repayment flow.

## Things that are real vs stub

- **Real:** loan pipeline (14 steps), state machine, application state,
  persona detection, pricing, schedule generation, offer expiry, ML inference
  (5 LightGBM persona models, AUC 0.76–0.88 on synthetic).
- **Real with key:** Mono account linking (server-side `/accounts/auth` +
  details + statement). Stub fallback if `MONO_SECRET_KEY` unset.
- **Stub:** MetaMap KYC liveness, Indicina, all 3 bureau clients,
  Flutterwave disbursement + repayment, Africa's Talking SMS.

See `docs/ARCHITECTURE.md` for the full reality status per component.

## Re-train the ML models

```bash
cd ~/sharp-sharp/ml-service
python scripts/train_baseline.py --n 60000   # bigger dataset
docker compose restart ml-service            # picks up new artefacts
```

## Common issues

- **`docker compose` build hangs on `pip install`** — slow network. Retry.
- **Frontend can't reach backend** — confirm `NEXT_PUBLIC_API_URL` in
  docker-compose env (default `http://localhost:8000`).
- **`init_db failed`** in backend logs — Postgres healthcheck didn't fire; run
  `docker compose restart backend` after Postgres is ready.
- **Bank linking shows "Mono widget not ready"** — config endpoint hit but
  `MONO_PUBLIC_KEY` is empty, so the stub UI shows. Set the keys and reload.
