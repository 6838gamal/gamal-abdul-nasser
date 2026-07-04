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


def _is_remote_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _make_signed_url(path_in_bucket: str, expires_in: int = 3600) -> str:
    """إنشاء رابط موقَّت من Supabase Storage."""
    from app.services.uploads import _supabase
    sb = _supabase()
    result = sb.storage.from_(settings.SUPABASE_BUCKET).create_signed_url(
        path_in_bucket, expires_in
    )
    return result["signedURL"]


def _extract_bucket_path(public_url: str) -> str:
    """استخراج مسار الملف داخل الـ bucket من الرابط العام."""
    # مثال: https://xxx.supabase.co/storage/v1/object/public/uploads/articles/abc.jpg
    # نريد: articles/abc.jpg
    marker = f"/object/public/{settings.SUPABASE_BUCKET}/"
    idx = public_url.find(marker)
    if idx != -1:
        return public_url[idx + len(marker):]
    # fallback: آخر جزء من المسار
    return public_url.split("/storage/v1/object/public/", 1)[-1]


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

    p.download_count = (p.download_count or 0) + 1
    await db.commit()

    # ─── ملف على Supabase Storage ────────────────────────────────────
    if _is_remote_url(p.file_path):
        bucket_path = _extract_bucket_path(p.file_path)
        signed_url: str = await asyncio.to_thread(_make_signed_url, bucket_path)
        return RedirectResponse(signed_url, status_code=302)

    # ─── ملف محلي (احتياطي) ─────────────────────────────────────────
    file = Path(p.file_path.lstrip("/"))
    if not file.exists():
        raise HTTPException(404)
    return FileResponse(file, filename=file.name)
