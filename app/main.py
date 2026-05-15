"""نقطة دخول التطبيق."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.gzip import GZipMiddleware
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
from app.routes import public, seo_routes, auth_routes, downloads
from app.admin.router import router as admin_router
from app.utils.templates import templates
from app.models.user import User

setup_logging("INFO" if not settings.DEBUG else "DEBUG")
log = logging.getLogger("app")

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # إنشاء الجداول وحساب المدير الأول إن لم يوجد
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.SITE_DESCRIPTION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware order matters (executed bottom-up)
app.add_middleware(GZipMiddleware, minimum_size=600)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                   https_only=not settings.DEBUG, same_site="lax")
app.add_middleware(RedirectMiddleware)
app.add_middleware(AnalyticsMiddleware)

# Static + uploads
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Routers
app.include_router(public.router)
app.include_router(seo_routes.router)
app.include_router(auth_routes.router)
app.include_router(downloads.router)
app.include_router(admin_router)


@app.get("/healthz")
async def health():
    return {"status": "ok"}


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
