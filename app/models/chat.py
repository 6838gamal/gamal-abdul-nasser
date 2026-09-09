"""نموذج سجل المحادثات لتخزين تفاعلات المستخدمين مع وكيل الذكاء الاصطناعي."""
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, Index
from sqlalchemy.sql import func
from app.database.base import Base
import enum


class ChatStatus(str, enum.Enum):
    """حالة المحادثة."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


class ChatLog(Base):
    """سجل محادثات المستخدمين مع وكيل الذكاء الاصطناعي."""
    __tablename__ = "chat_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    visitor_id = Column(String(255), nullable=True, index=True, comment="معرف الزائر (IP + User-Agent)")
    message = Column(Text, nullable=False, comment="رسالة المستخدم")
    reply = Column(Text, nullable=True, comment="رد الوكيل")
    status = Column(Enum(ChatStatus), default=ChatStatus.PENDING, comment="حالة الطلب")
    error_message = Column(Text, nullable=True, comment="رسالة الخطأ إن وجدت")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="وقت الإنشاء")
    
    # فهارس للبحث السريع
    __table_args__ = (
        Index("ix_chat_logs_visitor_id_created_at", "visitor_id", "created_at"),
    )
    
    def __repr__(self):
        return f"<ChatLog {self.id}: {self.message[:30]}...>"
