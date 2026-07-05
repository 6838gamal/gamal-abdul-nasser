"""نقطة دخول التطبيق."""
import logging
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
from sqlalchemy import select

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

setup_logging("INFO" if not settings.DEBUG else "DEBUG")
log = logging.getLogger("app")

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── التحقق من وجود DATABASE_URL قبل المحاولة ──────────────────
    db_url = settings.DATABASE_URL
    if "localhost" in db_url or "127.0.0.1" in db_url:
        log.warning(
            "⚠️  DATABASE_URL تشير إلى localhost — "
            "تأكد من ضبط متغير البيئة DATABASE_URL على خادم الإنتاج."
        )

    # ── إنشاء الجداول وحساب المدير الأول ─────────────────────────
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        log.critical(
            "❌ فشل الاتصال بقاعدة البيانات عند الإقلاع: %s\n"
            "   تأكد من ضبط DATABASE_URL بشكل صحيح في متغيرات البيئة.",
            exc,
        )
        raise SystemExit(1) from exc

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))).scalar_one_or_none()
        if not existing:
            db.add(User(email=settings.ADMIN_EMAIL,
                        full_name=settings.SITE_AUTHOR,
                        hashed_password=hash_password(settings.ADMIN_PASSWORD),
                        is_admin=True, is_active=True,
                        bio="مؤسس المنصة"))
            await db.commit()
            log.info("✓ تم إنشاء حساب المدير الافتراضي: %s", settings.ADMIN_EMAIL)
        elif existing.full_name != settings.SITE_AUTHOR:
            existing.full_name = settings.SITE_AUTHOR
            await db.commit()
            log.info("✓ تم تحديث اسم المدير إلى: %s", settings.SITE_AUTHOR)
        from app.utils.site_settings import load_site_settings, _apply_to_templates
        from sqlalchemy import text
        # مزامنة الاسم والوصف مباشرةً عبر UPSERT (يضمن تحديث القيم القديمة في DB)
        await db.execute(text("""
            INSERT INTO seo_settings (key, value)
            VALUES (:k1, :n1), (:k2, :n2), (:k3, :n3)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """), {
            "k1": "site_name",  "n1": settings.APP_NAME,
            "k2": "site_author", "n2": settings.SITE_AUTHOR,
            "k3": "site_description", "n3": settings.SITE_DESCRIPTION,
        })
        await db.commit()
        # تحميل جميع الإعدادات (ستظهر القيم المحدَّثة الآن)
        await load_site_settings(db)
        _apply_to_templates()

    from app.services import heartbeat
    heartbeat.start()
    try:
        yield
    finally:
        await heartbeat.stop()


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.SITE_DESCRIPTION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware: منع الكاش لصفحات الإدارة (لا عودة بعد الخروج) ──
class NoCacheAdminMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

# ── Middleware: تحديد لغة الواجهة الحالية من الكوكيز ──────────
class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.cookies.get(LOCALE_COOKIE, "ar")
        set_locale(lang if lang in SUPPORTED_LOCALES else "ar")
        response = await call_next(request)
        return response

# Middleware order matters (executed bottom-up)
app.add_middleware(NoCacheAdminMiddleware)
app.add_middleware(LocaleMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=600)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                   https_only=not settings.DEBUG, same_site="lax")
app.add_middleware(RedirectMiddleware)
app.add_middleware(AnalyticsMiddleware)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")
# ملاحظة: /uploads لم يعد ضرورياً — الملفات تُرفع إلى Supabase Storage مباشرةً

# Routers
app.include_router(public.router)
app.include_router(seo_routes.router)
app.include_router(auth_routes.router)
app.include_router(downloads.router)
app.include_router(chat_route.router)
app.include_router(admin_router)


@app.get("/healthz")
async def health():
    return {"status": "ok"}


@app.get("/set-lang/{lang}")
async def set_lang(lang: str, request: Request):
    referer = request.headers.get("referer", "/")
    resp = RedirectResponse(url=referer, status_code=303)
    resp.set_cookie(LOCALE_COOKIE, lang if lang in SUPPORTED_LOCALES else "ar",
                     max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("public/404.html", {"request": request,
                                                            "meta": {"title": "404", "description": "الصفحة غير موجودة",
                                                                     "robots": "noindex,follow"}},
                                       status_code=404)


@app.exception_handler(500)
async def server_error(request: Request, exc):
    log.exception("server error")
    return templates.TemplateResponse("public/500.html", {"request": request,
                                                            "meta": {"title": "خطأ", "description": "حدث خطأ ما",
                                                                     "robots": "noindex,nofollow"}},
                                       status_code=500)
