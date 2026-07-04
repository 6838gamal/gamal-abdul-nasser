"""خدمة رفع الملفات — Supabase Storage."""
import secrets
import mimetypes
import io
import asyncio
from pathlib import Path
from functools import lru_cache

from fastapi import UploadFile, HTTPException
from PIL import Image
from supabase import create_client, Client

from app.core.config import settings


ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
ALLOWED_FILE = ALLOWED_IMAGE | {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "text/plain",
}

# ─── عميل Supabase ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _supabase() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
        raise RuntimeError("SUPABASE_URL و SUPABASE_SECRET_KEY غير مضبوطَين")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)


def _optimize_image(data: bytes, content_type: str) -> bytes:
    """تحسين الصورة في الذاكرة ثم إعادة البايتات المضغوطة."""
    try:
        buf = io.BytesIO(data)
        img = Image.open(buf)
        fmt = img.format or "JPEG"
        if content_type == "image/jpeg" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((1920, 1920))
        out = io.BytesIO()
        img.save(out, format=fmt, optimize=True, quality=85)
        return out.getvalue()
    except Exception:
        return data


def _upload_to_supabase(data: bytes, path_in_bucket: str, content_type: str) -> str:
    """رفع الملف إلى Supabase Storage.
    للصور:  يعيد الرابط العام مباشرةً.
    للملفات: يعيد مسار الـ bucket (بادئة 'supabase://') للتعامل معها لاحقاً بروابط موقَّتة.
    """
    try:
        sb = _supabase()
        bucket = settings.SUPABASE_BUCKET
        sb.storage.from_(bucket).upload(
            path=path_in_bucket,
            file=data,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        return sb.storage.from_(bucket).get_public_url(path_in_bucket)
    except Exception as exc:
        raise HTTPException(502, f"فشل رفع الملف إلى Supabase Storage: {exc}") from exc


def _upload_file_to_supabase(data: bytes, path_in_bucket: str, content_type: str) -> str:
    """رفع ملف غير صورة إلى Supabase وإعادة مفتاح الـ bucket (supabase://<path>).
    الملفات لا تُخزَّن كروابط عامة بل كمسارات خاصة لتوليد روابط موقَّتة عند التحميل.
    """
    try:
        sb = _supabase()
        bucket = settings.SUPABASE_BUCKET
        sb.storage.from_(bucket).upload(
            path=path_in_bucket,
            file=data,
            file_options={"content-type": content_type, "upsert": "false"},
        )
        # نعيد مسار Bucket بادئاً بـ "supabase://" للتمييز عن المسارات المحلية القديمة
        return f"supabase://{path_in_bucket}"
    except Exception as exc:
        raise HTTPException(502, f"فشل رفع الملف إلى Supabase Storage: {exc}") from exc


async def save_upload(
    file: UploadFile,
    subdir: str = "general",
    *,
    images_only: bool = False,
    private: bool = False,
) -> str:
    """التحقق من الملف ورفعه إلى Supabase Storage.

    - private=False (الافتراضي): الصور ترفع وتُعاد كرابط عام مباشر (https://…)
    - private=True: يُرفع الملف ويُعاد كمفتاح Bucket (supabase://…) بغض النظر عن نوعه،
      وعند التحميل يُولَّد له رابط موقَّت منتهي الصلاحية.
    """
    ct = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    allowed = ALLOWED_IMAGE if images_only else ALLOWED_FILE

    if ct not in allowed:
        raise HTTPException(400, f"نوع ملف غير مدعوم: {ct}")

    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "حجم الملف كبير جداً")

    ext = Path(file.filename or "").suffix.lower() or ".bin"
    name = f"{secrets.token_hex(12)}{ext}"
    path_in_bucket = f"{subdir}/{name}"

    if private:
        # ملفات خاصة (مثل ملفات المنتجات): تُخزَّن كمفتاح Bucket دائماً
        bucket_key: str = await asyncio.to_thread(
            _upload_file_to_supabase, data, path_in_bucket, ct
        )
        return bucket_key
    else:
        # ملفات عامة (صور الغلاف): تُحسَّن وتُرفع كرابط عام
        if ct in ALLOWED_IMAGE and ct != "image/svg+xml":
            data = _optimize_image(data, ct)
        public_url: str = await asyncio.to_thread(
            _upload_to_supabase, data, path_in_bucket, ct
        )
        return public_url
