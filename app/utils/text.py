"""أدوات معالجة النصوص: slug، تنظيف HTML، حساب وقت القراءة."""
import re, bleach
from slugify import slugify as _slugify


ALLOWED_TAGS = ["p", "br", "strong", "em", "u", "h1", "h2", "h3", "h4", "ul", "ol", "li",
                "a", "blockquote", "code", "pre", "img", "figure", "figcaption", "table",
                "thead", "tbody", "tr", "td", "th", "hr", "span", "div"]
ALLOWED_ATTRS = {"a": ["href", "title", "rel", "target"], "img": ["src", "alt", "title", "loading"],
                 "*": ["class", "id"]}


def slugify(text: str) -> str:
    return _slugify(text, lowercase=True, max_length=140, word_boundary=True,
                    save_order=True, allow_unicode=True) or "item"


def sanitize_html(html: str) -> str:
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def reading_time(html: str) -> int:
    text = re.sub(r"<[^>]+>", " ", html or "")
    words = len(text.split())
    return max(1, round(words / 200))
