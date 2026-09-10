# app/services/knowledge_search.py

"""
Knowledge Search — Semantic + Keyword Fallback.
"""

import logging
import re
from typing import Any, Dict, List

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEntry
from app.services.embeddings import embed_text

log = logging.getLogger("app")

MIN_SIMILARITY = 0.5


# ══════════════════════════════════════════════════════════════════════
# Keyword Fallback
# ══════════════════════════════════════════════════════════════════════


def _tokenize(text_input: str) -> List[str]:
    text_input = text_input.lower()
    tokens = re.findall(r"\w+", text_input, flags=re.UNICODE)
    return [t for t in tokens if len(t) > 1]


async def keyword_search(
    db: AsyncSession,
    query: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    بحث keyword-based (fallback).
    """

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    result = await db.execute(
        select(KnowledgeEntry).where(
            KnowledgeEntry.is_active == True  # noqa: E712
        )
    )

    entries = result.scalars().all()
    scored: List[tuple] = []

    for entry in entries:
        title = str(getattr(entry, "title", "") or "")
        content = str(getattr(entry, "content", "") or "")

        blob = f"{title} {content}".lower()
        blob_tokens = set(_tokenize(blob))

        if not blob_tokens:
            continue

        overlap = query_tokens & blob_tokens
        if not overlap:
            continue

        score = len(overlap)

        title_tokens = set(_tokenize(title.lower()))
        score += 2 * len(query_tokens & title_tokens)

        scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "title": str(getattr(e, "title", "") or ""),
            "content": str(getattr(e, "content", "") or "")[:2000],
            "score": float(s),
        }
        for s, e in scored[:limit]
    ]


# ══════════════════════════════════════════════════════════════════════
# Semantic Search
# ══════════════════════════════════════════════════════════════════════


async def semantic_search(
    db: AsyncSession,
    query: str,
    limit: int = 3,
    min_similarity: float = MIN_SIMILARITY,
) -> List[Dict[str, Any]]:
    """
    بحث semantic باستخدام pgvector.
    """

    if not query:
        return []

    vector = await embed_text(query)

    if not vector:
        log.info("Embedding failed, using keyword fallback")
        return await keyword_search(db, query, limit)

    vector_str = "[" + ",".join(str(float(v)) for v in vector) + "]"

    try:
        result = await db.execute(
            text("""
                SELECT
                    id,
                    title,
                    content,
                    1 - (embedding <=> CAST(:vec AS vector)) AS similarity
                FROM knowledge_entries
                WHERE is_active = true
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:vec AS vector)
                LIMIT :lim
            """),
            {"vec": vector_str, "lim": limit},
        )

        rows = result.fetchall()

        results: List[Dict[str, Any]] = []

        for row in rows:
            similarity = float(row[3] or 0)

            if similarity < min_similarity:
                continue

            results.append({
                "title": str(row[1] or ""),
                "content": str(row[2] or "")[:2000],
                "score": round(similarity, 3),
            })

        if not results:
            log.info(
                "No results above %.2f, using keyword fallback",
                min_similarity,
            )
            return await keyword_search(db, query, limit)

        return results

    except Exception as e:
        log.error("Semantic search failed: %s", e)
        return await keyword_search(db, query, limit)


# ══════════════════════════════════════════════════════════════════════
# Public
# ══════════════════════════════════════════════════════════════════════


async def search_knowledge(
    db: AsyncSession,
    query: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    الواجهة العامة.
    """

    if not query:
        return []

    return await semantic_search(db, query, limit)
