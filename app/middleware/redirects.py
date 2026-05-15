"""إعادة التوجيه من جدول redirects."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.seo import Redirect


class RedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "GET":
            try:
                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(Redirect).where(Redirect.source == request.url.path))
                    rec = res.scalar_one_or_none()
                    if rec:
                        return RedirectResponse(rec.target, status_code=rec.status_code)
            except Exception:
                pass
        return await call_next(request)
