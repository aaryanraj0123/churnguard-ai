# ChurnGuard AI — v4.0

Customer Churn Prediction · FastAPI · React · PostgreSQL · Redis · Celery · Docker

---

## Local setup (< 5 min)

```bash
# 1. Copy env file
cp .env.example .env

# 2. Generate and set SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
# Open .env and paste the output as SECRET_KEY

# 3. Start everything
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5556 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (admin / churnguard) |

---

## Activate the ML model (first run only)

```bash
# Register
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"AdminPass1","role":"admin"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin@test.com&password=AdminPass1" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Register model
MODEL_ID=$(curl -s -X POST http://localhost:8000/api/v1/models \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version_tag":"v1","artifact_path":"app/ml/artifacts/v1.pkl",
       "auc_roc":0.8003,"f1_score":0.2969,"precision":0.6129,"recall":0.1959}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Promote
curl -s -X POST http://localhost:8000/api/v1/models/$MODEL_ID/promote \
  -H "Authorization: Bearer $TOKEN"
```

Or use the one-command pipeline:
```bash
ADMIN_TOKEN=$TOKEN ./pipeline.sh
```

---

## Run tests

```bash
docker compose exec app pytest tests/unit/ -v
docker compose exec app pytest tests/integration/ -v
docker compose exec app pytest tests/ --cov=app --cov-report=term-missing
```

---

## Push to GitHub

```bash
git init
git add .
git commit -m "feat: ChurnGuard AI v4.0"
git remote add origin https://github.com/YOUR_USERNAME/churnguard-ai
git push -u origin main
```

GitHub Actions runs automatically: **lint → frontend build → tests → docker build**

---

## Deploy (free tier)

### Backend → Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select repo → **Root Directory**: `backend` → Runtime: **Docker**
3. Add **PostgreSQL** service → copy `DATABASE_URL`
4. Add **Redis** service → copy `REDIS_URL`
5. Set these environment variables in Railway:

```
SECRET_KEY=<generate with python3>
APP_ENV=production
DEBUG=false
DOCS_URL=null
DATABASE_URL=postgresql+asyncpg://<railway-postgres-url>
SYNC_DATABASE_URL=postgresql+psycopg2://<railway-postgres-url>
REDIS_URL=<railway-redis-url>
CELERY_BROKER_URL=<railway-redis-url>
CELERY_RESULT_BACKEND=<railway-redis-url>
ALLOWED_ORIGINS=["https://your-app.vercel.app"]
MODEL_PATH=app/ml/artifacts/v1.pkl
MIN_AUC_THRESHOLD=0.75
PREDICTION_BATCH_SIZE=500
CHUNK_SIZE=1000
UPLOAD_DIR=/tmp/churnguard/uploads
MAX_UPLOAD_SIZE_MB=50
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256
LOG_LEVEL=INFO
```

6. Railway gives you: `https://churnguard-api-xxx.up.railway.app`

> **Railway DB URL conversion**: Railway gives `postgresql://user:pass@host:port/db`
> Add `+asyncpg` for DATABASE_URL and `+psycopg2` for SYNC_DATABASE_URL

### Frontend → Vercel

1. [vercel.com](https://vercel.com) → Add New Project → Import GitHub repo
2. **Root Directory**: `frontend` · **Framework**: Vite
3. Add environment variable:
   ```
   VITE_API_URL=https://churnguard-api-xxx.up.railway.app
   ```
4. Deploy → live URL instantly

Then go back to Railway and update `ALLOWED_ORIGINS` to include your Vercel URL.

---

## Common commands

```bash
make up           # Start full stack
make down         # Stop (keeps DB data)
make down-v       # Stop + wipe volumes (fresh DB)
make logs         # Follow app + frontend logs
make test         # Unit tests in container
make test-all     # Full suite with coverage
make shell        # bash into app container
```
