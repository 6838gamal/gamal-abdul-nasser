"""رؤوس HTTP الآمنة + CSP."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "SAMEORIGIN"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        h["X-XSS-Protection"] = "1; mode=block"
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # CSP — مرن للسماح بـ HTMX/Alpine + analytics
        h["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        )
        return response
