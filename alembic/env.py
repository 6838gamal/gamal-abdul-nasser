"""
Alembic environment — يقرأ DATABASE_URL من متغيرات البيئة.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ─────────────────────────────────────────────────────
# أضف مسار المشروع (يعتمد على موقع env.py وليس cwd)
# ─────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─────────────────────────────────────────────────────
# استورد Base وكل الموديلات
# ─────────────────────────────────────────────────────

# جرّب المصادر المحتملة لـ Base
try:
    from app.database.base import Base  # noqa: E402
except ImportError:
    from app.database.session import Base  # noqa: E402

# ⚠️ مهم: استورد كل الموديلات لتُسجَّل في Base.metadata
import app.models  # noqa: E402, F401

# ─────────────────────────────────────────────────────
# Alembic Config
# ─────────────────────────────────────────────────────

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ═════════════════════════════════════════════════════
# قراءة DATABASE_URL من البيئة
# ═════════════════════════════════════════════════════

def _get_db_url() -> str:
    """
    اقرأ DATABASE_URL من متغيرات البيئة.

    الأولويات:
    1. DATABASE_URL (المعيار)
    2. RENDER_DATABASE_URL (Render)
    3. SYNC_DATABASE_URL (driver متزامن)
    4. sqlalchemy.url في alembic.ini (fallback)

    يحوّل asyncpg → psycopg2 لأن Alembic يحتاج sync driver.
    """

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("RENDER_DATABASE_URL")
        or os.environ.get("SYNC_DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )

    if not url:
        raise RuntimeError(
            "❌ DATABASE_URL is not set.\n"
            "Set it in your environment:\n"
            "  export DATABASE_URL='postgresql://user:pass@host:5432/db'\n"
            "Or in Docker/Render env vars."
        )

    # ─── إصلاح البروتوكول ───
    # Alembic يعمل مع sync driver
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")

    # Render يعطي: postgres://...
    if url.startswith("postgres://"):
        url = url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )

    # إذا لم يكن هناك +driver، أضف psycopg2
    if url.startswith("postgresql://"):
        url = url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    # ─── إزالة sslmode (psycopg2 لا يدعمها بهذه الصيغة) ───
    # يمكن استخدام connect_args بدلاً منها
    if "?sslmode=" in url:
        url = url.split("?sslmode=")[0]
    elif "&sslmode=" in url:
        url = url.split("&sslmode=")[0]

    return url


# ═════════════════════════════════════════════════════
# Offline mode
# ═════════════════════════════════════════════════════

def run_migrations_offline() -> None:
    """
    توليد SQL بدون اتصال.
    """

    context.configure(
        url=_get_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ═════════════════════════════════════════════════════
# Online mode
# ═════════════════════════════════════════════════════

def run_migrations_online() -> None:
    """
    تشغيل migrations مع اتصال فعلي.
    """

    cfg = config.get_section(config.config_ini_section, {})

    # حقن DATABASE_URL في الإعدادات
    cfg["sqlalchemy.url"] = _get_db_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ═════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
