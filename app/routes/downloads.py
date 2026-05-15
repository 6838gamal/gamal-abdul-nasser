"""روابط تحميل آمنة للمنتجات الرقمية."""
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.models.product import Product, Order
from app.core.config import settings

router = APIRouter(prefix="/products")


@router.post("/{slug}/order")
async def create_order(slug: str, name: str = Form(...), email: str = Form(...),
                        db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where(Product.slug == slug,
                                                 Product.is_published == True))).scalar_one_or_none()
    if not p:
        raise HTTPException(404)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    order = Order(product_id=p.id, buyer_email=email, buyer_name=name,
                  amount=p.price, currency=p.currency,
                  status="paid" if float(p.price) == 0 else "pending",
                  download_token=token, download_expires=expires)
    db.add(order)
    await db.commit()
    return {"download_url": f"/products/download/{token}",
            "order_id": order.id, "status": order.status}


@router.get("/download/{token}")
async def download(token: str, db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(Order).where(Order.download_token == token))).scalar_one_or_none()
    if not order or order.status != "paid":
        raise HTTPException(403, "رابط غير صالح")
    if order.download_expires and order.download_expires < datetime.now(timezone.utc):
        raise HTTPException(410, "انتهت صلاحية الرابط")
    p = order.product
    if not p or not p.file_path:
        raise HTTPException(404)
    file = Path(p.file_path.lstrip("/"))
    if not file.exists():
        raise HTTPException(404)
    p.download_count = (p.download_count or 0) + 1
    await db.commit()
    return FileResponse(file, filename=file.name)
