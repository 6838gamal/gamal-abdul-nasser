"""إدارة إعدادات الموقع الكاملة من قاعدة البيانات مع كاش في الذاكرة."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.seo import SeoSetting
from app.core.config import settings as env_settings

# جميع المفاتيح القابلة للتعديل
ALL_KEYS = [
    # إعدادات الموقع الأساسية
    "site_name", "site_author", "site_description", "site_url", "site_locale", "default_og",
    "nav_logo",
    # الصفحة الرئيسية
    "hero_badge", "hero_cta1_text", "hero_cta1_url", "hero_cta2_text", "hero_cta2_url",
    "cta_title", "cta_body", "cta_btn",
    # صفحة من أنا
    "about_intro",
    "about_skills_title", "about_skills",
    "about_tech_title", "about_tech",
    "about_exp_title", "about_exp",
    # التواصل الاجتماعي
    "social_whatsapp", "social_twitter", "social_linkedin",
    "social_github", "social_youtube", "social_email",
    # التذييل
    "footer_tagline",
]

_cache: dict = {}


def _defaults() -> dict:
    return {
        "site_name": env_settings.APP_NAME,
        "site_author": env_settings.SITE_AUTHOR,
        "site_description": env_settings.SITE_DESCRIPTION,
        "site_url": env_settings.APP_URL,
        "site_locale": env_settings.SITE_LOCALE,
        "default_og": env_settings.DEFAULT_OG_IMAGE,
        "nav_logo": "J",
        # الصفحة الرئيسية
        "hero_badge": "مطوّر حلول رقمية ذكية",
        "hero_cta1_text": "شاهد المشاريع",
        "hero_cta1_url": "/projects",
        "hero_cta2_text": "تواصل معي",
        "hero_cta2_url": "/contact",
        "cta_title": "لديك مشروع أو فكرة تشغيلية؟",
        "cta_body": "حوّلها إلى نظام عملي يوفر الوقت ويزيد الإنتاجية.",
        "cta_btn": "ابدأ الآن",
        # صفحة من أنا
        "about_intro": (
            "مرحباً، أنا جمال المقطري، مطور تطبيقات وحلول رقمية متخصص في بناء الأنظمة الذكية "
            "وأتمتة العمليات وتحويل الأفكار إلى منتجات تقنية عملية.\n\n"
            "أساعد الأفراد والشركات والمؤسسات على تقليل الأعمال اليدوية، تحسين الإنتاجية، "
            "تنظيم البيانات، وأتمتة المهام المتكررة من خلال تطبيقات الويب، تطبيقات الجوال، "
            "أدوات الذكاء الاصطناعي، وأنظمة إدارة الأعمال المخصصة.\n\n"
            "أؤمن أن التقنية ليست مجرد برمجيات، بل وسيلة لحل المشكلات الحقيقية وتوفير الوقت "
            "والجهد وخلق فرص نمو جديدة. لذلك أركز دائماً على بناء حلول عملية قابلة للتطبيق "
            "تحقق قيمة ملموسة للمستخدم النهائي."
        ),
        "about_skills_title": "الخدمات",
        "about_skills": (
            "تطوير تطبيقات الويب المخصصة\n"
            "تطوير تطبيقات الجوال\n"
            "بناء أنظمة إدارة الأعمال\n"
            "أتمتة العمليات والإجراءات الداخلية\n"
            "دمج الذكاء الاصطناعي في الأعمال\n"
            "تطوير أنظمة إدارة العملاء (CRM)\n"
            "تطوير لوحات التحكم والتقارير التفاعلية\n"
            "حلول إدارة الوثائق والأرشفة الرقمية\n"
            "أنظمة خدمة العملاء والتواصل عبر واتساب\n"
            "تطوير منتجات SaaS\n"
            "تحليل المتطلبات وتحويل الأفكار إلى منتجات رقمية\n"
            "اختبار الأنظمة وتحسين الأداء والجودة"
        ),
        "about_tech_title": "المهارات التقنية",
        "about_tech": (
            "Python\n"
            "Flutter\n"
            "JavaScript\n"
            "TypeScript\n"
            "PostgreSQL\n"
            "MySQL\n"
            "REST APIs\n"
            "AI Integration\n"
            "Workflow Automation\n"
            "OCR & Document Processing\n"
            "Data Analysis\n"
            "Cloud Deployment\n"
            "System Architecture"
        ),
        "about_exp_title": "لماذا تختار العمل معي؟",
        "about_exp": (
            "التركيز على حل المشكلة وليس كتابة الكود فقط\n"
            "فهم احتياجات الأعمال قبل التطوير\n"
            "خبرة في الأتمتة والذكاء الاصطناعي\n"
            "حلول قابلة للتوسع والتطوير\n"
            "اهتمام بتجربة المستخدم وسهولة الاستخدام\n"
            "دعم فني وتحسين مستمر\n"
            "القدرة على تحويل الأفكار إلى منتجات قابلة للبيع والتشغيل"
        ),
        # التواصل الاجتماعي
        "social_whatsapp": "",
        "social_twitter": "",
        "social_linkedin": "",
        "social_github": "",
        "social_youtube": "",
        "social_email": "",
        # التذييل
        "footer_tagline": "",
    }


async def load_site_settings(db: AsyncSession) -> dict:
    rows = (await db.execute(
        select(SeoSetting).where(SeoSetting.key.in_(ALL_KEYS))
    )).scalars().all()
    result = _defaults()
    for row in rows:
        result[row.key] = row.value
    _cache.update(result)
    return result


async def save_site_settings(db: AsyncSession, data: dict) -> dict:
    for key, val in data.items():
        if key not in ALL_KEYS:
            continue
        existing = (await db.execute(
            select(SeoSetting).where(SeoSetting.key == key)
        )).scalar_one_or_none()
        if existing:
            existing.value = val
        else:
            db.add(SeoSetting(key=key, value=val))
    await db.commit()
    _cache.update(data)
    _apply_to_templates()
    return _cache


def get_cached() -> dict:
    if not _cache:
        _cache.update(_defaults())
    return _cache


def _lines(key: str) -> list[str]:
    """تحويل النص متعدد الأسطر إلى قائمة."""
    return [l.strip() for l in get_cached().get(key, "").splitlines() if l.strip()]


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

    templates.env.globals["content"] = {
        "nav_logo": c.get("nav_logo", "G"),
        # الصفحة الرئيسية
        "hero_badge": c.get("hero_badge", "منصة شخصية احترافية"),
        "hero_cta1_text": c.get("hero_cta1_text", "شاهد المشاريع"),
        "hero_cta1_url": c.get("hero_cta1_url", "/projects"),
        "hero_cta2_text": c.get("hero_cta2_text", "تواصل معي"),
        "hero_cta2_url": c.get("hero_cta2_url", "/contact"),
        "cta_title": c.get("cta_title", "لديك مشروع أو فكرة؟"),
        "cta_body": c.get("cta_body", "دعنا نحوّلها إلى منتج حقيقي."),
        "cta_btn": c.get("cta_btn", "ابدأ الآن"),
        # صفحة من أنا
        "about_intro": c.get("about_intro", ""),
        "about_skills_title": c.get("about_skills_title", "المهارات"),
        "about_skills": [l for l in c.get("about_skills", "").splitlines() if l.strip()],
        "about_tech_title": c.get("about_tech_title", "التقنيات"),
        "about_tech": [l for l in c.get("about_tech", "").splitlines() if l.strip()],
        "about_exp_title": c.get("about_exp_title", "الخبرات"),
        "about_exp": [l for l in c.get("about_exp", "").splitlines() if l.strip()],
        # التواصل الاجتماعي
        "social_whatsapp": c.get("social_whatsapp", ""),
        "social_twitter": c.get("social_twitter", ""),
        "social_linkedin": c.get("social_linkedin", ""),
        "social_github": c.get("social_github", ""),
        "social_youtube": c.get("social_youtube", ""),
        "social_email": c.get("social_email", ""),
        # التذييل
        "footer_tagline": c.get("footer_tagline", ""),
    }
