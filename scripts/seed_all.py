#!/usr/bin/env python
"""
Seed — تحميل knowledge_entries من seed/*.json
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
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


async def seed_file(db, path: Path) -> tuple[int, int]:

    if not path.exists():
        print(f"  ⚠️  not found: {path.name}")
        return 0, 0

    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not isinstance(entries, list):
        print(f"  ✗ {path.name}: expected a JSON array")
        return 0, 0

    added = 0
    skipped = 0

    for entry in entries:

        if not isinstance(entry, dict):
            skipped += 1
            continue

        title = str(entry.get("title", "")).strip()
        content = str(entry.get("content", "")).strip()

        if not title or not content:
            skipped += 1
            continue

        existing = await db.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.title == title)
        )

        if existing.scalar_one_or_none():
            skipped += 1
            continue

        db.add(KnowledgeEntry(
            title=title,
            content=content,
            is_active=bool(entry.get("is_active", True)),
        ))
        added += 1

    await db.commit()
    return added, skipped


async def main():

    print("═" * 55)
    print(" 🌱 Seeding knowledge base")
    print("═" * 55)
    print(f" SEED_DIR: {SEED_DIR}")
    print(f" Exists:   {SEED_DIR.exists()}")

    total_added = 0
    total_skipped = 0

    async with AsyncSessionLocal() as db:
        for filename in SEED_FILES:
            path = SEED_DIR / filename
            print(f"\n→ {filename}")

            added, skipped = await seed_file(db, path)

            print(f"   ✓ added: {added}, skipped: {skipped}")
            total_added += added
            total_skipped += skipped

    print(f"\n{'═' * 55}")
    print(f" ✅ Total: {total_added} added, {total_skipped} skipped")
    print(f"{'═' * 55}\n")


if __name__ == "__main__":
    asyncio.run(main())
