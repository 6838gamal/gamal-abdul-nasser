"""
Alembic environment — يقرأ DATABASE_URL من متغيرات البيئة.
"""

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from alembic import context
from sqlalchemy import engine_from_config, pool

# ─────────────────────────────────────────────────────
# Logging بسيط — يظهر فوراً على stderr
# ─────────────────────────────────────────────────────

log = logging.getLogger("alembic.env")
if not log.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    log.addHandler(handler)
    log.setLevel(logging.INFO)


# ─────────────────────────────────────────────────────
# أضف مسار المشروع (يعتمد على موقع env.py وليس cwd)
# ─────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────
# استورد Base وكل الموديلات
# ─────────────────────────────────────────────────────

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

if config.config_file_name and Path(config.config_file_name).exists():
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ═════════════════════════════════════════════════════
# أدوات مساعدة
# ═════════════════════════════════════════════════════

def _mask_url(url: str) -> str:
    """إخفاء كلمة المرور من URL قبل تسجيله."""
    if not url:
        return "(empty)"
    try:
        p = urlparse(url)
        host = p.hostname or "?"
        port = p.port or "?"
        db = (p.path or "/?").lstrip("/") or "?"
        user = p.username or "?"
        scheme = p.scheme or "?"
        return f"scheme={scheme} user={user} host={host}:{port} db={db}"
    except Exception:
        return "(unparseable)"


def _extract_ssl_params(url: str) -> dict:
    """
    استخرج معاملات SSL من URL ليتم تمريرها عبر connect_args.
    يدعم: sslmode, sslrootcert, sslcert, sslkey.
    """
    params: dict = {}
    if not url:
        return params
    try:
        parsed = urlparse(url)
        q = parse_qs(parsed.query, keep_blank_values=True)
        for k in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
            if k in q:
                params[k] = q[k][0]
    except Exception as exc:
        log.warning("فشل استخراج معاملات SSL: %s", exc)
    return params


def _strip_ssl_params(url: str) -> str:
    """
    أزل معاملات SSL من URL (psycopg2 لا يقبلها في URL،
    تمرَّر عبر connect_args بدلاً منها).
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
        q = parse_qs(parsed.query, keep_blank_values=True)
        for k in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
            q.pop(k, None)
        new_query = urlencode({k: v[0] for k, v in q.items()})
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url


# ═════════════════════════════════════════════════════
# قراءة DATABASE_URL من البيئة
# ═════════════════════════════════════════════════════

# تخزين مؤقت لتفادي إعادة الحساب
_db_url_cache: dict = {"url": None, "connect_args": None}


def _get_db_url() -> str:
    """
    اقرأ DATABASE_URL من متغيرات البيئة.

    الأولويات:
    1. DATABASE_URL (المعيار)
    2. SYNC_DATABASE_URL (driver متزامن جاهز)
    3. DATABASE_EXTERNAL_URL (Render external)
    4. sqlalchemy.url في alembic.ini (fallback)

    يحوّل asyncpg → psycopg2 لأن Alembic يحتاج sync driver.
    """

    if _db_url_cache["url"] is not None:
        return _db_url_cache["url"]

    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SYNC_DATABASE_URL")
        or os.environ.get("DATABASE_EXTERNAL_URL")
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
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("postgresql+psycopg://", "postgresql+psycopg2://")

    # Render يعطي: postgres://...
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)

    # إذا لم يكن هناك +driver، أضف psycopg2
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    # ─── استخرج SSL ثم أزلها من URL ───
    _db_url_cache["connect_args"] = _extract_ssl_params(url)
    url = _strip_ssl_params(url)

    _db_url_cache["url"] = url

    log.info("Alembic DATABASE_URL: %s", _mask_url(url))
    if _db_url_cache["connect_args"]:
        log.info(
            "Alembic connect_args: %s",
            {k: v for k, v in _db_url_cache["connect_args"].items()},
        )

    return url


def _get_connect_args() -> dict:
    """أعد connect_args المستخرجة أثناء _get_db_url."""
    if _db_url_cache["connect_args"] is None:
        _get_db_url()  # يملأ الـ cache
    return _db_url_cache["connect_args"] or {}


# ═════════════════════════════════════════════════════
# Offline mode
# ═════════════════════════════════════════════════════

def run_migrations_offline() -> None:
    """
    توليد SQL بدون اتصال.
    """
    url = _get_db_url()
    log.info("Running migrations (offline)")

    context.configure(
        url=url,
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
    url = _get_db_url()
    connect_args = _get_connect_args()

    log.info("Running migrations (online)")

    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
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
