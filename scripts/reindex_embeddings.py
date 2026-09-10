#!/usr/bin/env python
"""
Reindex — حساب embeddings لكل الإدخالات الناقصة.
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.session import AsyncSessionLocal
from app.services.embeddings import embed_all_knowledge


async def main():

    print("═" * 55)
    print(" 🧠 Reindexing embeddings")
    print("═" * 55)

    async with AsyncSessionLocal() as db:
        stats = await embed_all_knowledge(db)

    print(f"\n{'═' * 55}")
    print(f" Total:    {stats['total']}")
    print(f" Embedded: {stats['embedded']}")
    print(f" Failed:   {stats['failed']}")
    print(f"{'═' * 55}\n")


if __name__ == "__main__":
    asyncio.run(main())
