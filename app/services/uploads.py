"""خدمة رفع الملفات الآمنة + الصور."""
import secrets, mimetypes
from pathlib import Path
from fastapi import UploadFile, HTTPException
from PIL import Image
from app.core.config import settings


ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
ALLOWED_FILE = ALLOWED_IMAGE | {"application/pdf", "application/zip",
                                 "application/x-zip-compressed",
                                 "application/octet-stream", "text/plain"}


async def save_upload(file: UploadFile, subdir: str = "general", *, images_only=False) -> str:
    ct = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    allowed = ALLOWED_IMAGE if images_only else ALLOWED_FILE
    if ct not in allowed:
        raise HTTPException(400, f"نوع ملف غير مدعوم: {ct}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "حجم الملف كبير جداً")
    ext = Path(file.filename or "").suffix.lower() or ".bin"
    name = f"{secrets.token_hex(12)}{ext}"
    target_dir = Path(settings.UPLOAD_DIR) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    path.write_bytes(data)
    # تحسين الصور
    if ct in ALLOWED_IMAGE and ct != "image/svg+xml":
        try:
            img = Image.open(path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB") if ct == "image/jpeg" else img
            img.thumbnail((1920, 1920))
            img.save(path, optimize=True, quality=85)
        except Exception:
            pass
    return f"/uploads/{subdir}/{name}"
