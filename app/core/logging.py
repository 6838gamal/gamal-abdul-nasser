"""تهيئة سجلات النظام."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    """
    تهيئة السجلات.

    - يوجّه السجلات إلى stderr (غير مُخزَّن في Docker/Render).
    - اختياريًا يكتب إلى ملف إذا كان LOG_TO_FILE=1.
    - آمن ضد إعادة التهيئة (force=True).
    - مستوى uvicorn.access قابل للضبط عبر UVICORN_ACCESS_LEVEL.
    """

    # ── مستوى السجل ──────────────────────────────────────────
    numeric_level = getattr(logging, str(level).upper(), logging.INFO)

    # ── التنسيق ──────────────────────────────────────────────
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )

    # ── تجهيز handlers ───────────────────────────────────────
    handlers: list[logging.Handler] = []

    # 1) stderr — يظهر فوراً في كل البيئات
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(numeric_level)
    handlers.append(sh)

    # 2) ملف اختياري (معطّل افتراضياً في الإنتاج)
    if os.environ.get("LOG_TO_FILE", "0") == "1":
        try:
            Path("logs").mkdir(exist_ok=True)
            fh = RotatingFileHandler(
                "logs/app.log",
                maxBytes=5_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            fh.setLevel(numeric_level)
            handlers.append(fh)
        except Exception as exc:
            print(
                f"[setup_logging] WARN: could not set up file handler: {exc}",
                file=sys.stderr,
                flush=True,
            )

    # ── تطبيق الإعدادات على الـ root logger ──────────────────
    # root.level = DEBUG ليسمح لكل المستويات بالوصول إلى الـ handlers
    # كل handler له مستواه الخاص (sh.setLevel).
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
        force=True,
    )

    # ── تخفيف ضجيج مكتبات الطرف الثالث ──────────────────────
    # uvicorn.access: يمكن ضبطه عبر env (INFO في التطوير، WARNING في الإنتاج)
    access_level_name = os.environ.get("UVICORN_ACCESS_LEVEL", "WARNING").upper()
    access_level = getattr(logging, access_level_name, logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(access_level)

    # باقي المكتبات: WARNING دائماً
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # ── سطر تأكيد ────────────────────────────────────────────
    logging.getLogger("app").info(
        "setup_logging: level=%s, uvicorn.access=%s, handlers=%s",
        logging.getLevelName(numeric_level),
        logging.getLevelName(access_level),
        [type(h).__name__ for h in handlers],
    )
