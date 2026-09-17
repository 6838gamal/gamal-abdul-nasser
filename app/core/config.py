# app/core/config.py

"""
إعدادات التطبيق — تُحمّل من متغيرات البيئة فقط.

المبادئ:
- لا قيم حساسة مضمّنة في الكود.
- كل قيمة يمكن تجاوزها عبر env var.
- القيم الافتراضية آمنة للتطوير المحلي فقط.
- فشل سريع (fail-fast) عند نقص متغيرات حرجة في الإنتاج.
"""

import logging
import os
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


log = logging.getLogger("app.config")


# ══════════════════════════════════════════════════════════════════════
# URL helpers
# ══════════════════════════════════════════════════════════════════════


def _is_local_host(host: str, environment: str = "development") -> bool:
    """
    هل المضيف محلي (لا يحتاج SSL)؟

    ملاحظة: أسماء مثل 'db' و 'postgres' تُعتبر محلية فقط في
    بيئة التطوير. في الإنتاج، قد تكون أسماء خدمات حقيقية تحتاج SSL.
    """
    h = (host or "").lower()
    if h in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return True
    if environment != "production" and h in ("db", "postgres"):
        return True
    return False


def _needs_ssl(raw_url: str, environment: str = "development") -> bool:
    """هل يحتاج الاتصال SSL؟ (نعم لأي خادم خارجي)"""
    if not raw_url:
        return False
    try:
        parsed = urlparse(raw_url)
        host = (parsed.hostname or "").lower()
        params = parse_qs(parsed.query)
        sslmode = params.get("sslmode", [""])[0].lower()

        if sslmode == "disable":
            return False
        if _is_local_host(host, environment):
            return False
        return True
    except Exception as exc:
        log.warning("_needs_ssl: فشل تحليل URL (%s) — سيُعطَّل SSL", exc)
        return False


def _to_asyncpg_url(url: str) -> str:
    """تحويل رابط postgresql:// إلى asyncpg."""
    if not url:
        return url

    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            # asyncpg لا يقبل هذه المعاملات في URL
            for k in ("sslmode", "sslcert", "sslkey", "sslrootcert"):
                params.pop(k, None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            new_parsed = parsed._replace(
                scheme="postgresql+asyncpg",
                query=new_query,
            )
            return urlunparse(new_parsed)

    return url


def _to_psycopg2_url(url: str) -> str:
    """تحويل رابط postgresql:// إلى psycopg2."""
    if not url:
        return url

    for prefix in (
        "postgresql://",
        "postgres://",
        "postgresql+asyncpg://",
    ):
        if url.startswith(prefix):
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            for k in ("sslrootcert", "sslcert", "sslkey"):
                params.pop(k, None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            new_parsed = parsed._replace(
                scheme="postgresql+psycopg2",
                query=new_query,
            )
            return urlunparse(new_parsed)

    return url


# ══════════════════════════════════════════════════════════════════════
# Settings
# ══════════════════════════════════════════════════════════════════════


class Settings(BaseSettings):
    """
    كل الإعدادات تُقرأ من متغيرات البيئة.
    لا قيم حساسة مضمّنة في الكود.
    """

    # ─── عام ──────────────────────────────────────────────────────
    APP_NAME: str = "منصة جمال المقطري"
    APP_URL: str = "http://localhost:5000"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-change-me"

    # ─── قاعدة البيانات ───────────────────────────────────────────
    # يُقرأ من env: DATABASE_URL
    # مثال: postgresql://user:pass@host:5432/dbname
    DATABASE_URL: str = ""
    SYNC_DATABASE_URL: str = ""
    DB_USE_SSL: bool = False

    # Connection pool
    DB_POOL_SIZE: int = 3
    DB_POOL_MAX_OVERFLOW: int = 7
    DB_POOL_RECYCLE: int = 300
    DB_POOL_TIMEOUT: int = 30

    # ─── Redis ────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Admin ────────────────────────────────────────────────────
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # ─── JWT ──────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ─── Gemini ───────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ─── Supabase Storage ─────────────────────────────────────────
    # للرفع فقط، منفصل عن DATABASE_URL
    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_BUCKET: str = "uploads"

    # ─── SEO / Metadata ───────────────────────────────────────────
    SITE_AUTHOR: str = ""
    SITE_DESCRIPTION: str = ""
    SITE_LOCALE: str = "ar_SA"
    DEFAULT_OG_IMAGE: str = "/static/images/og-default.jpg"
    GOOGLE_INDEXING_KEY_FILE: str = ""
    GOOGLE_SEARCH_CONSOLE_SITE: str = ""

    # ─── Uploads ──────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 50

    # ══════════════════════════════════════════════════════════════
    # Config
    # ══════════════════════════════════════════════════════════════

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Validators ───────────────────────────────────────────────

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_async_driver(cls, v: str) -> str:
        return _to_asyncpg_url(v or "")

    @field_validator("SYNC_DATABASE_URL", mode="before")
    @classmethod
    def ensure_sync_driver(cls, v: str) -> str:
        return _to_psycopg2_url(v or "")

    @model_validator(mode="after")
    def _post_process(self):
        """
        - كشف SSL تلقائياً من DATABASE_URL.
        - اشتقاق SYNC_DATABASE_URL من DATABASE_URL إن لم يُحدَّد.
        - فشل سريع في الإنتاج عند نقص متغيرات حرجة.
        """
        # 0. تحقق من ENVIRONMENT
        env = (self.ENVIRONMENT or "development").lower()

        # 1. كشف SSL تلقائياً (إن لم يُضبط صراحة)
        if "DB_USE_SSL" not in os.environ and self.DATABASE_URL:
            # نحوّل +asyncpg → postgresql:// لتحليل host
            plain = self.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
            self.DB_USE_SSL = _needs_ssl(plain, env)

        # 2. اشتقاق SYNC_DATABASE_URL إن لم يُحدَّد صراحةً في env
        if "SYNC_DATABASE_URL" not in os.environ and self.DATABASE_URL:
            plain = self.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
            self.SYNC_DATABASE_URL = _to_psycopg2_url(plain)

        # 3. فشل سريع في الإنتاج
        if env == "production":
            required = {
                "DATABASE_URL": self.DATABASE_URL,
                "SECRET_KEY": self.SECRET_KEY,
                "GEMINI_API_KEY": self.GEMINI_API_KEY,
                "ADMIN_EMAIL": self.ADMIN_EMAIL,
                "ADMIN_PASSWORD": self.ADMIN_PASSWORD,
            }
            missing = [
                name for name, value in required.items()
                if not value or str(value).startswith("dev-")
            ]
            if missing:
                raise RuntimeError(
                    f"متغيرات بيئة مفقودة في production: "
                    f"{', '.join(missing)}"
                )

            # تحقق إضافي: SECRET_KEY معقول الطول
            if len(self.SECRET_KEY) < 32:
                raise RuntimeError(
                    "SECRET_KEY ضعيف في production (أقل من 32 حرفاً)."
                )

        return self


# ══════════════════════════════════════════════════════════════════════
# Builder
# ══════════════════════════════════════════════════════════════════════


def _build_settings() -> Settings:
    """
    دعم متغيرات خاصة بمنصات النشر:

    - Render: يوفّر DATABASE_URL (Internal) و DATABASE_EXTERNAL_URL.
    - Railway: يوفّر DATABASE_URL.
    - Supabase: يوفّر DATABASE_URL.
    - Fly.io: يوفّر DATABASE_URL.
    """
    raw_db = (
        os.environ.get("RENDER_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_EXTERNAL_URL", "")
    )

    overrides: dict = {}

    if raw_db:
        overrides["DATABASE_URL"] = raw_db
        # SYNC يُشتق تلقائياً في model_validator إن لم يُحدَّد

    return Settings(**overrides)


@lru_cache
def get_settings() -> Settings:
    return _build_settings()


settings = get_settings()


# ══════════════════════════════════════════════════════════════════════
# طباعة تشخيصية عند التحميل
# ══════════════════════════════════════════════════════════════════════

import sys as _sys


def _dbg(msg: str) -> None:
    print(f"[config] {msg}", file=_sys.stderr, flush=True)


def _describe_db_url(url: str) -> str:
    if not url:
        return "(empty)"
    try:
        p = urlparse(url)
        host = p.hostname or "?"
        port = p.port or "?"
        db = (p.path or "/?").lstrip("/") or "?"
        return f"scheme={p.scheme} host={host}:{port} db={db}"
    except Exception:
        return "(unparseable)"


_dbg(f"ENVIRONMENT={settings.ENVIRONMENT} DEBUG={settings.DEBUG}")
_dbg(f"DATABASE_URL: {_describe_db_url(settings.DATABASE_URL)}")
_dbg(f"SYNC_DATABASE_URL: {_describe_db_url(settings.SYNC_DATABASE_URL)}")
_dbg(f"DB_USE_SSL={settings.DB_USE_SSL}")
