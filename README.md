## PostgreSQL 18 Database Schema (Tables & Columns)

Every tenant-scoped table enforces strict multi-business isolation via `business_id` and PostgreSQL Row-Level Security (RLS)[cite: 5, 18, 19].

1. **`businesses`**: `id (PK)`, `name`, `tone_of_voice`, `readiness_score`, `readiness_threshold`, `created_at`[cite: 5, 15, 18]
2. **`users`**: `id (PK)`, `business_id (FK)`, `email`, `password_hash`, `full_name`, `created_at`[cite: 5, 18]
3. **`connections`**: `id (PK)`, `business_id (FK)`, `provider (claude|gemini|openrouter|ollama|gmail)`, `encrypted_credentials`, `endpoint_url`, `status`, `last_tested_at`[cite: 5, 18]
4. **`prompt_versions`**: `id (PK)`, `business_id (FK)`, `prompt_key`, `version_num`, `template_text`, `required_variables (JSONB)`, `is_active`, `created_by`, `created_at`[cite: 5, 6, 18, 19]
5. **`agent_roles`**: `id (PK)`, `business_id (FK)`, `name`, `goal`, `system_prompt`, `tone`, `allowed_skills (JSONB)`, `knowledge_sources (JSONB)`, `model_id`, `handover_rules`, `is_default`, `created_at`[cite: 6, 18, 19]
6. **`sitemaps`**: `id (PK)`, `business_id (FK)`, `parent_sitemap_id (FK)`, `url`, `sync_frequency (daily|weekly|15d|30d)`, `fail_threshold_x`, `fail_action`, `last_synced_at`, `created_at`[cite: 7, 8, 18]
7. **`knowledge_pages`**: `id (PK)`, `business_id (FK)`, `source_type (sitemap|single_url|upload)`, `canonical_url`, `title`, `content_hash`, `health_status (active|watch|quarantined|archived)`, `consecutive_failures`, `redirect_to_url`, `last_checked_at`, `created_at`[cite: 7, 8, 18]
8. **`sitemap_page_links`**: `sitemap_id (PK, FK)`, `page_id (PK, FK)`, `discovered_at` *(handles duplicate URLs across multiple sitemaps without duplicating chunks)*[cite: 7, 18]
9. **`page_change_history`**: `id (PK)`, `business_id (FK)`, `page_id (FK)`, `sync_run_id`, `change_type (added|updated|removed|status_changed|redirected)`, `diff_summary`, `recorded_at`[cite: 8, 18]
10. **`knowledge_chunks`**: `id (PK)`, `business_id (FK)`, `page_id (FK)`, `chunk_index`, `heading_path`, `content_text`, `image_s3_key`, `image_description`, `embedding (halfvec)`, `search_tsv (tsvector)`, `created_at`[cite: 8, 18, 19]
11. **`instructions_and_skills`**: `id (PK)`, `business_id (FK)`, `item_type (instruction|skill)`, `title`, `markdown_body`, `version_num`, `applies_to_role_ids (UUID[])`, `is_active`, `source_notes (JSONB)`, `created_at`[cite: 7, 8, 18, 19]
12. **`email_threads`**: `id (PK)`, `business_id (FK)`, `gmail_thread_id`, `subject`, `thread_note`, `last_message_at`, `created_at`[cite: 8, 9, 18]
13. **`email_messages`**: `id (PK)`, `business_id (FK)`, `thread_id (FK)`, `gmail_message_id`, `sender`, `body_text`, `message_note`, `sent_at`[cite: 8, 9, 18]
14. **`chat_sessions`**: `id (PK)`, `business_id (FK)`, `user_id (FK)`, `mode (ask|teach)`, `active_role_id (FK)`, `title`, `created_at`[cite: 9, 19]
15. **`chat_messages`**: `id (PK)`, `business_id (FK)`, `session_id (FK)`, `sender (user|assistant|human_expert)`, `content`, `role_id (FK)`, `prompt_version_id (FK)`, `citations (JSONB)`, `trace_metadata (JSONB)`, `feedback_vote (up|down)`, `feedback_reason`, `escalated_to_human (BOOLEAN)`, `created_at`[cite: 9, 10, 13, 18, 19]
16. **`lessons`**: `id (PK)`, `business_id (FK)`, `source_message_id (FK)`, `markdown_path`, `title`, `rule_summary`, `confidence_score`, `status (pending|approved|disabled)`, `approved_by`, `created_at`[cite: 10, 18]
17. **`eval_cases`**: `id (PK)`, `business_id (FK)`, `suite_name`, `version_tag`, `category (knowledge|screenshot|unanswerable|skill|synonym|url_health|chat|injection|escalation|teach)`, `question`, `expected_answer`, `expected_source`, `is_hidden (BOOLEAN)`, `created_at`[cite: 12, 13, 14, 20, 21]
18. **`eval_results`**: `id (PK)`, `business_id (FK)`, `eval_case_id (FK)`, `run_batch_id`, `step_name`, `model_id`, `model_answer`, `judge_model_id`, `judge_score`, `judge_reason`, `human_grade`, `human_note`, `cost_usd`, `latency_ms`, `created_at`[cite: 12, 13, 18]
19. **`model_routing_rules`**: `id (PK)`, `business_id (FK)`, `job_type`, `complexity (low|medium|high)`, `primary_model_id`, `fallback_model_ids (JSONB)`, `updated_at`[cite: 12, 13]
20. **`self_improve_runs`**: `id (PK)`, `business_id (FK)`, `trigger_eval_case_id (FK)`, `git_branch`, `diff_patch`, `score_before`, `score_after`, `hidden_score_after`, `rounds_used`, `cost_usd`, `status (running|awaiting_approval|merged|reverted|failed)`, `report_summary`, `created_at`[cite: 14]
21. **`model_call_logs`**: `id (PK)`, `business_id (FK)`, `job_type`, `model_id`, `prompt_version_id (FK)`, `role_id (FK)`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost_usd`, `latency_ms`, `escalated_from_model`, `created_at`[cite: 6, 13, 19]

---

## Planned Feature Ideas (4 Original Features — Planned, Not Built)

Full 9-section technical specifications live in the `features/` directory and are prioritized in `ROADMAP.md`[cite: 15, 16, 21]:

1. **Live Gmail Auto-Draft & Human Triage Queue** (`features/gmail-auto-draft-triage.md` — **Priority 1**, Est. 10 hrs)
   * **Problem & Buyer:** Support teams waste hours copying customer emails into the chat and pasting replies back[cite: 9, 15]. SaaS and e-commerce teams pay for zero-click inbox drafting[cite: 15].
   * **Flow & Architecture:** Uses existing Gmail OAuth (`connections`) to watch incoming threads, runs safety guardrails (routing angry/refund/legal threads to a human triage queue)[cite: 5, 10, 15], calls the Knowledge Brain API with the matched `agent_role`[cite: 6, 9, 16], and saves a cited reply directly as a Gmail Draft (`gmail.compose` scope)[cite: 15]. Adds `gmail_draft_queue` table and a "Triage Queue" tab inside `/chat`[cite: 15].
   * **Done When:** 90% of safe incoming emails have an accurate Gmail draft ready within 30 seconds of arrival, and 100% of angry/refund/legal emails are flagged for human review[cite: 10, 16].

2. **Knowledge Gap Detector & Auto-Article Drafter** (`features/knowledge-gap-drafter.md` — **Priority 2**, Est. 8 hrs)
   * **Problem & Buyer:** Help centers go stale because founders do not know which missing articles cause the most support tickets[cite: 15]. Knowledge managers pay to turn real customer blind spots into published docs[cite: 15].
   * **Flow & Architecture:** Clusters recurring "I don't know" escalations and human corrections (`chat_messages` + `lessons`) by semantic similarity, ranks top missing topics by ticket volume, and uses Claude Sonnet 5.5 to draft a ready-to-publish help article[cite: 9, 10, 11, 15]. Adds `knowledge_gaps` table and a "Gaps" sub-panel in `/knowledge`[cite: 15].
   * **Done When:** Approving a drafted gap article and indexing it raises Eval Lab accuracy on those previously unanswered queries from 0% to $\ge 95\%$[cite: 16].

3. **Embeddable Customer Self-Service Widget** (`features/embeddable-support-widget.md` — **Priority 3**, Est. 12 hrs)
   * **Problem & Buyer:** Businesses want customers to get instant answers on their website before submitting a support ticket[cite: 15]. Growing SaaS businesses pay per deflected ticket[cite: 15].
   * **Flow & Architecture:** Provides a single `<script>` tag authenticated via a public domain-restricted widget key, exposing a read-only `/api/widget/ask` endpoint backed by the Knowledge Brain API, strict prompt-injection shields, and seamless handoff to a human support ticket when confidence is low[cite: 9, 10, 15, 16]. Adds `widget_configs` and `widget_sessions` tables plus a "Widget" tab in `/settings`[cite: 15].
   * **Done When:** End-users receive cited answers in $<2.5\text{s}$ on an external test page with zero leakage of internal instructions, skills, or private lessons[cite: 16].

4. **Multi-Language Auto-Translate & Locale Routing** (`features/multi-language-routing.md` — **Priority 4**, Est. 9 hrs)
   * **Problem & Buyer:** Global businesses receive tickets in Spanish, French, German, or Hindi while maintaining help centers only in English[cite: 15]. International SMBs pay to support global customers without hiring multilingual agents[cite: 15].
   * **Flow & Architecture:** Detects incoming language during the router's job-tagging step, translates the query to English for high-precision hybrid retrieval against English chunks, and generates the final response in the customer's native language with locale-appropriate tone[cite: 9, 13, 15]. Adds `supported_locales` to `businesses` and `detected_language` to `chat_messages`[cite: 15].
   * **Done When:** Non-English benchmark questions achieve $\ge 92\%$ factual accuracy against English source docs with accurate native-language phrasing[cite: 16].
