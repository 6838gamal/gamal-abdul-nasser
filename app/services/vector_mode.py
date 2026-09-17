# app/services/vector_mode.py
import logging
from functools import lru_cache
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class VectorMode:
    PGVECTOR = "pgvector"
    JSONB = "jsonb"
    UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def get_cached_mode() -> str:
    """يُقرأ مرة واحدة عند بدء التطبيق."""
    return VectorMode.UNKNOWN


async def detect_vector_mode(db: AsyncSession) -> str:
    """
    يكتشف الوضع الحقيقي من قاعدة البيانات.
    يُستدعى مرة واحدة عند الإقلاع، ويُخزّن النتيجة.
    """
    cached = get_cached_mode()
    if cached != VectorMode.UNKNOWN:
        return cached

    try:
        # 1. جرّب قراءة الإعداد المسجّل
        row = await db.execute(text(
            "SELECT value FROM _system_config WHERE key='vector_mode'"
        ))
        result = row.first()
        if result:
            mode = result[0]
            logger.info(f"Vector mode detected: {mode}")
            _set_mode(mode)
            return mode
    except Exception as e:
        logger.debug(f"_system_config not found: {e}")

    # 2. فحص نوع العمود فعلياً
    try:
        row = await db.execute(text("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name='knowledge_chunks' AND column_name='embedding'
        """))
        result = row.first()
        if result:
            dtype = result[0].lower()
            if "vector" in dtype or "user-defined" in dtype:
                mode = VectorMode.PGVECTOR
            elif "jsonb" in dtype or "json" in dtype:
                mode = VectorMode.JSONB
            else:
                mode = VectorMode.UNKNOWN
            _set_mode(mode)
            logger.info(f"Vector mode detected from schema: {mode}")
            return mode
    except Exception as e:
        logger.error(f"Vector mode detection failed: {e}")

    return VectorMode.UNKNOWN


def _set_mode(mode: str):
    get_cached_mode.cache_clear()
    get_cached_mode.__wrapped__ = lambda: mode  # hack بسيط
    # بديل أنظف:
    _MODE_HOLDER["mode"] = mode


# بديل أنظف من lru_cache
_MODE_HOLDER = {"mode": VectorMode.UNKNOWN}


def set_mode(mode: str):
    _MODE_HOLDER["mode"] = mode


def current_mode() -> str:
    return _MODE_HOLDER["mode"]


def is_pgvector() -> bool:
    return current_mode() == VectorMode.PGVECTOR
