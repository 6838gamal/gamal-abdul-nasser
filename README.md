# منصة جمال عبد الناصر — FastAPI Production Ready

منصة شخصية احترافية متكاملة (مشاريع / خدمات / منتجات رقمية / مقالات) مع لوحة تحكم مدير، SEO متقدم، Google News، Google Discover، AI Search، Analytics، أمان كامل، وDocker جاهز للنشر.

## المكدّس
FastAPI · Jinja2 · PostgreSQL · SQLAlchemy 2 (Async) · Alembic · HTMX · Alpine.js · Tailwind CSS · Docker · Nginx · Redis · slowapi · bleach · Pillow

## الهيكل
```
project/
├── app/
│   ├── main.py                 # نقطة الدخول
│   ├── core/                   # الإعدادات + الأمان + السجلات
│   ├── database/               # SQLAlchemy async engine
│   ├── models/                 # نماذج (User, Article, Project, Service, Product, Order, Message, PageView, Redirect)
│   ├── schemas/                # Pydantic
│   ├── routes/                 # المسارات العامة + SEO + Auth + Downloads
│   ├── admin/                  # لوحة تحكم المدير الكاملة
│   ├── services/               # auth, uploads
│   ├── middleware/             # SecurityHeaders, Analytics, Redirects
│   ├── seo/                    # meta + sitemap + indexing
│   ├── utils/                  # text, templates
│   ├── templates/              # Jinja2 (public + admin + partials)
│   └── static/                 # css/js/images
├── uploads/  logs/  alembic/
├── docker/  nginx/
├── Dockerfile  docker-compose.yml  requirements.txt  .env.example
```

## التشغيل السريع (Docker)
```bash
cp .env.example .env          # عدّل القيم (SECRET_KEY, ADMIN_PASSWORD, APP_URL ...)
docker compose up -d --build
# لوحة التحكم:
#   http://localhost/admin/login
#   البريد:        قيمة ADMIN_EMAIL في .env
#   كلمة المرور:    قيمة ADMIN_PASSWORD في .env
```
الجداول تُنشأ تلقائياً عند الإقلاع. لتشغيل Alembic لاحقاً:
```bash
docker compose exec app alembic revision --autogenerate -m "msg"
docker compose exec app alembic upgrade head
```

## الميزات
### الواجهة العامة
- صفحة رئيسية أنيقة (Hero · خدمات · مشاريع مميزة · أحدث المقالات · منتجات · CTA)
- صفحات: من أنا، المشاريع (بحث/فلترة/Tags + صفحة لكل مشروع)، الخدمات (Landing + باقات)، المنتجات الرقمية (طلب + تحميل آمن)، المدونة (تصنيفات/وسوم/بحث + صفحة لكل مقال)، تواصل (HTMX)
- تصميم Noir & Gold فاخر، RTL، Tajawal/Cairo، Responsive، animations عبر Alpine

### لوحة تحكم المدير
- Dashboard (إحصائيات + أعلى الصفحات)
- CRUD: مقالات / مشاريع / خدمات / منتجات / تصنيفات
- محرر مقالات + جدولة نشر + Drafts + رفع غلاف
- تبويب SEO لكل مقال: Meta Title/Description/Keywords/Canonical/OG Image/Schema Type/FAQ JSON
- إدارة الطلبات والرسائل والمستخدمين
- لوحة SEO: Redirects + إعادة فهرسة فورية
- Analytics: زيارات يومية، أجهزة، مصادر، أعلى الصفحات

### SEO متقدم
- Meta Tags ديناميكية لكل صفحة + OpenGraph + Twitter Cards
- JSON-LD: Person / Article / Product / FAQPage / BreadcrumbList
- `/sitemap.xml` ديناميكي (يشمل صور Schema)
- `/news-sitemap.xml` لـ Google News (آخر 48 ساعة)
- `/rss.xml` خلاصة المقالات
- `/robots.txt` و `/llms.txt` (AI-friendly)
- Canonical URLs + max-image-preview:large لـ Google Discover
- نظام Redirects من قاعدة البيانات
- Google Indexing API (إذا أضفت `GOOGLE_INDEXING_KEY_FILE`)
- إشعار تلقائي لمحركات البحث عند نشر مقال/مشروع

### الأمان
- JWT في HttpOnly Cookie + bcrypt
- CSRF عبر SameSite cookies
- Rate Limiting (slowapi)
- Secure Headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)
- XSS Protection عبر `bleach.clean` على كل HTML من المستخدم
- SQL Injection-safe عبر SQLAlchemy ORM
- روابط تحميل موقّعة بصلاحية محدودة
- Upload validation (نوع MIME + حجم + إعادة معالجة الصور بـ Pillow)
- Session آمنة + Hashing لعنوان IP في Analytics

### الأداء
- GZip compression (Nginx + middleware)
- Static caching 30 يوم
- Lazy loading للصور
- Image optimization تلقائي
- Async DB + connection pooling
- Gunicorn + UvicornWorker (4 workers)

## بيئة الإنتاج
1. عدّل `.env`: `APP_URL`, `SECRET_KEY` (`openssl rand -hex 32`), `ADMIN_PASSWORD`, `DATABASE_URL`.
2. اربط الدومين على Nginx + أضف SSL (Let's Encrypt / Certbot).
3. أضف `GOOGLE_INDEXING_KEY_FILE` لتفعيل الفهرسة الفورية.
4. اربط Google Search Console + Bing Webmaster على `/sitemap.xml`.
5. سجّل الموقع في Google News Publisher Center.

تم بحمد الله ✨
