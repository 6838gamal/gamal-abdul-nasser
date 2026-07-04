"""روابط تحميل آمنة للمنتجات الرقمية."""
import asyncio
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.product import Product, Order
from app.core.config import settings

router = APIRouter(prefix="/products")

# ─── مساعدات Supabase ────────────────────────────────────────────────────────

_SUPABASE_SCHEME = "supabase://"


def _is_supabase_key(path: str) -> bool:
    """هل المسار مخزَّن كمفتاح Supabase Bucket (supabase://…)?"""
    return path.startswith(_SUPABASE_SCHEME)


def _is_remote_url(path: str) -> bool:
    """هل هو رابط عام مباشر (http/https)؟"""
    return path.startswith("http://") or path.startswith("https://")


def _make_signed_url(bucket_path: str, expires_in: int = 3600) -> str:
    """إنشاء رابط موقَّت من Supabase Storage لمسار الـ Bucket."""
    from app.services.uploads import _supabase
    try:
        sb = _supabase()
        result = sb.storage.from_(settings.SUPABASE_BUCKET).create_signed_url(
            bucket_path, expires_in
        )
        signed = result.get("signedURL") or result.get("signedUrl") or ""
        if not signed:
            raise ValueError(f"استجابة غير متوقعة من Supabase: {result}")
        return signed
    except Exception as exc:
        raise RuntimeError(f"فشل إنشاء رابط تحميل موقَّت: {exc}") from exc


# ─── المسارات ────────────────────────────────────────────────────────────────

@router.post("/{slug}/order")
async def create_order(
    slug: str,
    name: str = Form(...),
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    p = (
        await db.execute(
            select(Product).where(
                Product.slug == slug, Product.is_published == True
            )
        )
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(404)

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    order = Order(
        product_id=p.id,
        buyer_email=email,
        buyer_name=name,
        amount=p.price,
        currency=p.currency,
        status="paid" if float(p.price) == 0 else "pending",
        download_token=token,
        download_expires=expires,
    )
    db.add(order)
    await db.commit()
    return {
        "download_url": f"/products/download/{token}",
        "order_id": order.id,
        "status": order.status,
    }


@router.get("/download/{token}")
async def download(token: str, db: AsyncSession = Depends(get_db)):
    order = (
        await db.execute(select(Order).where(Order.download_token == token))
    ).scalar_one_or_none()

    if not order or order.status != "paid":
        raise HTTPException(403, "رابط غير صالح")
    if order.download_expires and order.download_expires < datetime.now(timezone.utc):
        raise HTTPException(410, "انتهت صلاحية الرابط")

    p = order.product
    if not p or not p.file_path:
        raise HTTPException(404)

    file_path: str = p.file_path

    # ─── ملف على Supabase (مفتاح bucket محمي) ───────────────────────
    if _is_supabase_key(file_path):
        bucket_path = file_path[len(_SUPABASE_SCHEME):]
        try:
            signed_url: str = await asyncio.to_thread(_make_signed_url, bucket_path)
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        # نحدّث العداد فقط بعد نجاح إنشاء الرابط الموقَّت
        p.download_count = (p.download_count or 0) + 1
        await db.commit()
        return RedirectResponse(signed_url, status_code=302)

    # ─── رابط عام مباشر (صور رُفعت قبل التعديل) ────────────────────
    if _is_remote_url(file_path):
        p.download_count = (p.download_count or 0) + 1
        await db.commit()
        return RedirectResponse(file_path, status_code=302)

    # ─── ملف محلي (احتياطي للبيانات القديمة) ───────────────────────
    local_file = Path(file_path.lstrip("/"))
    if not local_file.exists():
        raise HTTPException(404, "الملف غير موجود")
    p.download_count = (p.download_count or 0) + 1
    await db.commit()
    return FileResponse(local_file, filename=local_file.name)
