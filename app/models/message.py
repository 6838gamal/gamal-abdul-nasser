# app/models/message.py

"""
نموذج الرسالة — Message Model

كل رسالة (user / model / tool) داخل محادثة lead.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    lead_id = Column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    role = Column(
        String(16),
        nullable=False,
        comment="user / model / tool",
    )

    content = Column(Text, nullable=True)

    tool_name = Column(String(64), nullable=True)
    tool_payload = Column(Text, nullable=True)
    tool_result = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    lead = relationship("Lead", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role}>"
