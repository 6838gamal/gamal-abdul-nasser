"""add visitor lead message tables (idempotent)

Revision ID: 20260101_0000
Revises: <ضع هنا revision السابق>
Create Date: 2026-01-01 00:00:00

Migration آمنة:
- تفحص وجود الجداول قبل إنشائها.
- تفحص وجود الأعمدة قبل إضافتها.
- تفحص وجود الـ indexes قبل إنشائها.
- تفحص وجود الـ enum قبل إنشائه.
- تتعامل مع قواعد بيانات قديمة أو جزئية.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# ══════════════════════════════════════════════════════════════════════
# Revision identifiers
# ══════════════════════════════════════════════════════════════════════

revision = "0001"
down_revision = None  # ⚠️ عدّلها لتشير لآخر migration عندك
branch_labels = None
depends_on = None


# ══════════════════════════════════════════════════════════════════════
# Helpers — فحص الوجود
# ══════════════════════════════════════════════════════════════════════


def _get_bind():
    return op.get_bind()


def _inspector():
    return inspect(_get_bind())


def table_exists(table_name: str) -> bool:
    """هل الجدول موجود؟"""
    try:
        return table_name in _inspector().get_table_names()
    except Exception:
        return False


def column_exists(table_name: str, column_name: str) -> bool:
    """هل العمود موجود داخل الجدول؟"""
    try:
        if not table_exists(table_name):
            return False

        columns = _inspector().get_columns(table_name)
        return any(c["name"] == column_name for c in columns)

    except Exception:
        return False


def index_exists(index_name: str, table_name: str = None) -> bool:
    """هل الـ index موجود؟"""
    try:
        bind = _get_bind()

        if table_name:
            indexes = _inspector().get_indexes(table_name)
            return any(i["name"] == index_name for i in indexes)

        # بحث عام في كل الجداول
        for tbl in _inspector().get_table_names():
            for idx in _inspector().get_indexes(tbl):
                if idx["name"] == index_name:
                    return True

        return False

    except Exception:
        return False


def unique_constraint_exists(constraint_name: str, table_name: str) -> bool:
    """هل القيد الفريد موجود؟"""
    try:
        if not table_exists(table_name):
            return False

        constraints = _inspector().get_unique_constraints(table_name)
        return any(c["name"] == constraint_name for c in constraints)

    except Exception:
        return False


def enum_exists(enum_name: str) -> bool:
    """هل النوع enum موجود في PostgreSQL؟"""
    try:
        bind = _get_bind()

        result = bind.execute(
            sa.text(
                "SELECT 1 FROM pg_type WHERE typname = :name"
            ),
            {"name": enum_name},
        )

        return result.scalar() is not None

    except Exception:
        return False


def foreign_key_exists(
    table_name: str,
    fk_name: str = None,
    referred_table: str = None,
) -> bool:
    """هل الـ foreign key موجود؟"""
    try:
        if not table_exists(table_name):
            return False

        fks = _inspector().get_foreign_keys(table_name)

        for fk in fks:
            if fk_name and fk.get("name") == fk_name:
                return True
            if referred_table and fk.get("referred_table") == referred_table:
                return True

        return False

    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════
# Helper — إضافة عمود بأمان
# ══════════════════════════════════════════════════════════════════════


def safe_add_column(
    table_name: str,
    column: sa.Column,
    server_default=None,
):
    """
    أضف عموداً فقط إذا لم يكن موجوداً.
    """

    if column_exists(table_name, column.name):
        print(f"   ↩ column exists: {table_name}.{column.name}")
        return

    try:
        op.add_column(table_name, column)
        print(f"   ✓ added column: {table_name}.{column.name}")
    except Exception as e:
        print(f"   ✗ failed to add {table_name}.{column.name}: {e}")


def safe_create_index(
    index_name: str,
    table_name: str,
    columns: list,
    unique: bool = False,
):
    """
    أنشئ index فقط إذا لم يكن موجوداً.
    """

    if index_exists(index_name, table_name):
        print(f"   ↩ index exists: {index_name}")
        return

    try:
        op.create_index(index_name, table_name, columns, unique=unique)
        print(f"   ✓ created index: {index_name}")
    except Exception as e:
        print(f"   ✗ failed to create index {index_name}: {e}")


# ══════════════════════════════════════════════════════════════════════
# UPGRADE
# ══════════════════════════════════════════════════════════════════════


def upgrade() -> None:

    bind = _get_bind()
    dialect = bind.dialect.name

    print("\n══════════════════════════════════════════════════")
    print(" Migration: visitor + lead + message")
    print(f" Dialect: {dialect}")
    print("══════════════════════════════════════════════════")

    # ══════════════════════════════════════════════════
    # 1) enum: lead_stage
    # ══════════════════════════════════════════════════

    print("\n[1/3] lead_stage enum")

    if dialect == "postgresql":

        if not enum_exists("lead_stage"):
            try:
                lead_stage_enum = postgresql.ENUM(
                    "NEW",
                    "QUALIFYING",
                    "QUALIFIED",
                    "CONTACT_REQUESTED",
                    "READY_TO_BUY",
                    "HANDED_OFF",
                    "LOST",
                    name="lead_stage",
                )
                lead_stage_enum.create(bind, checkfirst=True)
                print("   ✓ created enum: lead_stage")
            except Exception as e:
                print(f"   ✗ failed to create enum: {e}")
        else:
            print("   ↩ enum exists: lead_stage")

    # ══════════════════════════════════════════════════
    # 2) visitors
    # ══════════════════════════════════════════════════

    print("\n[2/3] visitors table")

    if not table_exists("visitors"):

        try:
            op.create_table(
                "visitors",
                sa.Column("id", sa.Integer, primary_key=True),

                sa.Column(
                    "visitor_uid",
                    sa.String(64),
                    nullable=False,
                ),

                sa.Column(
                    "first_seen",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),

                sa.Column(
                    "last_seen",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),

                sa.Column("user_agent", sa.String(255), nullable=True),
                sa.Column("ip_hash", sa.String(64), nullable=True),
                sa.Column("locale", sa.String(16), nullable=True),
                sa.Column("referrer", sa.String(500), nullable=True),
            )

            print("   ✓ created table: visitors")

        except Exception as e:
            print(f"   ✗ failed to create visitors: {e}")

    else:
        print("   ↩ table exists: visitors")

        # أضف أي أعمدة ناقصة
        safe_add_column(
            "visitors",
            sa.Column("visitor_uid", sa.String(64), nullable=True),
        )
        safe_add_column(
            "visitors",
            sa.Column(
                "first_seen",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        safe_add_column(
            "visitors",
            sa.Column(
                "last_seen",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        safe_add_column(
            "visitors",
            sa.Column("user_agent", sa.String(255)),
        )
        safe_add_column(
            "visitors",
            sa.Column("ip_hash", sa.String(64)),
        )
        safe_add_column(
            "visitors",
            sa.Column("locale", sa.String(16)),
        )
        safe_add_column(
            "visitors",
            sa.Column("referrer", sa.String(500)),
        )

    # indexes visitors
    safe_create_index(
        "ix_visitors_visitor_uid",
        "visitors",
        ["visitor_uid"],
        unique=True,
    )

    # ══════════════════════════════════════════════════
    # 3) leads
    # ══════════════════════════════════════════════════

    print("\n[3/3] leads table")

    if not table_exists("leads"):

        try:
            if dialect == "postgresql":
                stage_column = postgresql.ENUM(
                    "NEW",
                    "QUALIFYING",
                    "QUALIFIED",
                    "CONTACT_REQUESTED",
                    "READY_TO_BUY",
                    "HANDED_OFF",
                    "LOST",
                    name="lead_stage",
                    create_type=False,
                )
            else:
                stage_column = sa.String(32)

            op.create_table(
                "leads",
                sa.Column("id", sa.Integer, primary_key=True),

                sa.Column(
                    "visitor_id",
                    sa.Integer,
                    sa.ForeignKey(
                        "visitors.id",
                        ondelete="CASCADE",
                    ),
                    nullable=False,
                ),

                sa.Column(
                    "stage",
                    stage_column,
                    nullable=False,
                    server_default="NEW",
                ),

                sa.Column(
                    "score",
                    sa.Integer,
                    nullable=False,
                    server_default="0",
                ),

                sa.Column("name", sa.String(120), nullable=True),
                sa.Column("company", sa.String(120), nullable=True),
                sa.Column("contact", sa.String(255), nullable=True),
                sa.Column("project_type", sa.String(120), nullable=True),
                sa.Column("problem", sa.Text, nullable=True),
                sa.Column("desired_solution", sa.Text, nullable=True),
                sa.Column("budget", sa.String(120), nullable=True),
                sa.Column("timeline", sa.String(120), nullable=True),
                sa.Column("intent", sa.String(100), nullable=True),
                sa.Column("next_action", sa.String(100), nullable=True),
                sa.Column("summary", sa.Text, nullable=True),
                sa.Column("handoff_reason", sa.Text, nullable=True),
                sa.Column(
                    "handoff_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
                sa.Column(
                    "notified_owner",
                    sa.Integer,
                    nullable=False,
                    server_default="0",
                ),

                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),

                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )

            print("   ✓ created table: leads")

        except Exception as e:
            print(f"   ✗ failed to create leads: {e}")

    else:
        print("   ↩ table exists: leads")

        # أضف الأعمدة الناقصة
        safe_add_column(
            "leads",
            sa.Column("visitor_id", sa.Integer, nullable=True),
        )
        safe_add_column(
            "leads",
            sa.Column("stage", sa.String(32),
                      server_default="NEW"),
        )
        safe_add_column(
            "leads",
            sa.Column("score", sa.Integer, server_default="0"),
        )
        safe_add_column("leads", sa.Column("name", sa.String(120)))
        safe_add_column("leads", sa.Column("company", sa.String(120)))
        safe_add_column("leads", sa.Column("contact", sa.String(255)))
        safe_add_column(
            "leads", sa.Column("project_type", sa.String(120))
        )
        safe_add_column("leads", sa.Column("problem", sa.Text))
        safe_add_column(
            "leads", sa.Column("desired_solution", sa.Text)
        )
        safe_add_column("leads", sa.Column("budget", sa.String(120)))
        safe_add_column("leads", sa.Column("timeline", sa.String(120)))
        safe_add_column("leads", sa.Column("intent", sa.String(100)))
        safe_add_column(
            "leads", sa.Column("next_action", sa.String(100))
        )
        safe_add_column("leads", sa.Column("summary", sa.Text))
        safe_add_column(
            "leads", sa.Column("handoff_reason", sa.Text)
        )
        safe_add_column(
            "leads",
            sa.Column("handoff_at", sa.DateTime(timezone=True)),
        )
        safe_add_column(
            "leads",
            sa.Column("notified_owner", sa.Integer,
                      server_default="0"),
        )
        safe_add_column(
            "leads",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        safe_add_column(
            "leads",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    # indexes leads
    safe_create_index("ix_leads_visitor_id", "leads", ["visitor_id"])
    safe_create_index("ix_leads_stage", "leads", ["stage"])
    safe_create_index("ix_leads_score", "leads", ["score"])

    # ══════════════════════════════════════════════════
    # 4) messages
    # ══════════════════════════════════════════════════

    print("\n[4/3] messages table")

    if not table_exists("messages"):

        try:
            op.create_table(
                "messages",
                sa.Column("id", sa.Integer, primary_key=True),

                sa.Column(
                    "lead_id",
                    sa.Integer,
                    sa.ForeignKey(
                        "leads.id",
                        ondelete="CASCADE",
                    ),
                    nullable=False,
                ),

                sa.Column("role", sa.String(16), nullable=False),
                sa.Column("content", sa.Text, nullable=True),
                sa.Column("tool_name", sa.String(64), nullable=True),
                sa.Column("tool_payload", sa.Text, nullable=True),
                sa.Column("tool_result", sa.Text, nullable=True),

                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
            )

            print("   ✓ created table: messages")

        except Exception as e:
            print(f"   ✗ failed to create messages: {e}")

    else:
        print("   ↩ table exists: messages")

        safe_add_column(
            "messages",
            sa.Column("lead_id", sa.Integer, nullable=True),
        )
        safe_add_column(
            "messages",
            sa.Column("role", sa.String(16)),
        )
        safe_add_column("messages", sa.Column("content", sa.Text))
        safe_add_column(
            "messages", sa.Column("tool_name", sa.String(64))
        )
        safe_add_column(
            "messages", sa.Column("tool_payload", sa.Text)
        )
        safe_add_column(
            "messages", sa.Column("tool_result", sa.Text)
        )
        safe_add_column(
            "messages",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )

    # indexes messages
    safe_create_index("ix_messages_lead_id", "messages", ["lead_id"])
    safe_create_index(
        "ix_messages_created_at",
        "messages",
        ["created_at"],
    )

    print("\n══════════════════════════════════════════════════")
    print(" Migration completed successfully")
    print("══════════════════════════════════════════════════\n")


# ══════════════════════════════════════════════════════════════════════
# DOWNGRADE
# ══════════════════════════════════════════════════════════════════════


def downgrade() -> None:

    bind = _get_bind()
    dialect = bind.dialect.name

    print("\n══════════════════════════════════════════════════")
    print(" Rollback: visitor + lead + message")
    print("══════════════════════════════════════════════════")

    # messages
    if table_exists("messages"):
        try:
            op.drop_table("messages")
            print("   ✓ dropped table: messages")
        except Exception as e:
            print(f"   ✗ failed to drop messages: {e}")
    else:
        print("   ↩ table not found: messages")

    # leads
    if table_exists("leads"):
        try:
            op.drop_table("leads")
            print("   ✓ dropped table: leads")
        except Exception as e:
            print(f"   ✗ failed to drop leads: {e}")
    else:
        print("   ↩ table not found: leads")

    # visitors
    if table_exists("visitors"):
        try:
            op.drop_table("visitors")
            print("   ✓ dropped table: visitors")
        except Exception as e:
            print(f"   ✗ failed to drop visitors: {e}")
    else:
        print("   ↩ table not found: visitors")

    # enum
    if dialect == "postgresql" and enum_exists("lead_stage"):
        try:
            bind.execute(
                sa.text("DROP TYPE IF EXISTS lead_stage")
            )
            print("   ✓ dropped enum: lead_stage")
        except Exception as e:
            print(f"   ✗ failed to drop enum: {e}")
    else:
        print("   ↩ enum not found: lead_stage")

    print("\n══════════════════════════════════════════════════")
    print(" Rollback completed")
    print("══════════════════════════════════════════════════\n")
