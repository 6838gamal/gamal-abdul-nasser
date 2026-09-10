"""add knowledge embeddings and message embeddings

Revision ID: 20260201_0000
Revises: <ضع آخر revision عندك>
Create Date: 2026-02-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table_name, "c": column_name})
    return result.scalar() is not None


def _has_extension(conn, ext_name: str) -> bool:
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_extension WHERE extname = :n"
    ), {"n": ext_name})
    return result.scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()

    # ═══════════════════════════════════════════════════════
    # 1) pgvector extension
    # ═══════════════════════════════════════════════════════
    print("\n[1/4] pgvector extension")
    if not _has_extension(conn, "vector"):
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
            print("   ✓ enabled pgvector")
        except Exception as e:
            print(f"   ✗ failed: {e}")
            raise
    else:
        print("   ↩ pgvector already enabled")

    # ═══════════════════════════════════════════════════════
    # 2) knowledge_entries.embedding
    # ═══════════════════════════════════════════════════════
    print("\n[2/4] knowledge_entries.embedding")
    if not _has_column(conn, "knowledge_entries", "embedding"):
        op.execute("""
            ALTER TABLE knowledge_entries
            ADD COLUMN embedding vector(768)
        """)
        print("   ✓ added embedding column")
    else:
        print("   ↩ column already exists")

    # ═══════════════════════════════════════════════════════
    # 3) IVFFlat index on knowledge_entries
    # ═══════════════════════════════════════════════════════
    print("\n[3/4] knowledge_entries ivfflat index")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_embedding
        ON knowledge_entries
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
    print("   ✓ index ensured")

    # ═══════════════════════════════════════════════════════
    # 4) message_embeddings table
    # ═══════════════════════════════════════════════════════
    print("\n[4/4] message_embeddings table")
    op.execute("""
        CREATE TABLE IF NOT EXISTS message_embeddings (
            id SERIAL PRIMARY KEY,
            message_id INTEGER NOT NULL
                REFERENCES messages(id) ON DELETE CASCADE,
            embedding vector(768) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_embeddings_message_id
        ON message_embeddings (message_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_message_embeddings_vec
        ON message_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)
    print("   ✓ table + indexes ensured")

    print("\n" + "═" * 50)
    print(" Migration completed")
    print("═" * 50 + "\n")


def downgrade() -> None:
    print("\n Rollback embeddings")
    op.execute("DROP TABLE IF EXISTS message_embeddings CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_entries_embedding")
    op.execute("ALTER TABLE knowledge_entries DROP COLUMN IF EXISTS embedding")
    # لا نحذف الـ extension لأنه قد يُستخدم من جداول أخرى
    print(" ✓ Done\n")
