# OneStopShop

The SUNRISE One Stop Shop application.

## Database Bootstrap (PostgreSQL + Django migrations)

This branch bootstraps the data layer for Task 1/2/3 with:

- Dockerized PostgreSQL
- Dockerized API service (Django)
- Dedicated `content` schema
- Django ORM models + migrations
- Deterministic seed commands

### What is included

- Core Task 1 entities:
	- `offer`, `offer_type`, `organization`, `contact`, `domain`, `oss_user`, `user_organization`, `user_role`, `source_type`, `target_profile`
- Task 2 decisions:
	- D-01: `contact.contact_approved` (default `false`)
	- D-02: `offer_contact` junction table
- Lookup/reference seeding from Task 2 (`OSS_Mapping_Seed.json`)
- Task 3 offer seeding from sample data (`OSS_Sample_Offers.json`)
	- Inserts only real + illustrative records
	- Skips fictional offers

## Quick Start

### 1) Install dependencies

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" -m pip install -r backend/requirements.txt
```

### 2) Start PostgreSQL

```powershell
docker compose up -d postgres
```

### 2b) Start PostgreSQL + API layer together

```powershell
docker compose up -d --build
```

To rebuild from a clean state:

```powershell
docker compose down -v
docker compose up -d --build --wait
```

The API container runs:

1. `python manage.py migrate`
2. `python manage.py seed_lookups`
3. `python manage.py seed_offers`
4. `python manage.py runserver 0.0.0.0:8000`

### 3) Configure environment

Create a local `.env` from `backend/.env.example` and adjust values if needed.

Default values:

- `POSTGRES_DB=oss_db`
- `POSTGRES_USER=oss_user`
- `POSTGRES_PASSWORD=oss_password`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`
- `POSTGRES_SCHEMA=content`
- `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver`
- `CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200`
- `CORS_ALLOW_CREDENTIALS=false`
- `API_PORT=8000`

For local Python runs, use `POSTGRES_HOST=localhost`.
For compose API container runs, `POSTGRES_HOST` is automatically set to `postgres`.

### 3b) Verify running services

```powershell
docker compose ps
docker compose logs --tail 100 api
```

### 4) Run migrations

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" backend/manage.py migrate
```

### 5) Seed lookup data and offers

```powershell
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" backend/manage.py seed_lookups
"d:/Masters/UNIBZ/Semester 2/GDSD - Sweden/.venv/Scripts/python.exe" backend/manage.py seed_offers
```

## Local URLs

When compose is running, use:

- API base: `http://localhost:8000/api`
- API Swagger UI: `http://localhost:8000/api` or `http://localhost:8000/api/docs`
- OpenAPI schema JSON: `http://localhost:8000/api/openapi.json`
- Health check: `http://localhost:8000/api/health`

## Current API Endpoints

All endpoints are read-only (`GET`):

- `/api` - Swagger UI
- `/api/docs` - same Swagger UI page
- `/api/openapi.json` - OpenAPI 3 schema
- `/api/health` - service health
- `/api/lookups/offer-types` - OfferType reference data
- `/api/lookups/domains` - Domain reference data
- `/api/scraping/runs` - recent scraping run summaries
	- optional query param: `limit`
- `/api/scraping/runs/{run_id}` - scraping run detail by UUID
- `/api/offers` - offer list
	- optional query params: `q`, `status`, `offer_type`, `organization`, `target_profile`, `domain`, `country`, `page`, `page_size`, `limit`
	- response metadata: `count`, `page`, `page_size`, `total_pages`, `limit`, `results`
- `/api/offers/{offer_id}` - offer detail by UUID

## Angular Demo UI

An Angular frontend is included in `backend/ui/` with two routes:

- `http://localhost:4200/offers` - offer explorer with search, filters, cards, and classic pagination
- `http://localhost:4200/admin/scrapper` - read-only scraper run tracking page

Start the UI:

```powershell
cd backend/ui
npm install
npm start
```

Build the UI:

```powershell
cd backend/ui
npm run build
```

The UI expects backend API at `http://localhost:8000/api`.
If origin calls are blocked, confirm `CORS_ALLOWED_ORIGINS` in `.env` includes `http://localhost:4200`.

### Quick smoke test (PowerShell)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/health"
Invoke-RestMethod -Uri "http://localhost:8000/api/scraping/runs"
Invoke-RestMethod -Uri "http://localhost:8000/api/lookups/offer-types"
Invoke-RestMethod -Uri "http://localhost:8000/api/lookups/domains"
Invoke-RestMethod -Uri "http://localhost:8000/api/offers?limit=5"
```

## Scraper Worker (Background Job)

The compose stack includes a dedicated `scraper-worker` service that runs the university scraper on a schedule.

Worker startup sequence:

1. `python manage.py migrate`
2. `python manage.py seed_lookups`
3. `python manage.py run_scraper_worker`

Runtime behavior:

- deterministic extraction first (BeautifulSoup/JSON-LD/text heuristics)
- optional Ollama fallback (`qwen3-coder:480b-cloud`) when confidence is low
- freshness policy: mark stale candidates in `details.scraping`, never auto-archive
- source fetch failures (for example HTTP 404/410) are stored as failed runs in `scraping_run` with structured error metadata, and do not automatically mark offers stale in that same failed cycle

### Run It

Start full stack (DB + API + worker):

```powershell
docker compose up -d --build
docker compose ps
```

Watch scraper worker logs:

```powershell
docker compose logs -f scraper-worker
```

Run one manual scrape cycle:

```powershell
docker compose exec api python manage.py run_scrape_once
```

Run only one source:

```powershell
docker compose exec api python manage.py run_scrape_once --source-key unibz_master_software_engineering
```

Dry-run (no DB writes):

```powershell
docker compose exec api python manage.py run_scrape_once --dry-run
```

### See Scraper Results

Recent run summaries:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/scraping/runs?limit=20" | ConvertTo-Json -Depth 6
```

Latest run detail with error payload and counters:

```powershell
$id = (Invoke-RestMethod -Uri "http://localhost:8000/api/scraping/runs?limit=1").results[0].id
Invoke-RestMethod -Uri ("http://localhost:8000/api/scraping/runs/" + $id) | ConvertTo-Json -Depth 8
```

### Configure The Scraper

Set values in `.env` (copy from `.env.example`).

Required startup behavior setting:

- Set `SCRAPER_RUN_ON_START=true` in `.env` to run one scrape cycle immediately when the worker starts.

Defaults:

- `SCRAPER_TIMEOUT_SECONDS=30` (HTTP request timeout per source page)
- `SCRAPER_INTERVAL_MINUTES=360` (scheduler interval)
- `SCRAPER_RUN_ON_START=true` (run one scrape cycle immediately at worker startup)
- `SCRAPER_LLM_FALLBACK_THRESHOLD=0.60` (use Ollama fallback when deterministic confidence is below threshold)
- `SCRAPER_USER_AGENT=SUNRISE-OSS-Scraper/1.0`
- `INGESTION_BOT_USERNAME=ingestion_bot`
- `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- `OLLAMA_MODEL=qwen3-coder:480b-cloud`
- `OLLAMA_TIMEOUT_SECONDS=45`

Source URLs and metadata are configured in `backend/content/scrapers/source_registry.py`.

### How Often It Runs

- By default, the worker runs every `360` minutes (every 6 hours).
- If `SCRAPER_RUN_ON_START=true`, one run happens immediately at startup, then recurring runs follow the interval.
- Scheduler cadence is controlled by `SCRAPER_INTERVAL_MINUTES`.

### What The Scraper Actually Does

For each configured source page, it:

1. Fetches HTML with timeout and user-agent.
2. Extracts offer title/summary/details deterministically (H1/title/meta/JSON-LD/paragraph fallback).
3. Optionally calls Ollama fallback for low-confidence extraction.
4. Upserts into `offer` using natural identity `(link, organization, offer_type)`.
5. Updates `offer_domain` relations based on source mapping.
6. Writes telemetry in `scraping_run` (`success`/`failed`, counters, logs, error metadata).
7. Applies freshness policy as non-destructive stale candidate flags in `offer.details.scraping`.

Important failure semantics:

- `404`/`410` are recorded as `failed` runs in `scraping_run`.
- Failures are visible via `/api/scraping/runs` and `/api/scraping/runs/{run_id}`.
- For `404`/`410`, scraper offers tied to the invalid source are deleted and counted in `offers_deleted`.
- Failed fetches in a cycle do not trigger stale-marking side effects for that failed source in the same cycle.

### Troubleshooting Commands

```powershell
docker compose logs --tail 200 scraper-worker
docker compose logs --tail 100 api
docker compose exec api python manage.py run_scrape_once --source-key unibz_erasmus_mobility --disable-llm-fallback
```

Stop services:

```powershell
docker compose down
```

## Seed Sources

- `backend/seed_data/task2/OSS_Mapping_Seed.json`
- `backend/seed_data/task3/OSS_Sample_Offers.json`

The offer seeder excludes fictional Task 3 records by design:

- `{offer_006}`
- `{offer_015}`
- `{offer_016}`
- `{offer_017}`
