"""تهيئة سجلات النظام."""
import logging, sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = RotatingFileHandler("logs/app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
