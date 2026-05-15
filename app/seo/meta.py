"""بناء وسوم الميتا و JSON-LD لكل صفحة."""
from app.core.config import settings


def base_meta(title: str, description: str, path: str = "/", image: str | None = None,
              og_type: str = "website") -> dict:
    url = settings.APP_URL.rstrip("/") + path
    return {
        "title": title,
        "description": description,
        "canonical": url,
        "og": {
            "title": title,
            "description": description,
            "url": url,
            "type": og_type,
            "image": (image or settings.DEFAULT_OG_IMAGE),
            "site_name": settings.APP_NAME,
            "locale": settings.SITE_LOCALE,
        },
        "twitter": {"card": "summary_large_image", "title": title, "description": description,
                    "image": (image or settings.DEFAULT_OG_IMAGE)},
        "robots": "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1",
    }


def organization_jsonld() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": settings.SITE_AUTHOR,
        "url": settings.APP_URL,
        "image": settings.APP_URL + settings.DEFAULT_OG_IMAGE,
        "description": settings.SITE_DESCRIPTION,
    }


def article_jsonld(article, base_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": article.schema_type or "Article",
        "headline": article.title,
        "description": article.meta_description or article.excerpt,
        "image": [base_url + (article.og_image or article.cover_image or settings.DEFAULT_OG_IMAGE)],
        "datePublished": (article.published_at or article.created_at).isoformat(),
        "dateModified": article.updated_at.isoformat(),
        "author": {"@type": "Person", "name": settings.SITE_AUTHOR},
        "publisher": {"@type": "Organization", "name": settings.APP_NAME,
                      "logo": {"@type": "ImageObject", "url": base_url + settings.DEFAULT_OG_IMAGE}},
        "mainEntityOfPage": base_url + f"/blog/{article.slug}",
    }


def breadcrumbs_jsonld(items: list[tuple[str, str]], base_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": base_url + url}
            for i, (name, url) in enumerate(items)
        ],
    }


def faq_jsonld(items: list[dict]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q["q"],
             "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}
            for q in items
        ],
    }
