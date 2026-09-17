# alembic/versions/0003_add_last_summarized_and_msg_embeddings_unique.py

"""
add last_summarized_count to leads
add unique constraint on message_embeddings.message_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

import logging

from alembic import op
import sqlalchemy as sa


log = logging.getLogger("alembic.runtime.migration")

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


# ══════════════════════════════════════════════════════════════════════
# أدوات مساعدة idempotent
# ══════════════════════════════════════════════════════════════════════

def _table_exists(table: str) -> bool:
    """فحص وجود جدول."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = :t
          AND table_schema = current_schema()
    """), {"t": table})
    return result.scalar() is not None


def _column_exists(table: str, column: str) -> bool:
    """فحص وجود عمود."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = :t
          AND column_name = :c
          AND table_schema = current_schema()
    """), {"t": table, "c": column})
    return result.scalar() is not None


def _unique_constraint_exists(name: str, table: str) -> bool:
    """فحص وجود قيد UNIQUE بالاسم على الجدول."""
    bind = op.get_bind()
    result = bind.execute(sa.text("""
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = :n
          AND table_name = :t
          AND constraint_type = 'UNIQUE'
          AND table_schema = current_schema()
    """), {"n": name, "t": table})
    return result.scalar() is not None


# ══════════════════════════════════════════════════════════════════════
# Upgrade
# ══════════════════════════════════════════════════════════════════════

def upgrade() -> None:
    # ─────────────────────────────────────
    # 1. leads.last_summarized_count
    # ─────────────────────────────────────
    if not _table_exists("leads"):
        log.warning("SKIP: table leads does not exist")
    elif _column_exists("leads", "last_summarized_count"):
        log.info("SKIP: leads.last_summarized_count already exists")
    else:
        log.info("Adding leads.last_summarized_count ...")
        op.add_column(
            "leads",
            sa.Column(
                "last_summarized_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="عدد الرسائل عند آخر تلخيص",
            ),
        )
        log.info("✓ leads.last_summarized_count added")

    # ─────────────────────────────────────
    # 2. message_embeddings unique constraint
    # ─────────────────────────────────────
    if not _table_exists("message_embeddings"):
        log.warning("SKIP: table message_embeddings does not exist")
        return

    if _unique_constraint_exists(
        "message_embeddings_message_id_key",
        "message_embeddings",
    ):
        log.info("SKIP: message_embeddings unique constraint already exists")
        return

    log.info("Cleaning duplicate message_embeddings rows ...")
    bind = op.get_bind()
    deleted = bind.execute(sa.text("""
        DELETE FROM message_embeddings a
        USING message_embeddings b
        WHERE a.id > b.id
          AND a.message_id = b.message_id
    """)).rowcount
    log.info("✓ Removed %d duplicate row(s)", deleted or 0)

    log.info("Creating unique constraint message_embeddings_message_id_key ...")
    op.create_unique_constraint(
        "message_embeddings_message_id_key",
        "message_embeddings",
        ["message_id"],
    )
    log.info("✓ message_embeddings unique constraint created")


# ══════════════════════════════════════════════════════════════════════
# Downgrade
# ══════════════════════════════════════════════════════════════════════

def downgrade() -> None:
    if _table_exists("message_embeddings") and _unique_constraint_exists(
        "message_embeddings_message_id_key",
        "message_embeddings",
    ):
        op.drop_constraint(
            "message_embeddings_message_id_key",
            "message_embeddings",
            type_="unique",
        )
        log.info("✓ Dropped message_embeddings unique constraint")

    if _table_exists("leads") and _column_exists(
        "leads", "last_summarized_count"
    ):
        op.drop_column("leads", "last_summarized_count")
        log.info("✓ Dropped leads.last_summarized_count")
