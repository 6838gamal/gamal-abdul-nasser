"""add visitor lead message tables

Revision ID: xxx
Revises: <previous>
Create Date: <date>
"""

from alembic import op
import sqlalchemy as sa


revision = "xxx"
down_revision = "<previous>"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ─────────────────────────────────────
    # visitors
    # ─────────────────────────────────────

    op.create_table(
        "visitors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("visitor_uid", sa.String(64), nullable=False),
        sa.Column(
            "first_seen", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "last_seen", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("locale", sa.String(16)),
        sa.Column("referrer", sa.String(500)),
    )

    op.create_index(
        "ix_visitors_visitor_uid",
        "visitors",
        ["visitor_uid"],
        unique=True,
    )

    # ─────────────────────────────────────
    # lead_stage enum
    # ─────────────────────────────────────

    lead_stage = sa.Enum(
        "NEW", "QUALIFYING", "QUALIFIED",
        "CONTACT_REQUESTED", "READY_TO_BUY",
        "HANDED_OFF", "LOST",
        name="lead_stage",
    )

    # ─────────────────────────────────────
    # leads
    # ─────────────────────────────────────

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "visitor_id", sa.Integer,
            sa.ForeignKey("visitors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", lead_stage, nullable=False,
                  server_default="NEW"),
        sa.Column("score", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("name", sa.String(120)),
        sa.Column("company", sa.String(120)),
        sa.Column("contact", sa.String(255)),
        sa.Column("project_type", sa.String(120)),
        sa.Column("problem", sa.Text),
        sa.Column("desired_solution", sa.Text),
        sa.Column("budget", sa.String(120)),
        sa.Column("timeline", sa.String(120)),
        sa.Column("intent", sa.String(100)),
        sa.Column("next_action", sa.String(100)),
        sa.Column("summary", sa.Text),
        sa.Column("handoff_reason", sa.Text),
        sa.Column("handoff_at", sa.DateTime(timezone=True)),
        sa.Column("notified_owner", sa.Integer,
                  nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_leads_visitor_id", "leads", ["visitor_id"])
    op.create_index("ix_leads_stage", "leads", ["stage"])
    op.create_index("ix_leads_score", "leads", ["score"])

    # ─────────────────────────────────────
    # messages
    # ─────────────────────────────────────

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "lead_id", sa.Integer,
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text),
        sa.Column("tool_name", sa.String(64)),
        sa.Column("tool_payload", sa.Text),
        sa.Column("tool_result", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_messages_lead_id", "messages", ["lead_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("leads")
    op.drop_table("visitors")

    sa.Enum(name="lead_stage").drop(op.get_bind(), checkfirst=True)
