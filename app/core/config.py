"""إعدادات التطبيق - تُحمّل من متغيرات البيئة."""
import os
from functools import lru_cache
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _needs_ssl(raw_url: str) -> bool:
    """هل يحتاج الاتصال بقاعدة البيانات إلى SSL؟
    نعم دائماً إذا لم يكن localhost/127.0.0.1/db (Docker Compose)."""
    if not raw_url:
        return False
    try:
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        params = parse_qs(parsed.query)
        sslmode = params.get("sslmode", [""])[0].lower()
        if sslmode == "disable":
            return False
        if host in ("localhost", "127.0.0.1", "db", "postgres"):
            return False
        # أي خادم خارجي → SSL مطلوب
        return True
    except Exception:
        return False


def _to_asyncpg_url(url: str) -> str:
    """تحويل رابط postgresql:// إلى asyncpg مع حذف المعاملات غير المتوافقة."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            # asyncpg لا يقبل sslmode كمعامل URL — يُعالَج عبر connect_args
            params.pop("sslmode", None)
            params.pop("sslcert", None)
            params.pop("sslkey", None)
            params.pop("sslrootcert", None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            new_parsed = parsed._replace(scheme="postgresql+asyncpg", query=new_query)
            return urlunparse(new_parsed)
    return url


def _to_psycopg2_url(url: str) -> str:
    """تحويل رابط postgresql:// إلى psycopg2 مع حذف المعاملات غير المتوافقة."""
    for prefix in ("postgresql://", "postgres://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            params.pop("sslrootcert", None)
            params.pop("sslcert", None)
            params.pop("sslkey", None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            new_parsed = parsed._replace(scheme="postgresql+psycopg2", query=new_query)
            return urlunparse(new_parsed)
    return url


class Settings(BaseSettings):
    APP_NAME: str = "منصة جمال المقطري"
    APP_URL: str = "http://localhost:5000"
    SECRET_KEY: str = "dev-secret-change-me"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ─── قاعدة البيانات PostgreSQL ────────────────────────────────
    # رابط الاتصال بقاعدة البيانات — يبدأ بـ postgresql://
    # مثال Supabase:  postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres
    # مثال Render:    postgresql://user:pass@host:5432/dbname
    # ⚠️  هذا الرابط مختلف تماماً عن SUPABASE_URL أدناه
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gan_platform"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/gan_platform"
    DB_USE_SSL: bool = False  # يُكتشف تلقائياً من الرابط

    REDIS_URL: str = "redis://localhost:6379/0"

    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "ChangeMe!2026"

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    SITE_AUTHOR: str = "جمال المقطري"
    SITE_DESCRIPTION: str = "منصة شخصية احترافية"
    SITE_LOCALE: str = "ar_SA"
    DEFAULT_OG_IMAGE: str = "/static/images/og-default.jpg"

    GOOGLE_INDEXING_KEY_FILE: str = ""
    GOOGLE_SEARCH_CONSOLE_SITE: str = ""

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 50

    # ─── Supabase Storage API ─────────────────────────────────────
    # هذه الإعدادات لـ Supabase Storage (رفع الملفات والصور) فقط
    # SUPABASE_URL = رابط HTTP لمشروع Supabase يبدأ بـ https://
    # مثال: https://bmaqlynnbhbnrsbuboim.supabase.co
    # ⚠️  هذا الرابط مختلف تماماً عن DATABASE_URL أعلاه
    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: str = ""   # مفتاح service role من Supabase → Settings → API
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_BUCKET: str = "uploads"

    # ─── إعدادات Connection Pool ──────────────────────────────────
    DB_POOL_SIZE: int = 3
    DB_POOL_MAX_OVERFLOW: int = 7
    DB_POOL_RECYCLE: int = 300  # ثانية (5 دقائق)
    DB_POOL_TIMEOUT: int = 30   # ثانية

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_async_driver(cls, v: str) -> str:
        return _to_asyncpg_url(v)

    @field_validator("SYNC_DATABASE_URL", mode="before")
    @classmethod
    def ensure_sync_driver(cls, v: str) -> str:
        return _to_psycopg2_url(v)


def _build_settings() -> "Settings":
    raw_db = os.environ.get("RENDER_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    kwargs: dict = {}
    if raw_db:
        kwargs["DATABASE_URL"] = raw_db
        kwargs["SYNC_DATABASE_URL"] = raw_db
        # كشف SSL تلقائياً من الرابط الأصلي
        if "DB_USE_SSL" not in os.environ:
            kwargs["DB_USE_SSL"] = _needs_ssl(raw_db)
    return Settings(**kwargs)


@lru_cache
def get_settings() -> Settings:
    return _build_settings()


settings = get_settings()
