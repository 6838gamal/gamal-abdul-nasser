"""تتبع الزيارات بشكل خفيف وغير حاجب."""
import hashlib, asyncio
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.database.session import AsyncSessionLocal
from app.models.analytics import PageView


SKIP_PREFIXES = ("/static", "/admin", "/api/internal", "/healthz", "/favicon")


class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if request.method == "GET" and not any(path.startswith(p) for p in SKIP_PREFIXES) \
                and response.status_code == 200:
            asyncio.create_task(self._record(request))
        return response

    async def _record(self, request: Request):
        try:
            ua = request.headers.get("user-agent", "")[:500]
            ref = request.headers.get("referer", "")[:500] or None
            ip = (request.client.host if request.client else "0.0.0.0")
            ip_hash = hashlib.sha256(ip.encode()).hexdigest()
            device = "mobile" if "Mobi" in ua else "desktop"
            async with AsyncSessionLocal() as db:
                db.add(PageView(
                    path=request.url.path[:500],
                    referrer=ref,
                    user_agent=ua,
                    device=device,
                    ip_hash=ip_hash,
                ))
                await db.commit()
        except Exception:
            pass
