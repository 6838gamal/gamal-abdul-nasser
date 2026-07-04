"""إعدادات التطبيق - تُحمّل من متغيرات البيئة."""
import os
from functools import lru_cache
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _to_asyncpg_url(url: str) -> str:
    """Convert a standard postgresql:// URL to asyncpg format, stripping incompatible params."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)
            # asyncpg does not accept sslmode as a query param
            params.pop("sslmode", None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            new_parsed = parsed._replace(scheme="postgresql+asyncpg", query=new_query)
            return urlunparse(new_parsed)
    return url


def _to_psycopg2_url(url: str) -> str:
    """Convert a standard postgresql:// URL to psycopg2 format."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            parsed = urlparse(url)
            new_parsed = parsed._replace(scheme="postgresql+psycopg2")
            return urlunparse(new_parsed)
    return url


class Settings(BaseSettings):
    APP_NAME: str = "منصة جمال عبد الناصر"
    APP_URL: str = "http://localhost:5000"
    SECRET_KEY: str = "dev-secret-change-me"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gan_platform"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/gan_platform"
    REDIS_URL: str = "redis://localhost:6379/0"

    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "ChangeMe!2026"

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    SITE_AUTHOR: str = "جمال عبد الناصر"
    SITE_DESCRIPTION: str = "منصة شخصية احترافية"
    SITE_LOCALE: str = "ar_SA"
    DEFAULT_OG_IMAGE: str = "/static/images/og-default.jpg"

    GOOGLE_INDEXING_KEY_FILE: str = ""
    GOOGLE_SEARCH_CONSOLE_SITE: str = ""

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 50

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
    raw_db = os.environ.get("DATABASE_URL", "")
    kwargs: dict = {}
    if raw_db:
        kwargs["DATABASE_URL"] = raw_db
        kwargs["SYNC_DATABASE_URL"] = raw_db
    return Settings(**kwargs)


@lru_cache
def get_settings() -> Settings:
    return _build_settings()


settings = get_settings()
