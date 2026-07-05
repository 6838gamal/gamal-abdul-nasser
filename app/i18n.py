"""نظام تبديل اللغة (عربي/إنجليزي) لواجهة الموقع العامة."""
from contextvars import ContextVar

DEFAULT_LOCALE = "ar"
SUPPORTED_LOCALES = ("ar", "en")
LOCALE_COOKIE = "lang"

DIR_MAP = {"ar": "rtl", "en": "ltr"}

_current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)


def set_locale(locale: str) -> None:
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE
    _current_locale.set(locale)


def get_locale() -> str:
    return _current_locale.get()


def get_dir() -> str:
    return DIR_MAP.get(get_locale(), "rtl")


TRANSLATIONS: dict[str, dict[str, str]] = {
    "ar": {
        "nav.home": "الرئيسية",
        "nav.about": "من أنا",
        "nav.projects": "المشاريع",
        "nav.services": "الخدمات",
        "nav.products": "المنتجات",
        "nav.blog": "المدونة",
        "nav.contact": "احجز استشارة",
        "footer.links": "روابط",
        "footer.other": "أخرى",
        "footer.about": "من أنا",
        "footer.projects": "المشاريع",
        "footer.services": "الخدمات",
        "footer.blog": "المدونة",
        "footer.contact": "التواصل",
        "footer.consult": "احجز استشارة",
        "footer.rights": "جميع الحقوق محفوظة",
        "theme.toggle": "تبديل الوضع الليلي/النهاري",
        "lang.toggle": "English",
        "admin.login_title": "دخول الإدارة",
        "admin.email": "البريد الإلكتروني",
        "admin.password": "كلمة المرور",
        "admin.submit": "دخول",
    },
    "en": {
        "nav.home": "Home",
        "nav.about": "About",
        "nav.projects": "Projects",
        "nav.services": "Services",
        "nav.products": "Products",
        "nav.blog": "Blog",
        "nav.contact": "Book a Consultation",
        "footer.links": "Links",
        "footer.other": "Other",
        "footer.about": "About",
        "footer.projects": "Projects",
        "footer.services": "Services",
        "footer.blog": "Blog",
        "footer.contact": "Contact",
        "footer.consult": "Book a Consultation",
        "footer.rights": "All rights reserved",
        "theme.toggle": "Toggle dark/light mode",
        "lang.toggle": "العربية",
        "admin.login_title": "Admin Login",
        "admin.email": "Email",
        "admin.password": "Password",
        "admin.submit": "Sign in",
    },
}


def t(key: str) -> str:
    locale = get_locale()
    return TRANSLATIONS.get(locale, {}).get(key) or TRANSLATIONS[DEFAULT_LOCALE].get(key, key)
