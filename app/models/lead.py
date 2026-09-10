# app/models/lead.py

"""
نموذج العميل المحتمل — Lead Model

يمثل lead واحد لكل زائر (حالياً).
يمكن لاحقاً السماح بعدة leads لكل زائر (مشاريع متعددة).
"""

import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class LeadStage(str, enum.Enum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    CONTACT_REQUESTED = "contact_requested"
    READY_TO_BUY = "ready_to_buy"
    HANDED_OFF = "handed_off"
    LOST = "lost"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)

    visitor_id = Column(
        Integer,
        ForeignKey("visitors.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # ─────────────────────────────────────
    # الحالة
    # ─────────────────────────────────────

    stage = Column(
        Enum(LeadStage, name="lead_stage"),
        default=LeadStage.NEW,
        nullable=False,
        index=True,
    )

    score = Column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="0-100",
    )

    # ─────────────────────────────────────
    # البيانات الأساسية
    # ─────────────────────────────────────

    name = Column(String(120), nullable=True)
    company = Column(String(120), nullable=True)
    contact = Column(String(255), nullable=True)

    project_type = Column(String(120), nullable=True)
    problem = Column(Text, nullable=True)
    desired_solution = Column(Text, nullable=True)
    budget = Column(String(120), nullable=True)
    timeline = Column(String(120), nullable=True)

    # ─────────────────────────────────────
    # Metadata
    # ─────────────────────────────────────

    intent = Column(String(100), nullable=True)
    next_action = Column(String(100), nullable=True)
    summary = Column(Text, nullable=True)

    # ─────────────────────────────────────
    # Handoff
    # ─────────────────────────────────────

    handoff_reason = Column(Text, nullable=True)
    handoff_at = Column(DateTime(timezone=True), nullable=True)
    notified_owner = Column(Integer, default=0, nullable=False)

    # ─────────────────────────────────────
    # Timestamps
    # ─────────────────────────────────────

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ─────────────────────────────────────
    # Relationships
    # ─────────────────────────────────────

    visitor = relationship("Visitor", back_populates="leads")

    messages = relationship(
        "Message",
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id} stage={self.stage} score={self.score}>"
