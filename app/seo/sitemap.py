"""مولّد Sitemap XML ديناميكي + News Sitemap + RSS."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.article import Article
from app.models.project import Project
from app.models.product import Product
from app.models.service import Service
from app.models.seo import CustomSitemapURL
from app.core.config import settings


def _url(loc, lastmod=None, changefreq="weekly", priority="0.7", image=None):
    parts = [f"<url><loc>{loc}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod.isoformat()}</lastmod>")
    parts.append(f"<changefreq>{changefreq}</changefreq>")
    parts.append(f"<priority>{priority}</priority>")
    if image:
        parts.append(f'<image:image><image:loc>{image}</image:loc></image:image>')
    parts.append("</url>")
    return "".join(parts)


async def build_sitemap(db) -> str:
    base = settings.APP_URL.rstrip("/")
    urls = [
        _url(f"{base}/", changefreq="daily", priority="1.0"),
        _url(f"{base}/about"),
        _url(f"{base}/projects"),
        _url(f"{base}/services"),
        _url(f"{base}/products"),
        _url(f"{base}/blog"),
        _url(f"{base}/contact"),
    ]
    for art in (await db.execute(select(Article).where(Article.is_published == True))).scalars():
        urls.append(_url(f"{base}/blog/{art.slug}", art.updated_at, "weekly", "0.8",
                         (base + art.cover_image) if art.cover_image else None))
    for p in (await db.execute(select(Project).where(Project.is_published == True))).scalars():
        urls.append(_url(f"{base}/projects/{p.slug}", p.updated_at))
    for s in (await db.execute(select(Service).where(Service.is_published == True))).scalars():
        urls.append(_url(f"{base}/services/{s.slug}"))
    for prod in (await db.execute(select(Product).where(Product.is_published == True))).scalars():
        urls.append(_url(f"{base}/products/{prod.slug}"))

    # الروابط المخصصة التي يضيفها المدير
    for cu in (await db.execute(select(CustomSitemapURL).order_by(CustomSitemapURL.id))).scalars():
        loc = cu.url if cu.url.startswith("http://") or cu.url.startswith("https://") \
              else base + "/" + cu.url.lstrip("/")
        urls.append(_url(loc, changefreq=cu.changefreq, priority=cu.priority))

    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
            + "".join(urls) + "</urlset>")


async def build_news_sitemap(db) -> str:
    """Sitemap مخصص لـ Google News (المقالات آخر 48 ساعة)."""
    from datetime import timedelta
    base = settings.APP_URL.rstrip("/")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    items = []
    res = await db.execute(select(Article).where(
        Article.is_published == True, Article.published_at >= cutoff
    ).order_by(Article.published_at.desc()))
    for a in res.scalars():
        items.append(
            f'<url><loc>{base}/blog/{a.slug}</loc>'
            f'<news:news><news:publication><news:name>{settings.APP_NAME}</news:name>'
            f'<news:language>ar</news:language></news:publication>'
            f'<news:publication_date>{a.published_at.isoformat()}</news:publication_date>'
            f'<news:title>{a.title}</news:title></news:news></url>'
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
            + "".join(items) + "</urlset>")


async def build_rss(db) -> str:
    from feedgen.feed import FeedGenerator
    base = settings.APP_URL.rstrip("/")
    fg = FeedGenerator()
    fg.title(settings.APP_NAME)
    fg.link(href=base, rel="alternate")
    fg.description(settings.SITE_DESCRIPTION)
    fg.language("ar")
    res = await db.execute(select(Article).where(Article.is_published == True)
                           .order_by(Article.published_at.desc()).limit(50))
    for a in res.scalars():
        fe = fg.add_entry()
        fe.id(f"{base}/blog/{a.slug}")
        fe.title(a.title)
        fe.link(href=f"{base}/blog/{a.slug}")
        fe.description(a.excerpt)
        if a.published_at:
            fe.pubDate(a.published_at)
    return fg.rss_str(pretty=True).decode()
