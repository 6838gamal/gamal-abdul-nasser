"""المقالات والتصنيفات والوسوم."""
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Integer, Table, Column, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


article_tags = Table(
    "article_tags",
    Base.metadata,
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    excerpt: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    reading_time: Mapped[int] = mapped_column(Integer, default=1)

    # SEO per-article
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    meta_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    og_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    schema_type: Mapped[str] = mapped_column(String(50), default="Article")
    faq_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    category: Mapped["Category | None"] = relationship(lazy="selectin")
    tags: Mapped[list["Tag"]] = relationship(secondary=article_tags, lazy="selectin")
    author: Mapped["User | None"] = relationship(lazy="selectin")  # noqa: F821

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
