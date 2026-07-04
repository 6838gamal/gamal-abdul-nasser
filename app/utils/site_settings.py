"""إدارة إعدادات الموقع من قاعدة البيانات مع كاش في الذاكرة."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.seo import SeoSetting
from app.core.config import settings as env_settings

SITE_KEYS = ["site_name", "site_author", "site_description", "site_url", "site_locale", "default_og"]

_cache: dict = {}


def _defaults() -> dict:
    return {
        "site_name": env_settings.APP_NAME,
        "site_author": env_settings.SITE_AUTHOR,
        "site_description": env_settings.SITE_DESCRIPTION,
        "site_url": env_settings.APP_URL,
        "site_locale": env_settings.SITE_LOCALE,
        "default_og": env_settings.DEFAULT_OG_IMAGE,
    }


async def load_site_settings(db: AsyncSession) -> dict:
    rows = (await db.execute(
        select(SeoSetting).where(SeoSetting.key.in_(SITE_KEYS))
    )).scalars().all()
    result = _defaults()
    for row in rows:
        result[row.key] = row.value
    _cache.update(result)
    return result


async def save_site_settings(db: AsyncSession, data: dict) -> dict:
    for key in SITE_KEYS:
        if key not in data:
            continue
        existing = (await db.execute(
            select(SeoSetting).where(SeoSetting.key == key)
        )).scalar_one_or_none()
        if existing:
            existing.value = data[key]
        else:
            db.add(SeoSetting(key=key, value=data[key]))
    await db.commit()
    _cache.update(data)
    _apply_to_templates()
    return _cache


def get_cached() -> dict:
    if not _cache:
        _cache.update(_defaults())
    return _cache


def _apply_to_templates():
    from app.utils.templates import templates
    from datetime import datetime
    c = get_cached()
    templates.env.globals["site"] = {
        "name": c.get("site_name", env_settings.APP_NAME),
        "author": c.get("site_author", env_settings.SITE_AUTHOR),
        "description": c.get("site_description", env_settings.SITE_DESCRIPTION),
        "url": c.get("site_url", env_settings.APP_URL),
        "year": datetime.now().year,
        "default_og": c.get("default_og", env_settings.DEFAULT_OG_IMAGE),
    }
