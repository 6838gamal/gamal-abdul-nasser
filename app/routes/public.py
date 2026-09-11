"""المسارات العامة للموقع."""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.article import Article, Category, Tag
from app.models.project import Project
from app.models.service import Service
from app.models.product import Product
from app.models.message import Message
from app.utils.templates import templates
from app.seo.meta import base_meta, organization_jsonld, article_jsonld, breadcrumbs_jsonld, faq_jsonld
from app.core.config import settings

router = APIRouter()


# ============================================================
# الرئيسية
# ============================================================
@router.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    featured_projects = (await db.execute(
        select(Project).where(Project.is_published == True, Project.featured == True).limit(6)
    )).scalars().all()
    latest_articles = (await db.execute(
        select(Article).where(Article.is_published == True)
        .order_by(Article.published_at.desc().nullslast()).limit(4)
    )).scalars().all()
    services = (await db.execute(
        select(Service).where(Service.is_published == True).order_by(Service.sort_order).limit(6)
    )).scalars().all()
    products = (await db.execute(
        select(Product).where(Product.is_published == True).limit(4)
    )).scalars().all()
    meta = base_meta(settings.APP_NAME,
                     settings.SITE_DESCRIPTION, "/")
    return templates.TemplateResponse("public/home.html", {
        "request": request, "meta": meta, "jsonld": [organization_jsonld()],
        "featured_projects": featured_projects, "latest_articles": latest_articles,
        "services": services, "products": products,
    })


# ============================================================
# من أنا
# ============================================================
@router.get("/about")
async def about(request: Request):
    meta = base_meta("من أنا — " + settings.SITE_AUTHOR,
                     "نبذة عن " + settings.SITE_AUTHOR + " وخبراته ومهاراته التقنية.", "/about")
    return templates.TemplateResponse("public/about.html", {"request": request, "meta": meta,
                                                             "jsonld": [organization_jsonld()]})


# ============================================================
# خدمات الذكاء الاصطناعي
# ============================================================
@router.get("/ai-agent-development")
async def ai_agent_development(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(
        select(Service).where(Service.is_published == True).order_by(Service.sort_order)
    )).scalars().all()
    meta = base_meta("تطوير وكلاء الذكاء الاصطناعي",
                     "بناء وكلاء أذكياء مخصصين لأتمتة المهام المعقدة والتفاعل الذكي.", "/ai-agent-development")
    return templates.TemplateResponse("public/ai_agent_development.html", {
        "request": request, "meta": meta, "items": items,
    })


@router.get("/ai-automation")
async def ai_automation(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(
        select(Service).where(Service.is_published == True).order_by(Service.sort_order)
    )).scalars().all()
    meta = base_meta("أتمتة الذكاء الاصطناعي",
                     "أتمتة العمليات والسيناريوهات المتكررة باستخدام الذكاء الاصطناعي.", "/ai-automation")
    return templates.TemplateResponse("public/ai_automation.html", {
        "request": request, "meta": meta, "items": items,
    })


@router.get("/workflow-automation")
async def workflow_automation(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(
        select(Service).where(Service.is_published == True).order_by(Service.sort_order)
    )).scalars().all()
    meta = base_meta("أتمتة سير العمل",
                     "ربط الأنظمة والأدوات وبناء تدفقات عمل ذكية بدون تدخل يدوي.", "/workflow-automation")
    return templates.TemplateResponse("public/workflow_automation.html", {
        "request": request, "meta": meta, "items": items,
    })


@router.get("/whatsapp-ai-agent")
async def whatsapp_ai_agent(request: Request):
    meta = base_meta("وكيل واتساب الذكي",
                     "وكيل ذكي يتفاعل مع عملائك على واتساب على مدار الساعة.", "/whatsapp-ai-agent")
    return templates.TemplateResponse("public/whatsapp_ai_agent.html", {
        "request": request, "meta": meta,
    })


@router.get("/ai-assistant")
async def ai_assistant(request: Request):
    meta = base_meta("المساعد الذكي",
                     "مساعد ذكي مخصص لمساعدتك في المهام اليومية واتخاذ القرارات.", "/ai-assistant")
    return templates.TemplateResponse("public/ai_assistant.html", {
        "request": request, "meta": meta,
    })


@router.get("/document-intelligence")
async def document_intelligence(request: Request):
    meta = base_meta("ذكاء المستندات",
                     "استخراج وفهم وتحليل بيانات المستندات تلقائياً باستخدام الذكاء الاصطناعي.",
                     "/document-intelligence")
    return templates.TemplateResponse("public/document_intelligence.html", {
        "request": request, "meta": meta,
    })


# ============================================================
# دراسات الحالة (Case Studies)
# ============================================================

# ---------- قائمة دراسات الحالة ----------
@router.get("/case-studies")
async def case_studies(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(
        select(Project).where(Project.is_published == True, Project.featured == True)
        .order_by(Project.created_at.desc()).limit(12)
    )).scalars().all()
    meta = base_meta("دراسات الحالة",
                     "قصص نجاح ومشاريع حقيقية مع النتائج والتأثير.", "/case-studies")
    return templates.TemplateResponse("public/case_studies.html", {
        "request": request, "meta": meta, "items": items,
    })


# ---------- تفاصيل دراسة حالة واحدة ----------
@router.get("/case-studies/{slug}")
async def case_study_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(
        select(Project).where(
            Project.slug == slug,
            Project.is_published == True
        )
    )).scalar_one_or_none()

    if not p:
        raise HTTPException(status_code=404, detail="Case study not found")

    meta = base_meta(
        p.title,
        p.short_description or p.title,
        f"/case-studies/{p.slug}",
        p.cover_image,
        og_type="article"
    )

    jsonld = [
        breadcrumbs_jsonld(
            [("الرئيسية", "/"),
             ("دراسات الحالة", "/case-studies"),
             (p.title, f"/case-studies/{p.slug}")],
            settings.APP_URL
        )
    ]

    return templates.TemplateResponse("public/case_study_detail.html", {
        "request": request,
        "meta": meta,
        "p": p,
        "jsonld": jsonld,
    })


# ============================================================
# المدونة (Blog)
# ============================================================
@router.get("/blog")
async def blog(request: Request, q: str | None = None, cat: str | None = None,
               tag: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Article).where(Article.is_published == True).order_by(
        Article.published_at.desc().nullslast())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Article.title.ilike(like) | Article.excerpt.ilike(like))
    items = (await db.execute(stmt)).scalars().all()
    cats = (await db.execute(select(Category))).scalars().all()
    tags = (await db.execute(select(Tag))).scalars().all()
    meta = base_meta("المدونة", "مقالات تقنية ودروس وأفكار.", "/blog")
    return templates.TemplateResponse("public/blog.html", {
        "request": request, "meta": meta, "items": items, "cats": cats, "tags": tags,
        "q": q or "", "cat": cat or "", "tag": tag or "",
    })


@router.get("/blog/{slug}")
async def article_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(Article).where(Article.slug == slug,
                                                 Article.is_published == True))).scalar_one_or_none()
    if not a:
        raise HTTPException(404)
    a.views = (a.views or 0) + 1
    await db.commit()
    related = (await db.execute(
        select(Article).where(Article.is_published == True, Article.id != a.id).limit(3)
    )).scalars().all()
    meta = base_meta(a.meta_title or a.title, a.meta_description or a.excerpt,
                     f"/blog/{a.slug}", a.og_image or a.cover_image, og_type="article")
    jsonld = [article_jsonld(a, settings.APP_URL),
              breadcrumbs_jsonld([("الرئيسية", "/"), ("المدونة", "/blog"), (a.title, f"/blog/{a.slug}")],
                                  settings.APP_URL)]
    if a.faq_json:
        try:
            import json
            faqs = json.loads(a.faq_json)
            if faqs:
                jsonld.append(faq_jsonld(faqs))
        except Exception:
            pass
    return templates.TemplateResponse("public/article_detail.html", {
        "request": request, "meta": meta, "a": a, "related": related, "jsonld": jsonld,
    })


# ============================================================
# التواصل (Contact)
# ============================================================
@router.get("/contact")
async def contact(request: Request):
    meta = base_meta("تواصل معي", "أرسل رسالتك مباشرة.", "/contact")
    return templates.TemplateResponse("public/contact.html", {"request": request, "meta": meta})


@router.post("/contact")
async def contact_post(request: Request,
                       name: str = Form(min_length=2, max_length=150),
                       email: str = Form(max_length=255),
                       subject: str = Form(min_length=2, max_length=255),
                       body: str = Form(min_length=5, max_length=5000),
                       db: AsyncSession = Depends(get_db)):
    msg = Message(name=name.strip(), email=email.strip(), subject=subject.strip(),
                  body=body.strip(),
                  ip_address=(request.client.host if request.client else None))
    db.add(msg)
    await db.commit()
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/contact_thanks.html", {"request": request})
    meta = base_meta("شكراً", "تم استلام رسالتك.", "/contact")
    return templates.TemplateResponse("public/contact.html",
                                       {"request": request, "meta": meta, "sent": True})
