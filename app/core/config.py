"""إعدادات التطبيق - تُحمّل من متغيرات البيئة."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "منصة جمال عبد الناصر"
    APP_URL: str = "http://localhost:8000"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
