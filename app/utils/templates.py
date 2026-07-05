"""تهيئة Jinja2 + الفلاتر العامة."""
from datetime import datetime
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
import markdown as md
from app.core.config import settings
from app.i18n import t, get_locale, get_dir

templates = Jinja2Templates(directory="app/templates")


def md_to_html(text: str) -> str:
    return Markup(md.markdown(text or "", extensions=["fenced_code", "tables", "toc"]))


def fmt_date(value, fmt="%Y-%m-%d"):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime(fmt)


templates.env.globals["site"] = {
    "name": settings.APP_NAME,
    "author": settings.SITE_AUTHOR,
    "description": settings.SITE_DESCRIPTION,
    "url": settings.APP_URL,
    "year": datetime.now().year,
    "default_og": settings.DEFAULT_OG_IMAGE,
}
templates.env.filters["md"] = md_to_html
templates.env.filters["fmtdate"] = fmt_date
templates.env.globals["t"] = t
templates.env.globals["locale"] = get_locale
templates.env.globals["text_dir"] = get_dir
