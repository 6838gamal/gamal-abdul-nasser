#!/usr/bin/env python
"""
Sync Knowledge — مزامنة كاملة بين seed/*.json و DB.

يدعم:
- إضافة إدخالات جديدة
- تحديث الإدخالات المُعدَّلة
- تعطيل الإدخالات المحذوفة (soft delete)
- إعادة حساب embeddings للتغييرات

آمن للتشغيل المتكرر (idempotent).
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, text
from app.database.session import AsyncSessionLocal
from app.models.knowledge import KnowledgeEntry

SEED_DIR = PROJECT_ROOT / "seed"

SEED_FILES = [
    "services.json",
    "faqs.json",
    "case_studies.json",
    "glossary.json",
    "industries.json",
    "policies.json",
]


# ══════════════════════════════════════════════════════════════════════
# Hash للمحتوى (لكشف التغييرات)
# ══════════════════════════════════════════════════════════════════════


def content_hash(title: str, content: str) -> str:
    """
    hash من title + content.
    """
    blob = f"{title}\n---\n{content}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════
# Sync Logic
# ══════════════════════════════════════════════════════════════════════


async def sync_file(db, path: Path) -> Dict[str, int]:
    """
    مزامنة ملف واحد.

    يُرجع: {
        "added": int,
        "updated": int,
        "deactivated": int,
        "unchanged": int,
    }
    """

    stats = {
        "added": 0,
        "updated": 0,
        "deactivated": 0,
        "unchanged": 0,
    }

    if not path.exists():
        print(f"  ⚠️  not found: {path.name}")
        return stats

    with open(path, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  ✗ invalid JSON in {path.name}: {e}")
            return stats

    if not isinstance(entries, list):
        print(f"  ✗ {path.name}: expected array")
        return stats

    # ═══════════════════════════════════════════════
    # اجلب كل الإدخالات الحالية من DB
    # ═══════════════════════════════════════════════

    result = await db.execute(
        select(KnowledgeEntry)
    )
    existing_entries = result.scalars().all()

    # خريطة: title → entry
    existing_by_title: Dict[str, KnowledgeEntry] = {
        e.title: e for e in existing_entries
    }

    # ═══════════════════════════════════════════════
    # معالجة كل إدخال في JSON
    # ═══════════════════════════════════════════════

    json_titles = set()

    for raw in entries:

        if not isinstance(raw, dict):
            continue

        title = str(raw.get("title", "")).strip()
        content = str(raw.get("content", "")).strip()
        is_active = bool(raw.get("is_active", True))

        if not title or not content:
            continue

        json_titles.add(title)

        existing = existing_by_title.get(title)

        if existing is None:
            # ─── جديد ───
            db.add(KnowledgeEntry(
                title=title,
                content=content,
                is_active=is_active,
            ))
            stats["added"] += 1

        else:
            # ─── موجود: تحقق من التغييرات ───

            content_changed = (existing.content or "") != content
            active_changed = bool(existing.is_active) != is_active

            if content_changed:
                existing.content = content
                # إعادة حساب embedding
                existing.embedding = None
                stats["updated"] += 1

            if active_changed:
                existing.is_active = is_active
                if not active_changed and content_changed:
                    pass  # محسوب أعلاه
                elif active_changed and not content_changed:
                    stats["updated"] += 1

            if not content_changed and not active_changed:
                stats["unchanged"] += 1

    # ═══════════════════════════════════════════════
    # الإدخالات في DB لكن ليس في JSON → soft delete
    # ═══════════════════════════════════════════════

    for title, entry in existing_by_title.items():
        if title not in json_titles and entry.is_active:
            entry.is_active = False
            stats["deactivated"] += 1

    await db.commit()
    return stats


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════


async def main():

    print("═" * 60)
    print(" 🔄 Syncing knowledge base")
    print("═" * 60)
    print(f" SEED_DIR: {SEED_DIR}")

    grand = {
        "added": 0,
        "updated": 0,
        "deactivated": 0,
        "unchanged": 0,
    }

    async with AsyncSessionLocal() as db:
        for filename in SEED_FILES:
            path = SEED_DIR / filename
            print(f"\n→ {filename}")

            stats = await sync_file(db, path)

            print(
                f"   ✓ added={stats['added']} "
                f"updated={stats['updated']} "
                f"deactivated={stats['deactivated']} "
                f"unchanged={stats['unchanged']}"
            )

            for k in grand:
                grand[k] += stats[k]

    print(f"\n{'═' * 60}")
    print(f" 📊 Grand total:")
    print(f"    Added:        {grand['added']}")
    print(f"    Updated:      {grand['updated']}")
    print(f"    Deactivated:  {grand['deactivated']}")
    print(f"    Unchanged:    {grand['unchanged']}")
    print(f"{'═' * 60}\n")

    # ─── تذكير ───
    if grand["added"] > 0 or grand["updated"] > 0:
        print("⚠️  يوجد إدخالات جديدة/محدّثة تحتاج embeddings.")
        print("   شغّل: python scripts/reindex_embeddings.py")
        print()


if __name__ == "__main__":
    asyncio.run(main())
