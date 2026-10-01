# docusign-master-service

A service that pulls envelope/signing data out of DocuSign on demand,
normalizes it into clean tables, and publishes it to shared storage (MinIO).
See [`DESIGN.md`](./DESIGN.md) for the full specification.

> **Status:** Day 1 bootstrap. The app, Docker stack, and `/api/health`
> endpoint are working end-to-end. Auth, extraction, normalization, and the
> scan API are not implemented yet — see [Project status](#project-status)
> below for what's done vs. pending.

## Requirements

- Docker and Docker Compose
- (For local, non-Docker development) Python 3.11+

## Setup

1. Clone the repo and copy the environment template:

   ```bash
   git clone <this-repo-url>
   cd docusign-master-service
   cp .env.example .env
   ```

2. Fill in `.env`. For Day 1, the defaults work as-is for local Docker use —
   you only need to touch `DOCUSIGN_*` values once auth is implemented in
   Week 1. `HMAC_SECRET_KEY_CORE` / `HMAC_SECRET_KEY_ENGINEER` should be
   changed to real random secrets before anything beyond local dev.

3. Build and start everything (app + PostgreSQL + MinIO):

   ```bash
   docker compose up --build
   ```

4. Confirm it's healthy:

   ```bash
   curl http://localhost:8000/api/health
   ```

   A healthy response looks like:

   ```json
   {"status": "ok", "dependencies": {"database": true, "minio": true}}
   ```

   If either dependency isn't reachable yet (e.g. containers still starting),
   this returns HTTP 503 with `"status": "degraded"` and shows which
   dependency failed.

The API docs (Swagger UI) are available at `http://localhost:8000/docs` once
the app is running.

### Running without Docker (local dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# You'll need a local Postgres and MinIO reachable at the URLs in .env,
# or point DATABASE_URL / MINIO_ENDPOINT at remote ones.
uvicorn app.main:app --reload
```

## Configuration

All configuration is environment-driven; see [`.env.example`](./.env.example)
for the full list with defaults. Settings are grouped by concern in
[`app/core/config.py`](./app/core/config.py):

| Group | Purpose |
|---|---|
| App | environment name, log level, debug flag |
| Database | PostgreSQL connection for job tracking |
| DocuSign API | integration key, user id, JWT private key path, auth server |
| Rate limiting | retry/backoff behavior on DocuSign 429 responses |
| Pagination | default page size for envelope listing |
| MinIO | endpoint, credentials, bucket name |
| Resilience | retry counts/delays for transient failures, DLQ payload cap |
| HMAC | shared secrets and settings for request signing |

In `staging`/`production`, the app refuses to start if `DEBUG=true`,
`HMAC_ENABLED=false`, or any secret is still set to a placeholder value
(see `Settings.validate_for_environment`).

## Running tests

```bash
pip install -r requirements.txt
pytest
```

(Test suite is currently minimal — expands alongside each milestone.)

## Project status

**Done**
- Repo structure, Docker Compose stack (app + PostgreSQL + MinIO)
- FastAPI app bootstrap, environment-driven config, logging
- `GET /api/health` — checks real DB and MinIO connectivity

**Not yet implemented** (see `DESIGN.md` for the full plan)
- DocuSign JWT auth + base-URL resolution
- Envelope/recipient/document/template fetching with pagination and rate-limit handling
- Job tracking, checkpointing, and resume
- `scan`, `normalization`, `credentials`, `maintenance`, `audit` endpoints
- Normalization into flat tables + Parquet upload to MinIO
- HMAC request signing
- Retry/dead-letter-queue handling for transient failures

## Repository layout

```
app/
  api/            FastAPI routers (health today; scan/normalization/etc. later)
  core/           config, logging, shared exceptions
  db/             SQLAlchemy engine/session + ORM base
  services/       business logic (JobService, ExtractionService, ...)
  docusign/       DocuSign auth + API client, rate limiter, retry logic
  normalization/  per-object-type normalizers
  storage/        MinIO client
  schemas/        Pydantic request/response models
  utils/          small shared helpers
tests/
migrations/       Alembic migrations (added with the first DB model)
```
