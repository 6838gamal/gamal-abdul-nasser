"""add_knowledge_chunks_with_pgvector auto-detection

Revision ID: knowledge_chunks_001
Revises: <ضع revision السابق>
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import logging

revision = "0004"
down_revision = "0003"   # ← عدّل
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024
logger = logging.getLogger("alembic.runtime.migration")


def _detect_pgvector(conn) -> bool:
    """يكتشف إن كان pgvector متاحاً وقابلاً للتفعيل."""
    try:
        row = conn.execute(sa.text(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        )).first()
        if not row:
            logger.warning("pgvector NOT available — falling back to JSONB")
            return False

        # جرّب التفعيل
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector enabled successfully")
        return True
    except Exception as e:
        logger.warning(f"pgvector activation failed: {e} — falling back to JSONB")
        return False


def upgrade() -> None:
    conn = op.get_bind()
    use_pgvector = _detect_pgvector(conn)

    # ============ الجدول ============
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_type", "source_id", "chunk_index", name="uq_chunk_source"),
    )

    op.create_index("ix_chunks_source_type", "knowledge_chunks", ["source_type"])
    op.create_index("ix_chunks_source_id", "knowledge_chunks", ["source_id"])
    op.create_index("ix_chunks_content_hash", "knowledge_chunks", ["content_hash"])
    op.create_index("ix_chunks_source", "knowledge_chunks", ["source_type", "source_id"])

    # ============ embedding ============
    if use_pgvector:
        op.execute(
            f"ALTER TABLE knowledge_chunks "
            f"ADD COLUMN embedding vector({EMBEDDING_DIM}) NOT NULL"
        )
        op.execute(
            "CREATE INDEX ix_chunks_embedding_hnsw ON knowledge_chunks "
            "USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
        logger.info("Created knowledge_chunks with VECTOR column")
    else:
        op.add_column(
            "knowledge_chunks",
            sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        )
        op.create_index(
            "ix_chunks_embedding_gin",
            "knowledge_chunks",
            ["embedding"],
            postgresql_using="gin",
        )
        logger.warning("Created knowledge_chunks with JSONB column (fallback mode)")

    # فهرس metadata
    op.create_index(
        "ix_chunks_metadata_gin",
        "knowledge_chunks",
        ["metadata"],
        postgresql_using="gin",
    )

    # سجّل الوضع في جدول إعدادات (اختياري لكن مفيد)
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS _system_config (
            key VARCHAR(50) PRIMARY KEY,
            value TEXT
        )
    """))
    op.execute(sa.text("""
        INSERT INTO _system_config (key, value)
        VALUES ('vector_mode', :mode)
        ON CONFLICT (key) DO UPDATE SET value = :mode
    """).bindparams(mode="pgvector" if use_pgvector else "jsonb"))


def downgrade() -> None:
    for idx in [
        "ix_chunks_metadata_gin",
        "ix_chunks_source",
        "ix_chunks_content_hash",
        "ix_chunks_source_id",
        "ix_chunks_source_type",
    ]:
        op.drop_index(idx, table_name="knowledge_chunks", if_exists=True)

    conn = op.get_bind()
    try:
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw"))
    except Exception:
        pass
    try:
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_chunks_embedding_gin"))
    except Exception:
        pass

    op.drop_table("knowledge_chunks")
    op.execute(sa.text("DELETE FROM _system_config WHERE key='vector_mode'"))
