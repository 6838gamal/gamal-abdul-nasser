"""نقطة دخول التطبيق."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select, text

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.database.session import engine, Base, AsyncSessionLocal
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.analytics import AnalyticsMiddleware
from app.middleware.redirects import RedirectMiddleware
from app.i18n import set_locale, get_locale, LOCALE_COOKIE, SUPPORTED_LOCALES
from app.routes import public, seo_routes, auth_routes, downloads, chat as chat_route
from app.admin.router import router as admin_router
from app.utils.templates import templates
from app.models.user import User


# ══════════════════════════════════════════════════════════════════════
# طباعة فورية على stderr — تظهر في كل بيئات النشر (Render/Docker/…)
# ══════════════════════════════════════════════════════════════════════

def _boot(msg: str = "") -> None:
    """طباعة فورية على stderr — لا تتأثر بـ stdout buffering."""
    print(msg, file=sys.stderr, flush=True)


_boot(">>> main.py: module loading ...")


# ══════════════════════════════════════════════════════════════════════
# ⚠️ مهم جداً: استورد كل الموديلات حتى تُسجَّل في Base.metadata
# بدونه لن يُنشئ create_all جداول visitor/lead/message
# ══════════════════════════════════════════════════════════════════════

import app.models  # noqa: F401, E402

# موديلات نحتاجها لتوليد DDL تلقائياً
from app.models.lead import Lead  # noqa: E402
from app.models.visitor import Visitor  # noqa: E402
from app.models.message import Message  # noqa: E402


setup_logging("INFO" if not settings.DEBUG else "DEBUG")
log = logging.getLogger("app")

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

_boot(">>> main.py: imports OK, logger ready")


# ══════════════════════════════════════════════════════════════════════
# أدوات مساعدة للترحيل (idempotent)
# ══════════════════════════════════════════════════════════════════════

async def _column_exists(conn, table: str, column: str) -> bool:
    """هل العمود موجود في الجدول؟"""
    result = await conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
        LIMIT 1
    """), {"t": table, "c": column})
    return result.fetchone() is not None


async def _ensure_column(
    conn,
    table: str,
    column: str,
    ddl_type: str,
    default: str | None = None,
    not_null: bool = False,
) -> bool:
    """
    يضمن وجود عمود في جدول. إن لم يكن موجوداً، يضيفه عبر ALTER TABLE.

    Returns:
        True إن أُضيف العمود الآن، False إن كان موجوداً مسبقاً.
    """
    if await _column_exists(conn, table, column):
        return False

    ddl = f'ALTER TABLE {table} ADD COLUMN "{column}" {ddl_type}'
    if default is not None:
        ddl += f" DEFAULT {default}"
    if not_null:
        ddl += " NOT NULL"

    await conn.execute(text(ddl))
    _boot(f"        ➕ أُضيف العمود {table}.{column} ({ddl_type})")
    log.info("أُضيف العمود %s.%s (%s)", table, column, ddl_type)
    return True


def _sqlalchemy_type_to_pg(col) -> str:
    """
    تحويل نوع عمود SQLAlchemy إلى نوع PostgreSQL نصي لاستخدامه في ALTER TABLE.
    يغطي الأنواع الشائعة المستخدمة في الموديلات.
    """
    import sqlalchemy as sa

    t = col.type

    # Integer
    if isinstance(t, sa.Integer):
        return "INTEGER"
    if isinstance(t, sa.BigInteger):
        return "BIGINT"
    if isinstance(t, sa.SmallInteger):
        return "SMALLINT"

    # String
    if isinstance(t, sa.String):
        length = getattr(t, "length", None)
        return f"VARCHAR({length})" if length else "VARCHAR(255)"

    # Text
    if isinstance(t, sa.Text):
        return "TEXT"

    # Boolean
    if isinstance(t, sa.Boolean):
        return "BOOLEAN"

    # DateTime
    if isinstance(t, sa.DateTime):
        return "TIMESTAMPTZ" if t.timezone else "TIMESTAMP"

    # Date / Time
    if isinstance(t, sa.Date):
        return "DATE"
    if isinstance(t, sa.Time):
        return "TIME"

    # Enum
    if isinstance(t, sa.Enum):
        return t.name  # اسم الـ enum المُنشأ مسبقاً

    # Float / Numeric
    if isinstance(t, sa.Float):
        return "DOUBLE PRECISION"
    if isinstance(t, sa.Numeric):
        return f"NUMERIC({t.precision},{t.scale})"

    # JSON
    if isinstance(t, sa.JSON):
        return "JSONB"

    # Fallback
    return "TEXT"


async def _ensure_columns_from_model(conn, model) -> list[str]:
    """
    يضمن وجود كل أعمدة الموديل في جدول قاعدة البيانات.
    يتجاهل المفاتيح الأجنبية (تُنشأ مع الجدول) والأعمدة الموجودة مسبقاً.

    Returns:
        قائمة بأسماء الأعمدة التي أُضيفت الآن.
    """
    table = model.__tablename__
    added: list[str] = []

    for col in model.__table__.columns:
        name = col.name
        ddl_type = _sqlalchemy_type_to_pg(col)

        # استخراج DEFAULT من server_default إن وُجد
        default = None
        if col.server_default is not None:
            default = str(col.server_default.arg)

        added_now = await _ensure_column(
            conn,
            table,
            name,
            ddl_type,
            default=default,
            not_null=bool(col.nullable is False and default is not None),
        )
        if added_now:
            added.append(name)

    return added


# ══════════════════════════════════════════════════════════════════════
# إنشاء الجداول الناقصة + ترحيل الأعمدة (آمن — idempotent)
# ══════════════════════════════════════════════════════════════════════

async def _ensure_chat_tables(conn) -> None:
    """
    تأكد من وجود جداول AI Sales Agent.

    - ينشئ الجداول إن لم تكن موجودة.
    - يضيف الأعمدة الناقصة إن كان الجدول موجوداً ببنية أقدم.
    - يعالج حالة وجود جدول messages قديم ببنية مختلفة.
    """

    _boot("")
    _boot("═" * 60)
    _boot("🔄 [MIGRATION] بدء التأكد من جداول AI Sales Agent...")
    _boot("═" * 60)

    # ─────────────────────────────────────────────────────────────
    # 1) enum lead_stage
    # ─────────────────────────────────────────────────────────────
    #
    # ⚠️ ملاحظة حاسمة:
    # الموديل LeadStage يحوي أعضاء مثل NEW بقيمة "new".
    # SQLAlchemy Enum(LeadStage) يخزّن *أسماء* الأعضاء ('NEW') في PG
    # افتراضياً، لذا يجب أن تكون قيم الـ enum في PG بأحرف كبيرة
    # لتطابق ما يتوقعه SQLAlchemy.
    # ─────────────────────────────────────────────────────────────

    _boot("  [1/5] التحقق من enum lead_stage...")
    await conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lead_stage') THEN
                CREATE TYPE lead_stage AS ENUM (
                    'NEW','QUALIFYING','QUALIFIED','CONTACT_REQUESTED',
                    'READY_TO_BUY','HANDED_OFF','LOST'
                );
            END IF;
        END $$;
    """))
    _boot("        ✓ enum lead_stage جاهز")

    # ─────────────────────────────────────────────────────────────
    # 2) visitors
    # ─────────────────────────────────────────────────────────────

    _boot("  [2/5] إنشاء/التحقق من جدول visitors...")
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS visitors (
            id SERIAL PRIMARY KEY,
            visitor_uid VARCHAR(64) NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_agent VARCHAR(255),
            ip_hash VARCHAR(64),
            locale VARCHAR(16),
            referrer VARCHAR(500)
        );
    """))

    added = await _ensure_columns_from_model(conn, Visitor)
    if added:
        _boot(f"        ➕ أعمدة visitors المضافة: {', '.join(added)}")

    await conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_visitors_visitor_uid
            ON visitors (visitor_uid);
    """))
    _boot("        ✓ جدول visitors جاهز")

    # ─────────────────────────────────────────────────────────────
    # 3) leads
    # ─────────────────────────────────────────────────────────────

    _boot("  [3/5] إنشاء/التحقق من جدول leads...")
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            visitor_id INTEGER NOT NULL REFERENCES visitors(id) ON DELETE CASCADE,
            stage lead_stage NOT NULL DEFAULT 'NEW',
            score INTEGER NOT NULL DEFAULT 0,
            name VARCHAR(120),
            company VARCHAR(120),
            contact VARCHAR(255),
            project_type VARCHAR(120),
            problem TEXT,
            desired_solution TEXT,
            budget VARCHAR(120),
            timeline VARCHAR(120),
            intent VARCHAR(100),
            next_action VARCHAR(100),
            summary TEXT,
            last_summarized_count INTEGER NOT NULL DEFAULT 0,
            handoff_reason TEXT,
            handoff_at TIMESTAMPTZ,
            notified_owner INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """))

    # ─── ترحيل تلقائي لكل أعمدة الموديل ──────────────────────
    # هذا يضمن أن leads.last_summarized_count وأي عمود آخر
    # يعرّفه الموديل سيُضاف تلقائياً إن كان ناقصاً.
    added = await _ensure_columns_from_model(conn, Lead)
    if added:
        _boot(f"        ➕ أعمدة leads المضافة: {', '.join(added)}")

    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_leads_visitor_id ON leads (visitor_id);"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_leads_stage ON leads (stage);"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_leads_score ON leads (score);"
    ))
    _boot("        ✓ جدول leads جاهز")

    # ─────────────────────────────────────────────────────────────
    # 4) messages — مع معالجة البنية القديمة
    # ─────────────────────────────────────────────────────────────

    _boot("  [4/5] إنشاء/التحقق من جدول messages...")
    result = await conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'messages'
    """))
    existing_cols = {row[0] for row in result.fetchall()}

    needs_recreate = bool(existing_cols) and ("lead_id" not in existing_cols)

    if needs_recreate:
        _boot("        ⚠️  جدول messages ببنية قديمة — سيُحذف ويُعاد إنشاؤه")
        log.warning(
            "⚠️  جدول messages موجود ببنية قديمة (بدون lead_id). "
            "سيُحذف ويُعاد إنشاؤه."
        )
        await conn.execute(text("DROP TABLE IF EXISTS messages CASCADE"))

    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            role VARCHAR(16) NOT NULL,
            content TEXT,
            tool_name VARCHAR(64),
            tool_payload TEXT,
            tool_result TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """))

    added = await _ensure_columns_from_model(conn, Message)
    if added:
        _boot(f"        ➕ أعمدة messages المضافة: {', '.join(added)}")

    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_messages_lead_id ON messages (lead_id);"
    ))
    await conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at);"
    ))
    _boot("        ✓ جدول messages جاهز")

    # ─────────────────────────────────────────────────────────────
    # 5) فحص نهائي: التأكد من الأعمدة الحرجة
    # ─────────────────────────────────────────────────────────────

    _boot("  [5/5] فحص نهائي للأعمدة الحرجة...")
    critical = [
        ("leads", "last_summarized_count"),
        ("leads", "visitor_id"),
        ("leads", "stage"),
        ("leads", "score"),
        ("messages", "lead_id"),
        ("messages", "role"),
        ("visitors", "visitor_uid"),
    ]
    missing = []
    for tbl, col in critical:
        if not await _column_exists(conn, tbl, col):
            missing.append(f"{tbl}.{col}")

    if missing:
        msg = "❌ أعمدة حرجة مفقودة بعد الترحيل: " + ", ".join(missing)
        _boot("        " + msg)
        log.error(msg)
        raise RuntimeError(msg)

    _boot("        ✓ جميع الأعمدة الحرجة موجودة")

    _boot("═" * 60)
    _boot("✅ [MIGRATION] اكتملت جميع جداول AI Sales Agent بنجاح")
    _boot("═" * 60)
    _boot("")


# ══════════════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):

    _boot("")
    _boot("█" * 60)
    _boot("🚀 [STARTUP] بدء تشغيل التطبيق...")
    _boot("█" * 60)

    # ── التحقق من DATABASE_URL ────────────────────────────────────
    db_url = settings.DATABASE_URL
    safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
    _boot(f"📦 [STARTUP] DATABASE_URL host: ...@{safe_url}")

    if "localhost" in db_url or "127.0.0.1" in db_url:
        _boot(
            "⚠️  [STARTUP] DATABASE_URL تشير إلى localhost — "
            "تأكد من ضبط متغير البيئة DATABASE_URL على خادم الإنتاج."
        )
        log.warning(
            "⚠️  DATABASE_URL تشير إلى localhost — "
            "تأكد من ضبط متغير البيئة DATABASE_URL على خادم الإنتاج."
        )

    # ── 1) إنشاء الجداول الأساسية عبر metadata ────────────────────
    _boot("")
    _boot("🔄 [STARTUP] (1/4) إنشاء الجداول الأساسية عبر metadata...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _boot("✅ [STARTUP] (1/4) تم إنشاء/التحقق من جداول metadata")
        log.info("✓ تم إنشاء/التحقق من جداول metadata")
    except Exception as exc:
        _boot(f"❌ [STARTUP] (1/4) فشل الاتصال بقاعدة البيانات: {exc}")
        log.critical(
            "❌ فشل الاتصال بقاعدة البيانات عند الإقلاع: %s\n"
            "   تأكد من ضبط DATABASE_URL بشكل صحيح في متغيرات البيئة.",
            exc,
        )
        raise SystemExit(1) from exc

    # ── 2) ضمان جداول AI Sales Agent (idempotent + migrations) ────
    _boot("")
    _boot("🔄 [STARTUP] (2/4) ضمان جداول AI Sales Agent...")
    try:
        async with engine.begin() as conn:
            await _ensure_chat_tables(conn)
        _boot("✅ [STARTUP] (2/4) تم التأكد من جداول visitors/leads/messages")
        log.info("✓ تم التأكد من جداول visitors/leads/messages")
    except Exception as exc:
        _boot(f"❌ [STARTUP] (2/4) فشل إنشاء/ترحيل جداول chat: {exc}")
        log.error("⚠️  فشل إنشاء/ترحيل جداول chat: %s", exc)
        # لا نوقف التطبيق — قد تكون المشكلة مؤقتة

    # ── 3) إنشاء/تحديث حساب المدير ────────────────────────────────
    _boot("")
    _boot("🔄 [STARTUP] (3/4) إنشاء/تحديث حساب المدير...")
    async with AsyncSessionLocal() as db:

        existing = (
            await db.execute(
                select(User).where(User.email == settings.ADMIN_EMAIL)
            )
        ).scalar_one_or_none()

        if not existing:
            db.add(User(
                email=settings.ADMIN_EMAIL,
                full_name=settings.SITE_AUTHOR,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                is_admin=True,
                is_active=True,
                bio="مؤسس المنصة",
            ))
            await db.commit()
            _boot(f"✅ [STARTUP] تم إنشاء حساب المدير: {settings.ADMIN_EMAIL}")
            log.info("✓ تم إنشاء حساب المدير الافتراضي: %s", settings.ADMIN_EMAIL)

        elif existing.full_name != settings.SITE_AUTHOR:
            existing.full_name = settings.SITE_AUTHOR
            await db.commit()
            _boot(f"✅ [STARTUP] تم تحديث اسم المدير إلى: {settings.SITE_AUTHOR}")
            log.info("✓ تم تحديث اسم المدير إلى: %s", settings.SITE_AUTHOR)
        else:
            _boot("ℹ️  [STARTUP] حساب المدير موجود مسبقاً — لا تغيير")

        # ── مزامنة seo_settings ───────────────────────────────────
        _boot("🔄 [STARTUP] مزامنة seo_settings...")
        from app.utils.site_settings import load_site_settings, _apply_to_templates

        await db.execute(text("""
            INSERT INTO seo_settings (key, value)
            VALUES (:k1, :n1), (:k2, :n2), (:k3, :n3)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """), {
            "k1": "site_name",        "n1": settings.APP_NAME,
            "k2": "site_author",      "n2": settings.SITE_AUTHOR,
            "k3": "site_description", "n3": settings.SITE_DESCRIPTION,
        })
        await db.commit()

        await load_site_settings(db)
        _apply_to_templates()
        _boot("✅ [STARTUP] تمت مزامنة seo_settings وتطبيقها على القوالب")

    # ── 4) تشغيل heartbeat ────────────────────────────────────────
    _boot("")
    _boot("🔄 [STARTUP] (4/4) تشغيل heartbeat...")
    from app.services import heartbeat
    heartbeat.start()
    _boot("✅ [STARTUP] heartbeat يعمل")

    _boot("")
    _boot("█" * 60)
    _boot("✅ [STARTUP] التطبيق جاهز لاستقبال الطلبات")
    _boot("█" * 60)
    _boot("")

    try:
        yield
    finally:
        _boot("")
        _boot("🛑 [SHUTDOWN] إيقاف heartbeat...")
        await heartbeat.stop()
        _boot("🛑 [SHUTDOWN] تم الإيقاف بنجاح")


# ══════════════════════════════════════════════════════════════════════
# App
# ══════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.SITE_DESCRIPTION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Middleware: منع الكاش لصفحات الإدارة ──────────────────────────
class NoCacheAdminMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = (
                "no-cache, no-store, must-revalidate, private"
            )
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


# ── Middleware: اللغة ──────────────────────────────────────────────
class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.cookies.get(LOCALE_COOKIE, "ar")
        set_locale(lang if lang in SUPPORTED_LOCALES else "ar")
        return await call_next(request)


# Middleware order (executed bottom-up)
app.add_middleware(NoCacheAdminMiddleware)
app.add_middleware(LocaleMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=600)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=not settings.DEBUG,
    same_site="lax",
)
app.add_middleware(RedirectMiddleware)
app.add_middleware(AnalyticsMiddleware)


# ── Static files ───────────────────────────────────────────────────
app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)


# ── Routers ────────────────────────────────────────────────────────
app.include_router(public.router)
app.include_router(seo_routes.router)
app.include_router(auth_routes.router)
app.include_router(downloads.router)
app.include_router(chat_route.router)
app.include_router(admin_router)


# ══════════════════════════════════════════════════════════════════════
# Misc endpoints
# ══════════════════════════════════════════════════════════════════════

@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/set-lang/{lang}")
async def set_lang(lang: str, request: Request):
    referer = request.headers.get("referer", "/")
    resp = RedirectResponse(url=referer, status_code=303)
    resp.set_cookie(
        LOCALE_COOKIE,
        lang if lang in SUPPORTED_LOCALES else "ar",
        max_age=60 * 60 * 24 * 365,
        samesite="lax",
    )
    return resp


# ── Error handlers ─────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        "public/404.html",
        {
            "request": request,
            "meta": {
                "title": "404",
                "description": "الصفحة غير موجودة",
                "robots": "noindex,follow",
            },
        },
        status_code=404,
    )


@app.exception_handler(500)
async def server_error(request: Request, exc):
    log.exception("server error")
    return templates.TemplateResponse(
        "public/500.html",
        {
            "request": request,
            "meta": {
                "title": "خطأ",
                "description": "حدث خطأ ما",
                "robots": "noindex,nofollow",
            },
        },
        status_code=500,
    )
