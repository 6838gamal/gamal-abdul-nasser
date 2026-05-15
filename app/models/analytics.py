from datetime import datetime
from sqlalchemy import String, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class PageView(Base):
    __tablename__ = "page_views"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(500), index=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(4), nullable=True)
    device: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
