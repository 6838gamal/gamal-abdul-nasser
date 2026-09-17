# app/models/knowledge_chunk.py
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, JSON, func, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

EMBEDDING_DIM = 1024


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    # ملاحظة: لا نعرّف embedding في الـ Model هنا!
    # لأن نوعه يختلف بين vector و jsonb.
    # سنتعامل معه عبر raw SQL في الطبقة المناسبة.
    # هذا يمنع SQLAlchemy من رفع خطأ عند اختلاف النوع.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "chunk_index", name="uq_chunk_source"),
        Index("ix_chunks_source", "source_type", "source_id"),
    )
