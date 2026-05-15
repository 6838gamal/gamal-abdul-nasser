from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class Redirect(Base):
    __tablename__ = "redirects"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    target: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int] = mapped_column(Integer, default=301)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SeoSetting(Base):
    __tablename__ = "seo_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
