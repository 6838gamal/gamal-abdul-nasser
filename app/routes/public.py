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


@router.get("/about")
async def about(request: Request):
    meta = base_meta("من أنا — " + settings.SITE_AUTHOR,
                     "نبذة عن " + settings.SITE_AUTHOR + " وخبراته ومهاراته التقنية.", "/about")
    return templates.TemplateResponse("public/about.html", {"request": request, "meta": meta,
                                                             "jsonld": [organization_jsonld()]})


# ---------- المشاريع ----------
@router.get("/projects")
async def projects(request: Request, q: str | None = None, tag: str | None = None,
                   db: AsyncSession = Depends(get_db)):
    stmt = select(Project).where(Project.is_published == True).order_by(Project.created_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Project.title.ilike(like) | Project.short_description.ilike(like))
    items = (await db.execute(stmt)).scalars().all()
    if tag:
        items = [p for p in items if tag in (p.tags or [])]
    meta = base_meta("المشاريع", "تصفح أحدث المشاريع التقنية والإبداعية.", "/projects")
    return templates.TemplateResponse("public/projects.html", {
        "request": request, "meta": meta, "items": items, "q": q or "", "tag": tag or "",
    })


@router.get("/projects/{slug}")
async def project_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Project).where(Project.slug == slug,
                                                 Project.is_published == True))).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    meta = base_meta(p.meta_title or p.title, p.meta_description or p.short_description,
                     f"/projects/{p.slug}", p.cover_image, og_type="article")
    crumbs = breadcrumbs_jsonld([("الرئيسية", "/"), ("المشاريع", "/projects"), (p.title, f"/projects/{p.slug}")],
                                 settings.APP_URL)
    return templates.TemplateResponse("public/project_detail.html", {
        "request": request, "meta": meta, "p": p, "jsonld": [crumbs],
    })


# ---------- الخدمات ----------
@router.get("/services")
async def services_list(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(Service).where(Service.is_published == True)
                              .order_by(Service.sort_order))).scalars().all()
    meta = base_meta("الخدمات", "خدماتي الاحترافية للأفراد والشركات.", "/services")
    return templates.TemplateResponse("public/services.html", {
        "request": request, "meta": meta, "items": items,
    })


@router.get("/services/{slug}")
async def service_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Service).where(Service.slug == slug,
                                                 Service.is_published == True))).scalar_one_or_none()
    if not s:
        raise HTTPException(404)
    meta = base_meta(s.meta_title or s.title, s.meta_description or s.short_description,
                     f"/services/{s.slug}", s.cover_image, "service")
    return templates.TemplateResponse("public/service_detail.html", {
        "request": request, "meta": meta, "s": s,
    })


# ---------- المنتجات ----------
@router.get("/products")
async def products_list(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(Product).where(Product.is_published == True))).scalars().all()
    meta = base_meta("المنتجات الرقمية", "منتجات رقمية جاهزة للتحميل الفوري.", "/products")
    return templates.TemplateResponse("public/products.html", {
        "request": request, "meta": meta, "items": items,
    })


@router.get("/products/{slug}")
async def product_detail(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where(Product.slug == slug,
                                                 Product.is_published == True))).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    meta = base_meta(p.meta_title or p.title, p.meta_description or p.short_description,
                     f"/products/{p.slug}", p.cover_image, og_type="product")
    jsonld = [{
        "@context": "https://schema.org", "@type": "Product",
        "name": p.title, "description": p.short_description,
        "image": settings.APP_URL + (p.cover_image or settings.DEFAULT_OG_IMAGE),
        "offers": {"@type": "Offer", "price": str(p.price), "priceCurrency": p.currency,
                   "availability": "https://schema.org/InStock"},
    }]
    return templates.TemplateResponse("public/product_detail.html", {
        "request": request, "meta": meta, "p": p, "jsonld": jsonld,
    })


# ---------- المدونة ----------
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


# ---------- التواصل ----------
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
    # HTMX: نعيد جزء "شكراً"
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/contact_thanks.html", {"request": request})
    meta = base_meta("شكراً", "تم استلام رسالتك.", "/contact")
    return templates.TemplateResponse("public/contact.html",
                                       {"request": request, "meta": meta, "sent": True})
