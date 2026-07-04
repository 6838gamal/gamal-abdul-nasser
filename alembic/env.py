from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys
sys.path.insert(0, os.path.abspath("."))
from app.database.session import Base
from app import models  # noqa

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

# قراءة رابط قاعدة البيانات من متغيرات البيئة إذا لم يكن محدداً في alembic.ini
def _get_db_url() -> str:
    url = (
        os.environ.get("RENDER_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SYNC_DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )
    # تحويل asyncpg إلى psycopg2 للـ migrations (alembic يحتاج sync driver)
    if url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        url = url.replace("postgres://", "postgresql+psycopg2://")
        # إزالة sslmode غير المدعوم من psycopg2 بهذه الطريقة
        if "?sslmode=" in url:
            url = url.split("?sslmode=")[0]
        elif "&sslmode=" in url:
            url = url.split("&sslmode=")[0]
    return url


def run_migrations_offline():
    context.configure(url=_get_db_url(),
                      target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_db_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
