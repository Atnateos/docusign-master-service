# DocuSign Master Service — What To Build

## 0. Getting Started — Account, Repo & Submission

### Create your account
- Create a GitHub account if you don't already have one (or use your existing one).
- Create a free DocuSign Developer account at the DocuSign developer sign-up page — this gives you a free eSignature sandbox account with full API access, no paid plan required.
- Send your GitHub username to the project contact so you can be invited/granted access as needed.

### Set up your own repository
- Create a new repository named `docusign-master-service`.
- Initialize it with a `README.md`, a Python `.gitignore`, and this document (saved as `DESIGN.md`).

### Timeline
- Total timeline: **1 month** from kickoff to final submission.
- Suggested milestones:
  - **Week 1** — Project set up, DocuSign developer sandbox access, authentication working (getting a valid access token + resolving the account's API base URL).
  - **Week 2** — Requesting and paging through envelope data from DocuSign works, including handling rate limits correctly.
  - **Week 3** — Turning the downloaded data into clean tables works, for the main record types (Envelopes, Recipients, Documents, Templates).
  - **Week 4** — Saving/uploading the finished tables, handling errors and resume gracefully, testing, and final submission.

### How to submit
- Push all code to your repository and make sure it runs from scratch (someone else should be able to clone it and get it running by following your README).
- Include a `README.md` that explains: how to set it up, what settings/credentials it needs, how to run it, and how to run the tests.
- Include a short write-up describing what you built, how it was working (what you tested and confirmed worked), what's incomplete, and anything you weren't able to finish.
- Share the repository link with the project contact ahead of the 1-month deadline.

## 1. What This Service Is, In Plain Terms

This service's only job is to **pull data out of DocuSign on demand and hand it off in a clean, organized form.**

Think of it as a pipeline with one job: given a DocuSign account, go get its envelope/signing data, clean it up, and put it somewhere it can be picked up and used. Nothing about scheduling ("when to run"), and nothing about what happens to the data afterward — this service only handles the extraction and cleanup step.

Another system (a "Coordinator") will be the one calling this service to say "start pulling data for this account", "how's it going", "cancel it", etc. This service just needs to respond correctly to those requests and do the work reliably — including respecting DocuSign's rate limits so it never gets the account throttled unexpectedly.

## 2. What Exactly You Need To Build

At a high level, build these pieces:

1. **A way to authenticate to DocuSign** using credentials provided to the service, get an access token, and resolve which base API URL to use for that specific account (DocuSign accounts are hosted on different regional base URLs, discovered via a single call after login).
2. **A way to request data from DocuSign, one page at a time** — envelopes first (using a date-range filter, since DocuSign requires one), then the recipients/documents/templates attached to each envelope.
3. **Rate limit handling** — DocuSign enforces both short burst limits and per-minute/per-hour limits per account and per integration. Your service must watch for "too many requests" responses, wait the amount of time DocuSign tells it to wait, and then continue — never just fail immediately because of rate limiting.
4. **A way to save each page of data as it comes in**, so a long-running extraction doesn't lose progress if interrupted.
5. **A way to clean up and reorganize each record type** into simple, consistent tables (e.g., turn a nested "Envelope" record into a flat `envelopes` table, plus related `recipients` and `documents` tables).
6. **A way to save the finished tables** as files and upload them to shared storage (MinIO), organized so other systems know where to find them (by account and by date).
7. **A tracking system for each run** ("job"), so that at any point you can ask "what's the status of this run?" and get an accurate answer — including if it crashed partway through, in which case it should be able to pick back up from the last page it successfully fetched instead of starting over.
8. **A small set of API endpoints** so the Coordinator system can start a run, check its status, cancel it, resume it, and list past runs.
9. **Basic security**, so that only the Coordinator (not just anyone on the network) can call this service.
10. **Basic error handling**, so that if DocuSign or the storage system is briefly unavailable, the service retries a few times automatically instead of failing immediately — and if it keeps failing, it records what went wrong somewhere so someone can investigate later, instead of silently losing the request.

That's the entire scope. Everything below just explains each of these in more detail.

## 3. Tech Stack

- **Language/Framework:** Python, using **FastAPI** to build the API
- **Database:** PostgreSQL — to keep track of every run ("job"), its progress checkpoints, and its status
- **File storage:** MinIO — where the finished, cleaned-up data gets uploaded
- **Packaging:** Docker, so it can run the same way anywhere

You don't need anything more exotic than this — no message queues, no extra infrastructure beyond a database and a place to store files.

## 4. Step-By-Step: How A Single Run Should Work

1. The Coordinator tells your service: "start pulling data for this DocuSign account."
2. Your service saves a new "job" record so it can track progress, and immediately replies "started" (it doesn't make the Coordinator wait for the whole thing to finish).
3. In the background, your service:
   a. Gets a valid access token, and resolves the correct account-specific base API URL.
   b. Requests envelopes created/modified within the configured date range, one page at a time.
   c. For each envelope, fetches its recipients and document list.
   d. If DocuSign responds with "too many requests," waits the required time and tries again.
   e. Saves a checkpoint (which page/position it just finished) so it can resume from here if interrupted.
   f. Repeats until there are no more pages.
4. Once envelope data is pulled, it reorganizes the raw data into clean tables, saves them, and uploads them to storage.
5. It marks the job as complete — or as failed, with a reason, if something went wrong.
6. At any point, the Coordinator can ask your service for the status of a job, cancel it, or resume it from wherever it left off.

## 5. What Data To Pull From DocuSign

Build support for at least these record types to start:

- Envelopes (the core signing transaction — status, dates, subject, custom fields)
- Recipients (who was sent the envelope, their role and signing status)
- Documents (the files attached to each envelope)
- Templates (reusable envelope definitions, if the account uses them)

Each one should end up as its own clean table (or a small handful of related tables) after processing.

## 6. API Endpoints You Need To Expose

| What it does | Example endpoint |
|---|---|
| Start a new run for an account | `POST /scan/start` |
| Check the status of a run | `GET /scan/{id}/status` |
| Cancel a run | `POST /scan/{id}/cancel` |
| Resume a failed/cancelled run | `POST /scan/{id}/resume` |
| List past/active runs | `GET /scan/list` |
| Remove a run's records | `DELETE /scan/{id}/remove` |
| Trigger the "clean up the data" step for a run | `POST /normalize/{id}` |
| Check that credentials are valid before starting a run | `POST /validate-credentials` |
| Basic health check (is the service up) | `GET /health` |

You don't need to build much beyond this list — keep the API small and focused.

## 7. Handling Errors Gracefully

- If a call to DocuSign or to storage fails because of a temporary problem (timeout, connection issue, "server busy" response), automatically try again a few times before giving up.
- If DocuSign responds with a rate-limit error, treat it differently from a normal failure: wait the amount of time DocuSign specifies (or a sensible default if it doesn't say) and continue, rather than counting it as one of your normal retry attempts.
- If it still fails after retries, don't lose the request — save a record of what failed and why, so it can be looked into later.
- If the service crashes or gets restarted mid-run, it should be able to tell (from its tracking records) that a run was left in an unfinished state, and either resume it from its last checkpoint or mark it as failed rather than leaving it stuck forever.

## 8. Security

- Only the Coordinator system should be able to call this service — every request coming in should be signed with a shared secret key, and the service should reject anything that isn't signed correctly.
- Credentials used to log into DocuSign should never be permanently stored in plain form — use them to get a token, then handle them carefully (encrypt at rest if a private key must be kept for repeated server-to-server authentication).

## 9. What NOT To Build

This service does **not** need:
- Any deduplication or "has this record changed" logic — every run just produces a fresh set of tables.
- Any PII masking, anonymization, or redaction of the data — the data is passed through as-is.

Keep the scope limited to: connect → page through data (respecting rate limits) → clean up → store → track status.

---

## 10. Technical Appendix

Everything above is the plain-language version. This section spells out the same system in implementation-level detail.

### 10.1 Architecture Overview

```
Coordinator (calls via signed HTTP)
        │
        ▼
DocuSign Master Service (FastAPI)
        │
        ├── Auth: DocuSign OAuth 2.0 (JWT Grant for server-to-server, or Authorization Code Grant)
        │         + a userinfo call to resolve the account's base API URL
        ├── Fetch: DocuSign eSignature REST API v2.1 (date-range filtered envelope list,
        │         position-based pagination via `start_position`/`count`/`next_uri`)
        ├── Rate limiting: burst + per-minute/per-hour limits, honor `Retry-After` on 429
        ├── Checkpointing: persist last-seen position/date-range cursor per run
        ├── Normalization: flatten DocuSign objects into relational tables
        └── Publish: upload normalized Parquet files to MinIO
```

Envelopes are fetched first (top-level list), then recipients/documents are fetched per envelope — so the pipeline has a natural two-level structure similar to a parent/child fetch.

### 10.2 Job Lifecycle / State Machine

A single `Job` row represents one run (one extraction for one account). Status values:

```
PENDING
  → FETCHING_ENVELOPES
  → FETCHING_DETAILS   (recipients/documents per envelope)
  → NORMALIZING
  → UPLOADING_TO_MINIO
  → COMPLETED
```

Side states: `FAILED`, `CANCELLED`, `CRASHED` (heartbeat timeout while an in-progress state is active).

- A background heartbeat is updated periodically while fetching; a separate maintenance check flags jobs whose heartbeat has gone stale as `CRASHED`.
- Resuming picks back up from the last saved envelope-list cursor/position, and re-checks which envelopes already had their details fetched before continuing to the ones that didn't.

### 10.3 API Endpoints (FastAPI routers)

All endpoints below (except `/health` and `/stats`) require HMAC-signed requests from the Coordinator (`X-DS-Signature`, `X-DS-Timestamp`, `X-DS-Client-ID`, `X-DS-Nonce` headers).

**`scan` router — `/api/scan`**

| Method | Path | Function |
|---|---|---|
| POST | `/scan/start` | `start_scan(request: ScanStartRequest)` — validates payload, creates job, kicks off background workflow, returns 202 with scan id |
| GET | `/scan/{scan_id}/status` | `get_scan_status(scan_id: str)` — returns current job status + pipeline progress |
| POST | `/scan/{scan_id}/cancel` | `cancel_scan(scan_id: str)` — cancels the job |
| POST | `/scan/{scan_id}/resume` | `resume_scan(scan_id: str)` — resumes a failed/cancelled scan from the last completed stage/checkpoint |
| GET | `/scan/list` | `list_scans(organization_id: str \| None, page: int, page_size: int)` — paginated scan listing |
| GET | `/scan/statistics` | `get_scan_statistics()` — aggregate counts by status |
| DELETE | `/scan/{scan_id}/remove` | `remove_scan(scan_id: str)` — deletes job row + local files (blocked while active) |

**`normalization` router — `/api/normalization`**

| Method | Path | Function |
|---|---|---|
| POST | `/normalization/{scan_id}/normalize` | `normalize_scan(scan_id: str, format: str, save_to_disk: bool, upload_to_minio: bool)` — runs normalization → save → (optional) MinIO upload |
| GET | `/normalization/{scan_id}/tables` | `list_normalized_tables(scan_id: str)` — lists normalized table files for a scan |
| GET | `/normalization/supported-objects` | `get_supported_objects()` — static catalog of supported DocuSign objects and their output tables |

**`maintenance` router — `/api/maintenance`**

| Method | Path | Function |
|---|---|---|
| POST | `/maintenance/cleanup` | `cleanup_old_scans(days_old: int)` — deletes scans + local files older than N days |
| POST | `/maintenance/detect-crashed` | `detect_crashed_jobs(timeout_minutes: int)` — flags jobs with stale heartbeats as `CRASHED` |

**`credentials`**

| Method | Path | Function |
|---|---|---|
| POST | `/api/validate-credentials` | `validate_credentials(request: DocuSignCredentials)` — validates DocuSign credentials via a token grant + userinfo call, without creating a job |

**Public/unauthenticated**

| Method | Path | Function |
|---|---|---|
| GET | `/api/health` | `health()` — liveness/readiness probe (DB + MinIO reachability) |
| GET | `/api/stats` | `service_stats()` — lightweight service-level counters |

**`audit` router — `/api/audit`**

| Method | Path | Function |
|---|---|---|
| GET | `/audit/logs` | `get_audit_logs(org_id, event_category, event_type, outcome, from_date, to_date, page, page_size)` — paginated audit log query |
| GET | `/audit/stats` | `get_audit_stats(window_minutes: int)` — rolling-window audit aggregates |

### 10.4 Core Services & Functions

**`JobService`**
- `create_job(scan_id, organization_id, request_config)` — creates the job row (credentials are never persisted in plain form)
- `get_job(scan_id)` — fetches a job by id
- `update_job_status(scan_id, status)` — transitions job status
- `update_heartbeat(scan_id)` — called periodically during long-running stages
- `save_checkpoint(scan_id, stage, cursor_position, records_processed)` / `get_latest_checkpoint(scan_id)`
- `complete_job(scan_id, stats)` / `fail_job(scan_id, error)` / `cancel_job(scan_id)`
- `detect_crashed_jobs(timeout_minutes)` — heartbeat-based crash detection
- `cleanup_old_jobs(days_old)`

**`DocuSignAuthClient`**
- `get_access_token(credentials)` — performs the JWT Grant (or Authorization Code Grant) token exchange; caches the token until near expiry
- `resolve_account_base_url(access_token)` — calls the userinfo endpoint once per run to determine the correct account-specific API base URL and account ID
- `validate_credentials(credentials)` — performs a lightweight token grant + userinfo call to confirm credentials are valid without starting a run

**`DocuSignAPIClient`**
- `list_envelopes(from_date, to_date, start_position)` — fetches one page of envelopes for the configured date range, returning records + the next position (or `None` if done)
- `get_envelope_recipients(envelope_id)` / `get_envelope_documents(envelope_id)` — fetches the child records for a given envelope
- `list_templates(start_position)` — fetches one page of templates
- Internally wraps every call with rate-limit awareness: on a 429, reads the `Retry-After` header (or a configured default), sleeps, and retries — this is separate from, and checked before, the generic retry/backoff logic in §10.5

**`ExtractionService` (top-level orchestrator)**
- `start_scan(request_config)` — creates the job, launches the background workflow, returns immediately
- `_execute_scan(scan_id)` — fetches envelopes page by page (checkpointing between pages), then for each envelope fetches recipients/documents (checkpointing which envelopes are done), then templates
- `resume_scan(scan_id)` — resumes from the last saved checkpoint, picking up mid-envelope-list or mid-detail-fetch as needed
- `cancel_scan(scan_id)`
- `get_scan_status(scan_id)` / `get_scan_statistics()` / `remove_scan(scan_id)`

**`NormalizationService` + per-object normalizers**

Per-object normalizers, each implementing `normalize(records) -> dict[str, list[dict]]`:
- `EnvelopeNormalizer` → `envelopes`
- `RecipientNormalizer` → `recipients`
- `DocumentNormalizer` → `documents`
- `TemplateNormalizer` → `templates`

`NormalizationService.normalize_scan(scan_id, output_format, save_to_disk, upload_to_minio)`:
1. Lists the raw fetched records per object type.
2. Runs each normalizer, saves output as JSON or Parquet.
3. Aggregates stats, marks the job's normalization stage complete.
4. If `upload_to_minio`, uploads via `MinIOClient.upload_normalized_data`.
5. Cleans up local scan data on success.

**`MinIOClient`**
- `upload_file(local_path, object_key)`
- `upload_normalized_data(scan_id, organization_id, processing_date, tables)` — writes to `docusign/{table_name}/glynac_organization_id={org_id}/processing_date={date}/{table}.parquet`
- `ensure_bucket_exists()`

**`AuditService`**
- `write_audit(event_category, event_type, organization_id, outcome, extra_metadata)` — fire-and-forget insert into `audit_logs`, non-blocking

### 10.5 Resilience — Retry, Rate-Limit Handling & Dead-Letter Queue

**`rate_limiter.py`**
- `handle_rate_limit_response(response)` — detects a 429, reads `Retry-After` (falling back to a configured default delay if absent), sleeps, and signals the caller to retry the same request — this check happens **before** generic retry logic, since a rate-limit response is not a failure to count against retry budget, just a "wait and continue" signal

**`retry.py`**
- `is_retryable(exc)` — classifies transient failures (timeouts, connection errors, `500/502/503/504`; `429` is handled separately by the rate limiter, not treated as a generic retryable error)
- `retry_call(fn, max_retries, delays, jitter, op_label)` — bounded-retry executor used around every external call (DocuSign API, MinIO)

**`dlq.py`**
- `write_to_dlq(target_service, operation, payload, attempts, error, organization_id=None, scan_id=None)` — persists an exhausted external call into `failed_external_calls`, scrubbing sensitive fields and capping payload size; never raises
- `scrub_payload(payload)` — redacts sensitive keys before persisting

### 10.6 HMAC Authentication

Dual-key scheme:
- **Coordinator key** — full access (GET/POST/DELETE)
- **Engineer/read-only key** — GET-only, for inspection endpoints
- Required headers: `X-DS-Signature`, `X-DS-Timestamp`, `X-DS-Client-ID`, `X-DS-Nonce`
- Canonical string: `METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(BODY)`, signed with HMAC-SHA256
- Nonce replay protection, timestamp freshness window, and audit logging on every auth outcome (success, missing header, expired timestamp, invalid signature, replay, unauthorized)
- Implemented as a FastAPI dependency (`Depends(hmac_auth_required)`) applied per-router

### 10.7 Data Models

**`Job` (`jobs` table)**

Core identity/status/timing columns, plus:
- `date_range_from`, `date_range_to` (the envelope query window for this run)
- `entity_record_counts` (JSON, per-object-type counts)
- `normalized_at`, `minio_uploaded_at`
- `last_heartbeat` — used for crash detection

**`JobCheckpoint` (`job_checkpoints` table)**

FK to `jobs.id`: `stage` (`envelopes`/`details`/`templates`), `cursor_position`, `records_processed`, `last_updated_at` — this is what makes resume and crash-recovery possible without re-fetching everything.

**`AuditLog` (`audit_logs` table)**

`event_category`, `event_type`, `actor_client_id`, `actor_role`, `organization_id`, `entity_type`, `resource_type`, `resource_id`, `http_method`, `endpoint`, `request_ip`, `status_code`, `outcome`, `severity`, `error_detail`, `extra_metadata`, `created_at`.

**`FailedExternalCall` (`failed_external_calls` table)**

`target_service`, `operation`, `organization_id`, `scan_id`, `payload` (scrubbed/capped JSON), `attempts`, `last_error`, `status`, `created_at`.

### 10.8 Config

Environment-driven config (`Settings` via Pydantic `BaseSettings`), grouped as:
- App metadata (`APP_ENV`, `LOG_LEVEL`)
- Database (`DATABASE_URL`, pool size)
- DocuSign API (`DOCUSIGN_INTEGRATION_KEY`, `DOCUSIGN_USER_ID`, `DOCUSIGN_PRIVATE_KEY`/JWT key path, `DOCUSIGN_AUTH_SERVER`, timeouts)
- Rate limiting (`DOCUSIGN_MAX_RETRIES_ON_429`, default retry-after fallback if the header is missing)
- Pagination (`DOCUSIGN_DEFAULT_PAGE_SIZE`)
- MinIO (`MINIO_ENDPOINT`, `MINIO_BUCKET`, credentials)
- Resilience (`EXTERNAL_CALL_MAX_RETRIES`, `EXTERNAL_CALL_RETRY_DELAYS`, `EXTERNAL_CALL_JITTER`, `DLQ_PAYLOAD_MAX_BYTES`)
- HMAC (`HMAC_ENABLED`, `HMAC_SECRET_KEY_CORE`, `HMAC_SECRET_KEY_ENGINEER`, `HMAC_SIGNATURE_MAX_AGE`, `HMAC_CLIENT_CONFIG`)
- Health check flags

Environment-specific validation (staging/production) should fail fast at startup if secrets are placeholder values, HMAC is disabled, or DEBUG is enabled in production.

### 10.9 Deployment

Single Docker image, deployed to Nomad in dev/stage/prod, one task per environment, health check on `/api/health`, secrets templated from Vault (`secrets/data/docusign/docusign-master-service-{env}`).

### 10.10 Utils

- `deep_serialize(obj)` — recursively converts Decimals, UUIDs, Enums, and datetimes into JSON-safe structures for API responses
- `calculate_duration(start, end)` — ISO datetime diff in seconds for job duration reporting
- `build_pagination_info(page, page_size, total)` — standard pagination envelope
- `Encrypter` — optional Fernet-based symmetric encryption utility for any sensitive config blob (e.g. the JWT signing private key) that must be stored at rest
