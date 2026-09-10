# app/models/visitor.py

"""
نموذج الزائر — Visitor Model

يمثل زائراً دائماً عبر الجلسات.
يُعرَّف بواسطة UUID يُخزَّن في localStorage عند العميل.
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Visitor(Base):
    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, index=True)

    visitor_uid = Column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="UUID دائم من العميل",
    )

    first_seen = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_seen = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user_agent = Column(String(255), nullable=True)
    ip_hash = Column(String(64), nullable=True, comment="SHA256 للـ IP")
    locale = Column(String(16), nullable=True)
    referrer = Column(String(500), nullable=True)

    leads = relationship(
        "Lead",
        back_populates="visitor",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Visitor uid={self.visitor_uid}>"
