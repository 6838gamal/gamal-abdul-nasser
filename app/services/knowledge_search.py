# app/services/knowledge_search.py

"""
البحث في قاعدة المعرفة.

مرحلة أولى: keyword search بسيط.
مرحلة لاحقة: استبدل بـ pgvector + embeddings.
"""

import logging
import re
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEntry

log = logging.getLogger("app")


def tokenize(text: str) -> List[str]:
    """تقسيم بسيط للنص."""
    text = text.lower()
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    return [t for t in tokens if len(t) > 1]


async def search_knowledge(
    db: AsyncSession,
    query: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    بحث keyword-based في قاعدة المعرفة.

    يُستدعى من tool: search_knowledge.
    """

    if not query:
        return []

    query_tokens = set(tokenize(query))

    if not query_tokens:
        return []

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.is_active == True  # noqa: E712
        )
    )

    entries = result.scalars().all()

    scored: List[tuple[int, KnowledgeEntry]] = []

    for entry in entries:
        title = str(getattr(entry, "title", "") or "")
        content = str(getattr(entry, "content", "") or "")

        blob = f"{title} {content}".lower()
        blob_tokens = set(tokenize(blob))

        if not blob_tokens:
            continue

        overlap = query_tokens & blob_tokens

        if not overlap:
            continue

        score = len(overlap)

        # مكافأة إذا ظهر المصطلح في العنوان
        title_tokens = set(tokenize(title.lower()))
        score += 2 * len(query_tokens & title_tokens)

        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    results: List[Dict[str, Any]] = []

    for score, entry in scored[:limit]:
        results.append({
            "title": str(getattr(entry, "title", "") or ""),
            "content": str(getattr(entry, "content", "") or "")[:2000],
            "score": score,
        })

    return results
