from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


class HeartbeatLog(Base):
    """سجل نبضات التحقق الدورية من يقظة السيرفر وقاعدة البيانات."""
    __tablename__ = "heartbeat_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
