# OneStopShop

The SUNRISE One Stop Shop application.

## Quick Start

```bash
docker compose up -d --build
```

This starts three services: `postgres`, `api`, `scraper-worker`.

The API container runs on startup:
1. `python manage.py migrate`
2. `python manage.py seed_lookups`
3. `python manage.py runserver 0.0.0.0:8000`

The scraper worker runs on startup:
1. `python manage.py seed_lookups`
2. `python manage.py run_scraper_worker`

To rebuild from a clean state:

```bash
docker compose down -v
docker compose up -d --build --wait
```

## Local URLs

| URL | Description |
|-----|-------------|
| `http://localhost:8000/api` | Swagger UI |
| `http://localhost:8000/api/docs` | Swagger UI (alias) |
| `http://localhost:8000/api/openapi.json` | OpenAPI 3 schema |
| `http://localhost:8000/api/health` | Health check |
| `http://localhost:4200/offers` | Offer explorer UI |
| `http://localhost:4200/admin/scrapper` | Scraper dashboard |

## API Endpoints

All endpoints are read-only (`GET`):

**Lookups**
- `/api/lookups/offer-types` — OfferType reference data
- `/api/lookups/domains` — Domain reference data

**Offers**
- `/api/offers` — offer list (`q`, `status`, `offer_type`, `organization`, `target_profile`, `domain`, `country`, `page`, `page_size`, `limit`)
- `/api/offers/{offer_id}` — offer detail

**Scraping runs**
- `/api/scraping/runs` — recent run summaries (`limit`)
- `/api/scraping/runs/{run_id}` — run detail with full log

**Dashboard / telemetry**
- `/api/scraping/overview?window=24h|7d|30d` — KPI counts + timeline buckets
- `/api/scraping/sources/health` — per-source URL queue stats from `CrawlUrl` table
- `/api/scraping/llm/stats?window=24h|7d|30d` — extraction method split + confidence averages

## Scraper Architecture

The scraper runs as two decoupled APScheduler jobs inside the `scraper-worker` container:

### Job 1 — Crawler (every 360 min)

Discovers URLs for each configured source and writes them into the `CrawlUrl` queue table.

- Crawl-enabled sources: BFS depth-1 link discovery filtered by include/exclude patterns
- Non-crawl sources: single known URL
- Uses `get_or_create` — existing URLs keep their schedule, archived URLs are not resurrected

### Job 2 — Scraper (every 5 min)

Claims up to `SCRAPER_BATCH_SIZE` (default 10) pending/due URLs from the queue and processes them.

For each URL:

1. Fetch HTML (timeout: `SCRAPER_TIMEOUT_SECONDS`)
2. Run deterministic extraction (BeautifulSoup / JSON-LD / meta / heuristics)
3. For crawl sources: AI relevance check + extraction via Ollama. LLM result wins if confidence ≥ deterministic
4. For non-crawl sources: AI is primary extractor; deterministic is fallback only
5. If content is extractable: upsert offer into DB, link `CrawlUrl.offer`
6. If page is generic or deemed irrelevant: mark URL as **skipped** (not an error)
7. Update `CrawlUrl` status and schedule next check

**Outcome mapping:**

| HTTP result | Consecutive errors | Outcome |
|-------------|-------------------|---------|
| 2xx | — | `done`, next check in 7 days |
| Generic/irrelevant page | — | `done` (skipped), not an error |
| 404 / 410 | — | `archived`; linked offer archived/deleted |
| 5xx / timeout | < 3 | `error`, backoff: 1h → 6h → 24h |
| 5xx / timeout | ≥ 3 | `archived`; linked offer archived |

### URL Status Lifecycle

```
pending → processing → done      (scraped, revisit in 7 days)
                     → archived  (permanent 404/410 or repeated errors)
                     → error     (transient failure, retry with backoff)
```

### What Counts as an Error vs Skipped

- **Error**: HTTP failure (4xx/5xx) or network exception — visible in Errors tab of dashboard
- **Skipped**: Page fetched OK but content rejected (generic homepage title, AI flagged as non-offer) — amber in Runs tab, not an error

## Scraper Dashboard

At `http://localhost:4200/admin/scrapper` — live telemetry, auto-refreshes every 30s.

**Tabs:**

| Tab | What it shows |
|-----|--------------|
| Overview | KPI cards (runs, offers created/updated, URLs skipped, errors), bar charts for run activity and errors over 24h/7d/30d |
| Runs | Browsable list of scraping batches with URL-level results table. Rows: green (ok), amber (skipped), red (error) |
| Sources | Per-source CrawlUrl queue health: total URLs, % done, pending/error/archived counts |
| Extraction | AI vs rules-based method split and confidence scores |
| Errors | Real HTTP/network failures across last 50 runs (skipped URLs excluded) |

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and adjust as needed.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `oss_db` | |
| `POSTGRES_USER` | `oss_user` | |
| `POSTGRES_PASSWORD` | `oss_password` | |
| `POSTGRES_HOST` | `localhost` (local) / `postgres` (compose) | |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_SCHEMA` | `content` | |

### API

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,testserver` | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:4200,http://127.0.0.1:4200` | |
| `API_PORT` | `8000` | |

### Scraper

| Variable | Default | Description |
|----------|---------|-------------|
| `CRAWLER_INTERVAL_MINUTES` | `360` | How often the crawler job runs (URL discovery) |
| `SCRAPER_INTERVAL_MINUTES` | `5` | How often the scraper job runs (URL processing) |
| `SCRAPER_BATCH_SIZE` | `10` | URLs processed per scraper job tick |
| `SCRAPER_REVISIT_DAYS` | `7` | Days before a successfully scraped URL is re-queued |
| `SCRAPER_MAX_CONSECUTIVE_ERRORS` | `3` | Errors before a URL is archived |
| `SCRAPER_TIMEOUT_SECONDS` | `30` | HTTP request timeout per URL |
| `SCRAPER_RUN_ON_START` | `true` | Run both jobs immediately at worker startup |
| `SCRAPER_USER_AGENT` | `SUNRISE-OSS-Scraper/1.0` | |
| `INGESTION_BOT_USERNAME` | `ingestion_bot` | DB user for offer upserts |

### Ollama (AI extraction)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Use `host.docker.internal` on Windows/Mac Docker Desktop |
| `OLLAMA_MODEL` | `qwen3-coder:480b-cloud` | Primary model |
| `OLLAMA_TIMEOUT_SECONDS` | `45` | |
| `OLLAMA_REQUEST_DELAY_SECONDS` | `2` | Delay between Ollama calls |
| `OLLAMA_COOLDOWN_MAX_WAIT_SECONDS` | `65` | Max wait when all models are in cooldown |

If Ollama is not running, AI extraction silently skips and the scraper continues with deterministic extraction only.

## Manual Operations

### Run a single scrape batch now

```bash
docker compose exec api python manage.py run_scrape_once
```

### Run only one source

```bash
docker compose exec api python manage.py run_scrape_once --source-key unibz_master_software_engineering
```

### Dry-run (no DB writes)

```bash
docker compose exec api python manage.py run_scrape_once --dry-run
```

### Watch live logs

```bash
docker compose logs -f scraper-worker
docker compose logs -f api
```

### Inspect queue state

```bash
docker compose exec api python manage.py shell -c "
from content.models import CrawlUrl
from django.db.models import Count
print(CrawlUrl.objects.values('status').annotate(n=Count('id')))
"
```

### Smoke test endpoints

```bash
curl http://localhost:8000/api/health
curl "http://localhost:8000/api/scraping/runs?limit=5"
curl "http://localhost:8000/api/scraping/overview?window=24h"
curl "http://localhost:8000/api/scraping/sources/health"
curl "http://localhost:8000/api/offers?limit=5"
```

## Data Model Highlights

- `Offer` — scraped offer records with organization, type, domains, country
- `ScrapingRun` — one record per scraper batch; holds counters and structured JSON log
- `CrawlUrl` — per-URL queue record (status, next check time, consecutive errors, linked offer)

Migrations: `0001` – `0005` (including `CrawlUrl` table added in `0005`)

## Source Configuration

Sources are defined in `backend/content/scrapers/source_registry.py`.

Each source specifies:
- URL, organization, offer type, country
- `crawl_enabled` — whether BFS discovery runs or a single known URL is used
- `crawl_match_patterns` / `crawl_exclude_patterns` — URL filters for crawl mode
- `llm_fallback_enabled` — whether Ollama is used for this source

## Seed Data

- `backend/seed_data/task2/OSS_Mapping_Seed.json` — lookups (offer types, domains, organizations)
- `backend/seed_data/task3/OSS_Sample_Offers.json` — illustrative offer records (excludes fictional Task 3 placeholders)
