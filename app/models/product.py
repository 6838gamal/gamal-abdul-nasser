from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON, Numeric, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    short_description: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gallery: Mapped[list] = mapped_column(JSON, default=list)
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    meta_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    buyer_email: Mapped[str] = mapped_column(String(255), index=True)
    buyer_name: Mapped[str] = mapped_column(String(150))
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending, paid, refunded
    download_token: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    download_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(lazy="selectin")
