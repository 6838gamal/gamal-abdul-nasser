"""إرسال إشعارات الفهرسة لمحركات البحث."""
import logging, httpx
from app.core.config import settings

log = logging.getLogger(__name__)


async def ping_search_engines(url: str) -> None:
    """Ping bing + IndexNow + sitemap pings."""
    pings = [
        f"https://www.bing.com/ping?sitemap={settings.APP_URL}/sitemap.xml",
    ]
    async with httpx.AsyncClient(timeout=5) as client:
        for u in pings:
            try:
                await client.get(u)
            except Exception as e:
                log.warning("ping failed %s: %s", u, e)


async def google_indexing_request(url: str, action: str = "URL_UPDATED") -> bool:
    """طلب فهرسة عبر Google Indexing API (يحتاج service-account)."""
    if not settings.GOOGLE_INDEXING_KEY_FILE:
        return False
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_INDEXING_KEY_FILE,
            scopes=["https://www.googleapis.com/auth/indexing"])
        service = build("indexing", "v3", credentials=creds, cache_discovery=False)
        service.urlNotifications().publish(body={"url": url, "type": action}).execute()
        return True
    except Exception as e:
        log.warning("google indexing failed: %s", e)
        return False
