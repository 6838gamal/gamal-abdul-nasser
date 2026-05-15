from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    short_description: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    features: Mapped[list] = mapped_column(JSON, default=list)
    pricing: Mapped[list] = mapped_column(JSON, default=list)  # [{name, price, features}]
    cta_text: Mapped[str] = mapped_column(String(120), default="اطلب الآن")
    cta_url: Mapped[str] = mapped_column(String(500), default="/contact")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
