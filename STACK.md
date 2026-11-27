# Step 2: Tech Stack & Model Decisions (S1-S7, M1-M5)

## Language & Mandatory Stack
- Language: Python 3.14 (async, type hints end-to-end)
- Backend & UI: FastAPI + Jinja2 Templates + HTMX + Tailwind CSS
- ORM & Migrations: SQLAlchemy 2.0 (asyncpg) + Alembic
- Database & Vector Engine: PostgreSQL 18 + pgvector (halfvec(768)) + pg_trgm + Full-Text Search (tsvector)
- Deployment: Docker Compose (web, worker, db)

## Stack Questions (S1-S7)
- S1 (Background Jobs & No Redis at Start): Postgres-backed job tables keep state transactional with tenant data and eliminate Redis operational overhead at launch. Add Valkey/Redis when background polling exceeds ~200 jobs/sec or Postgres CPU stays above 70%.
- S2 (Raw SQL vs ORM): Hybrid RRF search (halfvec <=> :emb + ts_rank_cd) and SET LOCAL app.current_business_id RLS calls use parameterized raw SQL for deterministic HNSW index plans; CRUD operations use SQLAlchemy 2.0.
- S3 (Crawling): httpx + BeautifulSoup4 crawls static help centers politely (~20 pages/min, <80 MB RAM). Headless Playwright is needed only for client-rendered SPAs with <100 chars of static HTML.
- S4 (Screenshots & Uploads): Extracted text/captions live in PostgreSQL; binary files live in tenant-scoped storage/{business_id}/ behind a storage interface ready for Cloudflare R2 / S3.
- S5 (Past Emails): Gmail REST API with minimal gmail.readonly and gmail.compose scopes, batching 20 threads per sync and deduplicating by threadId.
- S6 (Auth & Token Storage): Session cookies with bcrypt password hashing; API keys and OAuth tokens are encrypted at rest with Fernet and never logged.
- S7 (Hosting & Cost): 4 vCPU / 8 GB VPS with Docker Compose costs ~/month vs. ~-/month for managed PaaS + managed Postgres + separate vector DB.

## Model Questions (M1-M5)
- M1 (Embeddings): Local nomic-embed-text (halfvec(768)) with deterministic fallback costs .00 / 1,000 pages vs. ~.12/1M tokens on hosted APIs.
- M2 (Model Routing by Job): Job Tagging -> qwen3.5:4b ( local) or Qwen 3.7 Flash (.03/.13 per 1M); Support Replies -> gemma4:e4b ( local) or Gemini 3 Flash (.50/.00 per 1M); Skill/Lesson Synthesis & Judge -> Claude Opus 5.5 (/ per 1M).
- M3 (Reading Screenshots): gemma4:e4b (.00/100 images locally) and nvidia/nemotron-3.5-super-vl:free (.00 on OpenRouter); Gemini 3.8 Flash (~.04/100 images) as paid fallback.
- M4 (Agents): Custom typed router (app/core/models_catalog.py) gives exact token/cost logging and zero framework overhead.
- M5 (Prompt Caching): Static system prompt + active Instructions + approved Skills (~1,800 tokens) are cached on repeated calls, cutting input prompt spend by ~80-90%.
