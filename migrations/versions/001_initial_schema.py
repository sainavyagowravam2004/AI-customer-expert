"""initial schema with 21 tables and multi-tenant RLS

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-26 15:50:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = [
    "users",
    "connections",
    "prompt_versions",
    "agent_roles",
    "sitemaps",
    "knowledge_pages",
    "sitemap_page_links",
    "page_change_history",
    "knowledge_chunks",
    "instructions_and_skills",
    "email_threads",
    "email_messages",
    "chat_sessions",
    "chat_messages",
    "lessons",
    "eval_cases",
    "eval_results",
    "model_routing_rules",
    "self_improve_runs",
    "model_call_logs",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # 1. businesses
    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), unique=True, nullable=False),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("brand_tone", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 2. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="owner", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. connections
    op.create_table(
        "connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("config_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(30), server_default="disconnected", nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("business_id", "provider", name="uq_business_provider"),
    )

    # 4. prompt_versions
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. agent_roles
    op.create_table(
        "agent_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("default_model", sa.String(120), server_default="qwen3.5:4b", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.2", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 6. sitemaps
    op.create_table(
        "sitemaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("root_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 7. knowledge_pages
    op.create_table(
        "knowledge_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sitemap_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sitemaps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("raw_markdown", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(30), server_default="indexed", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 8. sitemap_page_links
    op.create_table(
        "sitemap_page_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_url", sa.String(1000), nullable=False),
        sa.Column("anchor_text", sa.String(500), nullable=True),
    )

    # 9. page_change_history
    op.create_table(
        "page_change_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_hash", sa.String(64), nullable=True),
        sa.Column("new_hash", sa.String(64), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 10. knowledge_chunks
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_pages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding halfvec(768);")
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;")
    op.execute("CREATE INDEX idx_chunks_embedding ON knowledge_chunks USING hnsw (embedding halfvec_cosine_ops);")
    op.execute("CREATE INDEX idx_chunks_tsv ON knowledge_chunks USING GIN (search_tsv);")

    # 11. instructions_and_skills
    op.create_table(
        "instructions_and_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), server_default="instruction", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 12. email_threads
    op.create_table(
        "email_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_thread_id", sa.String(255), nullable=True),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("status", sa.String(40), server_default="needs_review", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 13. email_messages
    op.create_table(
        "email_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("email_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_type", sa.String(30), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("draft_status", sa.String(30), server_default="sent", nullable=False),
        sa.Column("citations_json", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 14. chat_sessions
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), server_default="Support Chat", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 15. chat_messages
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 16. lessons
    op.create_table(
        "lessons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("trigger_pattern", sa.Text(), nullable=False),
        sa.Column("learned_rule", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), server_default="approved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 17. eval_cases
    op.create_table(
        "eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(80), server_default="general", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 18. eval_results
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("eval_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("eval_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("actual_answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 19. model_routing_rules
    op.create_table(
        "model_routing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(50), server_default="ollama", nullable=False),
        sa.Column("model_name", sa.String(120), server_default="qwen3.5:4b", nullable=False),
        sa.Column("fallback_model", sa.String(120), server_default="gemma4:e4b", nullable=False),
    )

    # 20. self_improve_runs
    op.create_table(
        "self_improve_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("lessons_proposed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 21. model_call_logs
    op.create_table(
        "model_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("prompt_preview", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Enable Row-Level Security (RLS) on all tenant tables
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (
                current_setting('app.current_business_id', true) IS NULL
                OR current_setting('app.current_business_id', true) = ''
                OR business_id = current_setting('app.current_business_id', true)::uuid
            );
            """
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    op.drop_table("businesses")