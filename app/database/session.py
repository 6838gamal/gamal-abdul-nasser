"""جلسة قاعدة البيانات async + sync (للأدوات والـ migrations)."""
import ssl
import logging
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

log = logging.getLogger("app.db")


class Base(DeclarativeBase):
    pass


def _build_connect_args() -> dict:
    """بناء معاملات الاتصال بما فيها SSL إذا لزم."""
    if not settings.DB_USE_SSL:
        return {}
    
    # SSL مع التحقق الكامل (آمن — Supabase/Render/Neon يستخدمون شهادات CA موثوقة)
    ctx = ssl.create_default_context()
    
    # للمطورين: فك التعليق فقط لو واجهت SSLCertVerificationError
    # (وهو نادر جداً مع المزودين السحابيين)
    # ctx.check_hostname = False
    # ctx.verify_mode = ssl.CERT_NONE
    
    log.info("قاعدة البيانات: تم تفعيل SSL مع التحقق الكامل")
    return {"ssl": ctx}


engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args=_build_connect_args(),
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
