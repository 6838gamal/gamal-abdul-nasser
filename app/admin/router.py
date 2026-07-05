"""لوحة تحكم المدير - CRUD لكل الكيانات + لوحة الإحصائيات."""
import json, asyncio
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.services.auth import require_admin
from app.services.uploads import save_upload
from app.utils.templates import templates
from app.utils.text import slugify, sanitize_html, reading_time
from app.models.user import User
from app.models.article import Article, Category, Tag
from app.models.project import Project
from app.models.service import Service
from app.models.product import Product, Order
from app.models.message import Message
from app.models.analytics import PageView
from app.models.seo import Redirect, CustomSitemapURL
from app.seo.indexing import ping_search_engines, google_indexing_request
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.utils.site_settings import load_site_settings, save_site_settings

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


# ============ Dashboard ============
@router.get("")
@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_admin)):
    counts = {
        "articles": (await db.execute(select(func.count()).select_from(Article))).scalar() or 0,
        "projects": (await db.execute(select(func.count()).select_from(Project))).scalar() or 0,
        "services": (await db.execute(select(func.count()).select_from(Service))).scalar() or 0,
        "products": (await db.execute(select(func.count()).select_from(Product))).scalar() or 0,
        "messages_unread": (await db.execute(select(func.count()).select_from(Message).where(Message.is_read == False))).scalar() or 0,
    }
    since = datetime.now(timezone.utc) - timedelta(days=7)
    visits_week = (await db.execute(select(func.count()).select_from(PageView).where(PageView.created_at >= since))).scalar() or 0
    visits_today = (await db.execute(select(func.count()).select_from(PageView).where(
        PageView.created_at >= datetime.now(timezone.utc) - timedelta(days=1)))).scalar() or 0
    top_pages = (await db.execute(
        select(PageView.path, func.count().label("c")).where(PageView.created_at >= since)
        .group_by(PageView.path).order_by(desc("c")).limit(10)
    )).all()
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "user": user, "counts": counts,
        "visits_week": visits_week, "visits_today": visits_today,
        "top_pages": top_pages, "active": "dashboard",
    })


# ============ Articles ============
@router.get("/articles")
async def articles_list(request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    items = (await db.execute(select(Article).order_by(Article.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("admin/articles_list.html", {
        "request": request, "items": items, "user": user, "active": "articles",
    })


@router.get("/articles/new")
async def article_new(request: Request, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_admin)):
    cats = (await db.execute(select(Category))).scalars().all()
    return templates.TemplateResponse("admin/article_form.html", {
        "request": request, "a": None, "cats": cats, "user": user, "active": "articles",
    })


@router.post("/articles/new")
async def article_create(request: Request,
                         title: str = Form(...), excerpt: str = Form(...),
                         content: str = Form(...), category_id: int | None = Form(None),
                         tags: str = Form(""), is_published: bool = Form(False),
                         scheduled_at: str = Form(""),
                         meta_title: str = Form(""), meta_description: str = Form(""),
                         meta_keywords: str = Form(""), canonical_url: str = Form(""),
                         schema_type: str = Form("Article"), faq_json: str = Form(""),
                         cover: UploadFile | None = File(None),
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    safe_html = sanitize_html(content)
    a = Article(
        title=title.strip(), slug=slugify(title), excerpt=excerpt.strip(),
        content=safe_html, reading_time=reading_time(safe_html),
        category_id=category_id, is_published=is_published,
        published_at=datetime.now(timezone.utc) if is_published else None,
        scheduled_at=datetime.fromisoformat(scheduled_at) if scheduled_at else None,
        meta_title=meta_title or None, meta_description=meta_description or None,
        meta_keywords=meta_keywords or None, canonical_url=canonical_url or None,
        schema_type=schema_type or "Article", faq_json=faq_json or None,
        author_id=user.id,
    )
    if cover and cover.filename:
        a.cover_image = await save_upload(cover, "articles", images_only=True)
    # tags
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    for tname in tag_names:
        ts = slugify(tname)
        existing = (await db.execute(select(Tag).where(Tag.slug == ts))).scalar_one_or_none()
        if not existing:
            existing = Tag(name=tname, slug=ts)
            db.add(existing)
            await db.flush()
        a.tags.append(existing)
    db.add(a)
    await db.commit()
    if a.is_published:
        url = settings.APP_URL + f"/blog/{a.slug}"
        asyncio.create_task(ping_search_engines(url))
        asyncio.create_task(google_indexing_request(url))
    return RedirectResponse("/admin/articles", status_code=303)


@router.get("/articles/{aid}/edit")
async def article_edit(aid: int, request: Request, db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    a = await db.get(Article, aid)
    if not a:
        raise HTTPException(404)
    cats = (await db.execute(select(Category))).scalars().all()
    return templates.TemplateResponse("admin/article_form.html", {
        "request": request, "a": a, "cats": cats, "user": user, "active": "articles",
    })


@router.post("/articles/{aid}/edit")
async def article_update(aid: int,
                         title: str = Form(...), excerpt: str = Form(...),
                         content: str = Form(...), category_id: int | None = Form(None),
                         tags: str = Form(""), is_published: bool = Form(False),
                         meta_title: str = Form(""), meta_description: str = Form(""),
                         meta_keywords: str = Form(""), canonical_url: str = Form(""),
                         schema_type: str = Form("Article"), faq_json: str = Form(""),
                         cover: UploadFile | None = File(None),
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    a = await db.get(Article, aid)
    if not a:
        raise HTTPException(404)
    a.title = title.strip()
    a.excerpt = excerpt.strip()
    a.content = sanitize_html(content)
    a.reading_time = reading_time(a.content)
    a.category_id = category_id
    was_pub = a.is_published
    a.is_published = is_published
    if is_published and not a.published_at:
        a.published_at = datetime.now(timezone.utc)
    a.meta_title = meta_title or None
    a.meta_description = meta_description or None
    a.meta_keywords = meta_keywords or None
    a.canonical_url = canonical_url or None
    a.schema_type = schema_type or "Article"
    a.faq_json = faq_json or None
    if cover and cover.filename:
        a.cover_image = await save_upload(cover, "articles", images_only=True)
    # reset tags
    a.tags.clear()
    for tname in [t.strip() for t in tags.split(",") if t.strip()]:
        ts = slugify(tname)
        ex = (await db.execute(select(Tag).where(Tag.slug == ts))).scalar_one_or_none()
        if not ex:
            ex = Tag(name=tname, slug=ts)
            db.add(ex)
            await db.flush()
        a.tags.append(ex)
    await db.commit()
    if a.is_published and not was_pub:
        url = settings.APP_URL + f"/blog/{a.slug}"
        asyncio.create_task(ping_search_engines(url))
        asyncio.create_task(google_indexing_request(url))
    return RedirectResponse("/admin/articles", status_code=303)


@router.post("/articles/{aid}/delete")
async def article_delete(aid: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_admin)):
    a = await db.get(Article, aid)
    if a:
        await db.delete(a)
        await db.commit()
    return RedirectResponse("/admin/articles", status_code=303)


# ============ Projects (مبسط CRUD) ============
@router.get("/projects")
async def projects_list(request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    items = (await db.execute(select(Project).order_by(Project.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("admin/projects_list.html", {
        "request": request, "items": items, "user": user, "active": "projects",
    })


@router.get("/projects/new")
@router.get("/projects/{pid}/edit")
async def project_form(request: Request, pid: int | None = None,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    p = await db.get(Project, pid) if pid else None
    return templates.TemplateResponse("admin/project_form.html", {
        "request": request, "p": p, "user": user, "active": "projects",
    })


@router.post("/projects/save")
async def project_save(pid: int = Form(0), title: str = Form(...),
                        short_description: str = Form(...), description: str = Form(...),
                        github_url: str = Form(""), live_url: str = Form(""),
                        video_url: str = Form(""),
                        technologies: str = Form(""), tags: str = Form(""),
                        featured: bool = Form(False), is_published: bool = Form(False),
                        cover: UploadFile | None = File(None),
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    p = await db.get(Project, pid) if pid else Project(slug=slugify(title))
    p.title = title.strip()
    p.short_description = short_description.strip()
    p.description = sanitize_html(description)
    p.github_url = github_url or None
    p.live_url = live_url or None
    p.video_url = video_url or None
    p.technologies = [t.strip() for t in technologies.split(",") if t.strip()]
    p.tags = [t.strip() for t in tags.split(",") if t.strip()]
    p.featured = featured
    p.is_published = is_published
    if not p.id:
        p.slug = slugify(title)
    if cover and cover.filename:
        p.cover_image = await save_upload(cover, "projects", images_only=True)
    if not pid:
        db.add(p)
    await db.commit()
    if p.is_published:
        asyncio.create_task(ping_search_engines(settings.APP_URL + f"/projects/{p.slug}"))
    return RedirectResponse("/admin/projects", status_code=303)


@router.post("/projects/{pid}/delete")
async def project_delete(pid: int, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_admin)):
    p = await db.get(Project, pid)
    if p:
        await db.delete(p); await db.commit()
    return RedirectResponse("/admin/projects", status_code=303)


# ============ Services ============
@router.get("/services")
async def services_admin(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_admin)):
    items = (await db.execute(select(Service).order_by(Service.sort_order))).scalars().all()
    return templates.TemplateResponse("admin/services_list.html", {
        "request": request, "items": items, "user": user, "active": "services",
    })


@router.get("/services/new")
@router.get("/services/{sid}/edit")
async def service_form(request: Request, sid: int | None = None,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    s = await db.get(Service, sid) if sid else None
    return templates.TemplateResponse("admin/service_form.html", {
        "request": request, "s": s, "user": user, "active": "services",
    })


@router.post("/services/save")
async def service_save(sid: int = Form(0), title: str = Form(...),
                        short_description: str = Form(...), description: str = Form(...),
                        icon: str = Form(""), features: str = Form(""),
                        pricing_json: str = Form("[]"), cta_text: str = Form("اطلب الآن"),
                        cta_url: str = Form("/contact"),
                        is_published: bool = Form(True), sort_order: int = Form(0),
                        cover: UploadFile | None = File(None),
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    s = await db.get(Service, sid) if sid else Service(slug=slugify(title))
    s.title = title.strip()
    s.short_description = short_description.strip()
    s.description = sanitize_html(description)
    s.icon = icon or None
    s.features = [f.strip() for f in features.split("\n") if f.strip()]
    try:
        s.pricing = json.loads(pricing_json or "[]")
    except Exception:
        s.pricing = []
    s.cta_text = cta_text
    s.cta_url = cta_url
    s.is_published = is_published
    s.sort_order = sort_order
    if not s.id:
        s.slug = slugify(title)
    if cover and cover.filename:
        s.cover_image = await save_upload(cover, "services", images_only=True)
    if not sid:
        db.add(s)
    await db.commit()
    return RedirectResponse("/admin/services", status_code=303)


@router.post("/services/{sid}/delete")
async def service_del(sid: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_admin)):
    s = await db.get(Service, sid)
    if s:
        await db.delete(s); await db.commit()
    return RedirectResponse("/admin/services", status_code=303)


# ============ Products ============
@router.get("/products")
async def products_admin(request: Request, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_admin)):
    items = (await db.execute(select(Product).order_by(Product.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("admin/products_list.html", {
        "request": request, "items": items, "user": user, "active": "products",
    })


@router.get("/products/new")
@router.get("/products/{pid}/edit")
async def product_form(request: Request, pid: int | None = None,
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    p = await db.get(Product, pid) if pid else None
    return templates.TemplateResponse("admin/product_form.html", {
        "request": request, "p": p, "user": user, "active": "products",
    })


@router.post("/products/save")
async def product_save(pid: int = Form(0), title: str = Form(...),
                        short_description: str = Form(...), description: str = Form(...),
                        price: float = Form(0), currency: str = Form("USD"),
                        is_published: bool = Form(False),
                        cover: UploadFile | None = File(None),
                        product_file: UploadFile | None = File(None),
                        db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin)):
    p = await db.get(Product, pid) if pid else Product(slug=slugify(title))
    p.title = title.strip()
    p.short_description = short_description.strip()
    p.description = sanitize_html(description)
    p.price = price
    p.currency = currency
    p.is_published = is_published
    if not p.id:
        p.slug = slugify(title)
    if cover and cover.filename:
        p.cover_image = await save_upload(cover, "products", images_only=True)
    if product_file and product_file.filename:
        p.file_path = await save_upload(product_file, "product_files", private=True)
    if not pid:
        db.add(p)
    await db.commit()
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{pid}/delete")
async def product_del(pid: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_admin)):
    p = await db.get(Product, pid)
    if p:
        await db.delete(p); await db.commit()
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/orders")
async def orders_list(request: Request, db: AsyncSession = Depends(get_db),
                       user: User = Depends(require_admin)):
    items = (await db.execute(select(Order).order_by(Order.created_at.desc()).limit(200))).scalars().all()
    return templates.TemplateResponse("admin/orders_list.html", {
        "request": request, "items": items, "user": user, "active": "products",
    })


# ============ Messages ============
@router.get("/messages")
async def messages_list(request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    items = (await db.execute(select(Message).order_by(Message.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("admin/messages_list.html", {
        "request": request, "items": items, "user": user, "active": "messages",
    })


@router.post("/messages/{mid}/toggle")
async def msg_toggle(mid: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_admin)):
    m = await db.get(Message, mid)
    if m:
        m.is_read = not m.is_read
        await db.commit()
    return RedirectResponse("/admin/messages", status_code=303)


# ============ Categories / Tags ============
@router.get("/categories")
async def cats_list(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_admin)):
    items = (await db.execute(select(Category))).scalars().all()
    return templates.TemplateResponse("admin/categories.html", {
        "request": request, "items": items, "user": user, "active": "categories",
    })


@router.post("/categories/add")
async def cat_add(name: str = Form(...), description: str = Form(""),
                   db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    db.add(Category(name=name.strip(), slug=slugify(name), description=description or None))
    await db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


# ============ SEO + Redirects + Re-indexing ============
@router.get("/seo")
async def seo_panel(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_admin)):
    redirects = (await db.execute(select(Redirect).order_by(Redirect.id.desc()))).scalars().all()
    custom_urls = (await db.execute(select(CustomSitemapURL).order_by(CustomSitemapURL.id))).scalars().all()
    return templates.TemplateResponse("admin/seo.html", {
        "request": request, "redirects": redirects, "custom_urls": custom_urls,
        "user": user, "active": "seo",
    })


@router.post("/seo/redirects/add")
async def add_redirect(source: str = Form(...), target: str = Form(...),
                        status_code: int = Form(301),
                        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    db.add(Redirect(source=source.strip(), target=target.strip(), status_code=status_code))
    await db.commit()
    return RedirectResponse("/admin/seo", status_code=303)


@router.post("/seo/redirects/{rid}/delete")
async def delete_redirect(rid: int, db: AsyncSession = Depends(get_db),
                           user: User = Depends(require_admin)):
    obj = await db.get(Redirect, rid)
    if obj:
        await db.delete(obj)
        await db.commit()
    return RedirectResponse("/admin/seo", status_code=303)


@router.post("/seo/sitemap/add")
async def add_sitemap_url(url: str = Form(...), changefreq: str = Form("weekly"),
                           priority: str = Form("0.5"), notes: str = Form(""),
                           db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    existing = (await db.execute(select(CustomSitemapURL).where(CustomSitemapURL.url == url.strip()))).scalar_one_or_none()
    if not existing:
        db.add(CustomSitemapURL(
            url=url.strip(), changefreq=changefreq, priority=priority,
            notes=notes.strip() or None,
        ))
        await db.commit()
    return RedirectResponse("/admin/seo", status_code=303)


@router.post("/seo/sitemap/{sid}/delete")
async def delete_sitemap_url(sid: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(require_admin)):
    obj = await db.get(CustomSitemapURL, sid)
    if obj:
        await db.delete(obj)
        await db.commit()
    return RedirectResponse("/admin/seo", status_code=303)


@router.post("/seo/reindex")
async def reindex_all(db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    asyncio.create_task(ping_search_engines(settings.APP_URL + "/sitemap.xml"))
    return RedirectResponse("/admin/seo", status_code=303)


# ============ Analytics ============
@router.get("/analytics")
async def analytics(request: Request, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_admin)):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    by_day = (await db.execute(
        select(func.date_trunc('day', PageView.created_at).label("d"), func.count())
        .where(PageView.created_at >= since)
        .group_by("d").order_by("d")
    )).all()
    by_device = (await db.execute(
        select(PageView.device, func.count()).where(PageView.created_at >= since)
        .group_by(PageView.device)
    )).all()
    referrers = (await db.execute(
        select(PageView.referrer, func.count().label("c")).where(PageView.created_at >= since,
                                                                  PageView.referrer.isnot(None))
        .group_by(PageView.referrer).order_by(desc("c")).limit(10)
    )).all()
    top = (await db.execute(
        select(PageView.path, func.count().label("c")).where(PageView.created_at >= since)
        .group_by(PageView.path).order_by(desc("c")).limit(20)
    )).all()
    return templates.TemplateResponse("admin/analytics.html", {
        "request": request, "by_day": by_day, "by_device": by_device,
        "referrers": referrers, "top": top, "user": user, "active": "analytics",
    })


# ============ Users ============
@router.get("/users")
async def users_list(request: Request, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_admin)):
    items = (await db.execute(select(User))).scalars().all()
    return templates.TemplateResponse("admin/users_list.html", {
        "request": request, "items": items, "user": user, "active": "users",
    })


# ============ Settings ============
@router.get("/settings")
async def settings_page(request: Request, db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_admin),
                        msg: str = "", msg_type: str = "success"):
    site_cfg = await load_site_settings(db)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": msg, "msg_type": msg_type,
    })


@router.post("/settings/site")
async def settings_site_save(
        request: Request,
        site_name: str = Form(...), site_author: str = Form(...),
        site_description: str = Form(...), site_url: str = Form(...),
        site_locale: str = Form("ar_SA"), default_og: str = Form(""),
        nav_logo: str = Form("G"),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    await save_site_settings(db, {
        "site_name": site_name.strip(),
        "site_author": site_author.strip(),
        "site_description": site_description.strip(),
        "site_url": site_url.strip(),
        "site_locale": site_locale.strip(),
        "default_og": default_og.strip(),
        "nav_logo": nav_logo.strip() or "G",
    })
    site_cfg = await load_site_settings(db)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم حفظ إعدادات الموقع بنجاح", "msg_type": "success",
    })


@router.post("/settings/home")
async def settings_home_save(
        request: Request,
        hero_badge: str = Form(""),
        hero_cta1_text: str = Form(""), hero_cta1_url: str = Form(""),
        hero_cta2_text: str = Form(""), hero_cta2_url: str = Form(""),
        cta_title: str = Form(""), cta_body: str = Form(""), cta_btn: str = Form(""),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    await save_site_settings(db, {
        "hero_badge": hero_badge.strip(),
        "hero_cta1_text": hero_cta1_text.strip(),
        "hero_cta1_url": hero_cta1_url.strip(),
        "hero_cta2_text": hero_cta2_text.strip(),
        "hero_cta2_url": hero_cta2_url.strip(),
        "cta_title": cta_title.strip(),
        "cta_body": cta_body.strip(),
        "cta_btn": cta_btn.strip(),
    })
    site_cfg = await load_site_settings(db)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم حفظ نصوص الصفحة الرئيسية بنجاح", "msg_type": "success",
    })


@router.post("/settings/about")
async def settings_about_save(
        request: Request,
        about_intro: str = Form(""),
        about_skills_title: str = Form(""), about_skills: str = Form(""),
        about_tech_title: str = Form(""), about_tech: str = Form(""),
        about_exp_title: str = Form(""), about_exp: str = Form(""),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    await save_site_settings(db, {
        "about_intro": about_intro.strip(),
        "about_skills_title": about_skills_title.strip(),
        "about_skills": about_skills.strip(),
        "about_tech_title": about_tech_title.strip(),
        "about_tech": about_tech.strip(),
        "about_exp_title": about_exp_title.strip(),
        "about_exp": about_exp.strip(),
    })
    site_cfg = await load_site_settings(db)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم حفظ صفحة «من أنا» بنجاح", "msg_type": "success",
    })


@router.post("/settings/social")
async def settings_social_save(
        request: Request,
        social_email: str = Form(""),
        social_whatsapp: str = Form(""), social_twitter: str = Form(""),
        social_linkedin: str = Form(""), social_github: str = Form(""),
        social_youtube: str = Form(""), footer_tagline: str = Form(""),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    await save_site_settings(db, {
        "social_email": social_email.strip(),
        "social_whatsapp": social_whatsapp.strip(),
        "social_twitter": social_twitter.strip(),
        "social_linkedin": social_linkedin.strip(),
        "social_github": social_github.strip(),
        "social_youtube": social_youtube.strip(),
        "footer_tagline": footer_tagline.strip(),
    })
    site_cfg = await load_site_settings(db)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم حفظ روابط التواصل الاجتماعي بنجاح", "msg_type": "success",
    })


@router.post("/settings/profile")
async def settings_profile_save(
        request: Request,
        full_name: str = Form(...), email: str = Form(...), bio: str = Form(""),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    from sqlalchemy import select as sa_select
    from app.models.user import User as UserModel
    conflict = (await db.execute(
        sa_select(UserModel).where(UserModel.email == email.strip(), UserModel.id != user.id)
    )).scalar_one_or_none()
    site_cfg = await load_site_settings(db)
    if conflict:
        return templates.TemplateResponse("admin/settings.html", {
            "request": request, "user": user, "active": "settings",
            "site_cfg": site_cfg, "msg": "✗ البريد الإلكتروني مستخدم بالفعل", "msg_type": "error",
        })
    user.full_name = full_name.strip()
    user.email = email.strip()
    user.bio = bio.strip() or None
    await db.commit()
    await db.refresh(user)
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم تحديث الملف الشخصي بنجاح", "msg_type": "success",
    })


@router.get("/categories/{cid}/edit")
async def cat_edit_form(cid: int, request: Request, db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_admin)):
    c = await db.get(Category, cid)
    if not c:
        raise HTTPException(404)
    return templates.TemplateResponse("admin/category_form.html", {
        "request": request, "c": c, "user": user, "active": "categories",
    })


@router.post("/categories/{cid}/edit")
async def cat_edit_save(cid: int, name: str = Form(...), description: str = Form(""),
                         db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    c = await db.get(Category, cid)
    if not c:
        raise HTTPException(404)
    c.name = name.strip()
    c.slug = slugify(name)
    c.description = description.strip() or None
    await db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{cid}/delete")
async def cat_delete(cid: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_admin)):
    c = await db.get(Category, cid)
    if c:
        await db.delete(c)
        await db.commit()
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/messages/{mid}/delete")
async def msg_delete(mid: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_admin)):
    m = await db.get(Message, mid)
    if m:
        await db.delete(m)
        await db.commit()
    return RedirectResponse("/admin/messages", status_code=303)


@router.post("/orders/{oid}/status")
async def order_status_update(oid: int, order_status: str = Form(...),
                               db: AsyncSession = Depends(get_db),
                               user: User = Depends(require_admin)):
    o = await db.get(Order, oid)
    if o:
        o.status = order_status
        await db.commit()
    return RedirectResponse("/admin/orders", status_code=303)


@router.post("/settings/password")
async def settings_password_save(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        confirm_password: str = Form(...),
        db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    site_cfg = await load_site_settings(db)

    def fail(msg):
        return templates.TemplateResponse("admin/settings.html", {
            "request": request, "user": user, "active": "settings",
            "site_cfg": site_cfg, "msg": msg, "msg_type": "error",
        })

    if not verify_password(current_password, user.hashed_password):
        return fail("✗ كلمة المرور الحالية غير صحيحة")
    if len(new_password) < 8:
        return fail("✗ كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل")
    if new_password != confirm_password:
        return fail("✗ كلمتا المرور الجديدتان غير متطابقتين")
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return templates.TemplateResponse("admin/settings.html", {
        "request": request, "user": user, "active": "settings",
        "site_cfg": site_cfg, "msg": "✓ تم تغيير كلمة المرور بنجاح", "msg_type": "success",
    })
