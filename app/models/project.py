from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    short_description: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gallery: Mapped[list] = mapped_column(JSON, default=list)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    live_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
