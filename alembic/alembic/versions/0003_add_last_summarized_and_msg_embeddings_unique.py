# alembic/versions/0003_add_last_summarized_and_msg_embeddings_unique.py

"""
add last_summarized_count to leads
add unique constraint on message_embeddings.message_id

Revision ID: xxxx
Revises: <previous_revision>
Create Date: ...
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """فحص وجود عمود (idempotent migration)."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column})
    return result.scalar() is not None


def _constraint_exists(name: str, table: str) -> bool:
    """فحص وجود قيد (idempotent migration)."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = :n AND table_name = :t
    """), {"n": name, "t": table})
    return result.scalar() is not None


def upgrade() -> None:
    # ─────────────────────────────────────
    # 1. leads.last_summarized_count
    # ─────────────────────────────────────
    if not _column_exists("leads", "last_summarized_count"):
        op.add_column(
            "leads",
            sa.Column(
                "last_summarized_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
        op.execute("""
            COMMENT ON COLUMN leads.last_summarized_count
            IS 'عدد الرسائل عند آخر تلخيص'
        """)
    else:
        print("SKIP: leads.last_summarized_count already exists")

    # ─────────────────────────────────────
    # 2. message_embeddings unique index
    # ─────────────────────────────────────
    if not _constraint_exists(
        "message_embeddings_message_id_key",
        "message_embeddings",
    ):
        # احذف أي duplicates قبل إنشاء الفهرس
        op.execute("""
            DELETE FROM message_embeddings a
            USING message_embeddings b
            WHERE a.id > b.id
              AND a.message_id = b.message_id
        """)

        op.create_unique_constraint(
            "message_embeddings_message_id_key",
            "message_embeddings",
            ["message_id"],
        )
    else:
        print("SKIP: message_embeddings unique constraint already exists")


def downgrade() -> None:
    if _constraint_exists(
        "message_embeddings_message_id_key",
        "message_embeddings",
    ):
        op.drop_constraint(
            "message_embeddings_message_id_key",
            "message_embeddings",
            type_="unique",
        )

    if _column_exists("leads", "last_summarized_count"):
        op.drop_column("leads", "last_summarized_count")
