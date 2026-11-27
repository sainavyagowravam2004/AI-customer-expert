# AI Customer Expert — Multi-Tenant SaaS Support Platform

Multi-tenant AI customer support SaaS built with **Python 3.14 (async)**, **FastAPI**, **SQLAlchemy 2.0**, **Alembic**, **PostgreSQL 18 (pgvector + FTS)**, **Jinja2 + HTMX**, and **Docker Compose**.

## Core Features
- **Feature 1 — Workspace & Settings (/login, /settings):** Multi-tenant isolation via PostgreSQL FORCE ROW LEVEL SECURITY (app.current_business_id), Fernet-encrypted API keys (Claude, Gemini, OpenRouter, Ollama, Gmail), PII masking, 3 ready Agent Roles, and per-call cost/token logging.
- **Feature 2 — Knowledge Brain (/knowledge):** 5 knowledge sources (Sitemaps, Page URLs, Instructions, Skills, Past Emails) with pre-crawl summaries, URL health states (Active, Watch, Quarantined, Archived), and hybrid halfvec + BM25 Reciprocal Rank Fusion (RRF) search.
- **Feature 3 — Ask & Teach Chat (/chat, /inbox):** Grounded Q&A with source citations and cost trace, explicit Teach Me mode saving lessons to lessons/, 10-pattern prompt-injection shield, and automatic human escalation for angry/refund/legal queries.
- **Feature 4 & 5 — Eval Lab & Self-Improve Loop (/evals):** 14-model catalog comparison, Local-Only offline switch, and branch-isolated lesson/prompt patches with human approval.
- **Feature 6 — Go Live in 15 Minutes (/go-live):** Guided onboarding wizard that indexes knowledge, auto-generates starting benchmark cases, and unlocks live chat once the Readiness Score reaches 80+.

## Quick Start (One Command)
- Run: docker compose up -d --build
- Migrate: docker compose exec web alembic upgrade head
- Test: docker compose exec web python -m pytest -v
- Open http://localhost:8000/login and click One-Click Demo Login.

## Running Locally With Only the 2 Local Models
1. Pull both local Ollama models: ollama pull gemma4:e4b and ollama pull qwen3.5:4b
2. Verify ollama list shows both models and Ollama is running at http://localhost:11434.
3. In Eval Lab (/evals), enable Local-Only Switch (or leave cloud API keys blank in Settings) to run 100% offline at .00 cost.

## Documentation & Planned Features
- [UX.md](UX.md) — Task 0 screen map, internal tabs, and wireframes
- [DATABASE.md](DATABASE.md) — Schema, indexes, RLS isolation, and D1-D15 answers
- [STACK.md](STACK.md) — Tech stack decisions and S1-S7 / M1-M5 answers
- [THINKING.md](THINKING.md) — 3-round engineering thinking log
- [ROADMAP.md](ROADMAP.md) & [features/](features/) — 4 planned future features
