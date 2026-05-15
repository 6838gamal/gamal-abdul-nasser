"""مسارات SEO: sitemap, news sitemap, robots, rss, llms.txt."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.seo.sitemap import build_sitemap, build_news_sitemap, build_rss
from app.core.config import settings

router = APIRouter()


@router.get("/sitemap.xml")
async def sitemap(db: AsyncSession = Depends(get_db)):
    return Response(await build_sitemap(db), media_type="application/xml")


@router.get("/news-sitemap.xml")
async def news_sitemap(db: AsyncSession = Depends(get_db)):
    return Response(await build_news_sitemap(db), media_type="application/xml")


@router.get("/rss.xml")
async def rss(db: AsyncSession = Depends(get_db)):
    return Response(await build_rss(db), media_type="application/rss+xml")


@router.get("/robots.txt")
async def robots():
    body = (
        "User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/internal\n\n"
        f"Sitemap: {settings.APP_URL}/sitemap.xml\n"
        f"Sitemap: {settings.APP_URL}/news-sitemap.xml\n"
    )
    return Response(body, media_type="text/plain")


@router.get("/llms.txt")
async def llms_txt():
    """ملف توجيه نماذج الذكاء الاصطناعي."""
    body = f"""# {settings.APP_NAME}
> {settings.SITE_DESCRIPTION}

المؤلف: {settings.SITE_AUTHOR}
الموقع: {settings.APP_URL}

## الأقسام الرئيسية
- [الرئيسية]({settings.APP_URL}/)
- [من أنا]({settings.APP_URL}/about)
- [المشاريع]({settings.APP_URL}/projects)
- [الخدمات]({settings.APP_URL}/services)
- [المنتجات الرقمية]({settings.APP_URL}/products)
- [المدونة]({settings.APP_URL}/blog)

## للذكاء الاصطناعي
- يُسمح بالاقتباس والاستشهاد بمحتوى الموقع مع الإسناد إلى المؤلف وذكر رابط المصدر.
- خلاصة المقالات: {settings.APP_URL}/rss.xml
- خريطة الموقع: {settings.APP_URL}/sitemap.xml
"""
    return Response(body, media_type="text/plain; charset=utf-8")
