# Step 1: Database Architecture & Design (D1–D15)

## 1. Tables & Multi-Tenant Isolation
Every tenant table carries `business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE` and is protected by PostgreSQL `FORCE ROW LEVEL SECURITY` (`app_user` role) using `current_setting('app.current_business_id', true)::uuid`:
- `businesses`, `users`, `connections`, `agent_roles`, `prompt_templates`
- `sitemaps`, `knowledge_pages`, `knowledge_chunks` (`embedding halfvec(768)`, `search_tsv tsvector`), `page_change_history`, `instructions_and_skills`
- `email_threads`, `email_messages`, `chat_sessions`, `chat_messages`, `lessons`
- `eval_cases`, `eval_results`, `self_improve_runs`, `model_call_logs`

## 2. Database Design Answers (D1–D15)
- **D1 (Tenant Isolation):** Shared schema with `business_id` on every table plus `FORCE ROW LEVEL SECURITY` (`app_user` role). One DB per business breaks connection pooling at 1,000 businesses; RLS scales cleanly past 10,000 tenants.
- **D2 (Nested Sitemaps):** Self-referencing `parent_sitemap_id` FK on `sitemaps` models arbitrary sitemap index depth cleanly.
- **D3 (Duplicate URLs Across Sitemaps):** One canonical row per `(business_id, url)` in `knowledge_pages` prevents duplicate embeddings; `preview_sitemap` reports duplicates skipped.
- **D4 (URL Health & Pending Query):** `status` column (`active`, `watch`, `quarantined`, `archived`) plus `consecutive_failures` on `knowledge_pages`. Query: `SELECT url, status, consecutive_failures FROM knowledge_pages WHERE business_id = :bid AND status IN ('watch', 'quarantined');`.
- **D5 (Change History Storage):** SHA-256 `content_hash` on `knowledge_pages` + diffs in `page_change_history` only when changed (<130 MB/year for 1,000 pages checked daily at 2% daily churn).
- **D6 (Chunking & Screenshots):** 800-character chunks with 120-character overlap; screenshot captions/OCR append into page chunks with `[Screenshot Captions]` markers.
- **D7 (Vectors):** `halfvec(768)` with `HNSW` index cuts vector storage by 50% vs `float32` with <0.5% recall loss; model switches re-embed chunks in background batches.
- **D8 (Hybrid Search):** Combine PostgreSQL `tsvector` (`ts_rank_cd`) + `pg_trgm` similarity with `halfvec` cosine distance via Reciprocal Rank Fusion (`1/(60+rank_v) + 1/(60+rank_k)`).
- **D9 (Past Emails):** Normalized threads and messages stored in `email_threads` and `email_messages` deduplicated by Gmail `threadId`.
- **D10 (Teaching Loop):** `chat_messages` holds Q&A; `lessons` stores structured rules exported to `lessons/*.md`.
- **D11 (Chats & Citations):** `chat_sessions` groups turns; `chat_messages.citations_json` logs exact sources per reply.
- **D12 (Skills & Instructions):** `instructions_and_skills` stores `kind` (`instruction` or `skill`), `is_active`, and versioned updates.
- **D13 (Model Call Logging):** `model_call_logs` records `business_id`, `task_type`, `provider`, `model_name`, `tokens_in`, `tokens_out`, and `cost_usd`.
- **D14 (Account Deletion):** `DELETE FROM businesses WHERE id = :bid` cascades across all child tables (`ON DELETE CASCADE`), followed by `storage/{business_id}/` cleanup.
- **D15 (Prompts & Roles):** `prompt_templates` versions every prompt edit; `agent_roles` links roles to `system_prompt` and `default_model`.
