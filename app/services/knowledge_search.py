# app/services/knowledge_search.py

"""
Knowledge Search — Semantic + Keyword Fallback.

- semantic_search: pgvector cosine similarity
- keyword_search:  fallback عند فشل semantic
- search_knowledge: الواجهة العامة

التحسينات:
- تطبيع النص العربي قبل tokenization
- استخدام RETRIEVAL_QUERY للاستعلامات
- حد أعلى لعدد الصفوف في keyword_search
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Set

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEntry
from app.services.embeddings import (
    TASK_QUERY,
    embed_text,
)

log = logging.getLogger("app")

MIN_SIMILARITY = 0.5
KEYWORD_SCAN_LIMIT = 2000


# ══════════════════════════════════════════════════════════════════════
# Text normalization (Arabic-aware)
# ══════════════════════════════════════════════════════════════════════

_ARABIC_DIACRITICS = re.compile(r"[\u064B-\u0652\u0670\u0640]")


def normalize_text(s: str) -> str:
    """
    تطبيع النص العربي:
    - إزالة التشكيل والتطويل
    - توحيد الهمزات
    - توحيد ة/ه و ى/ي
    - lowercase للحروف اللاتينية
    """
    if not s:
        return ""

    # Unicode normalization
    s = unicodedata.normalize("NFKC", s)

    # lowercase
    s = s.lower()

    # إزالة التشكيل
    s = _ARABIC_DIACRITICS.sub("", s)

    # توحيد الهمزات
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

    # توحيد التاء المربوطة والألف المقصورة
    s = s.replace("ة", "ه").replace("ى", "ي")

    return s


def _tokenize(text_input: str) -> List[str]:
    """
    تقسيم النص إلى tokens بعد التطبيع.
    """
    normalized = normalize_text(text_input)
    tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
    return [t for t in tokens if len(t) > 1]


# ══════════════════════════════════════════════════════════════════════
# Keyword Fallback
# ══════════════════════════════════════════════════════════════════════


async def keyword_search(
    db: AsyncSession,
    query: str,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    بحث keyword-based (fallback).
    """

    query_tokens: Set[str] = set(_tokenize(query))
    if not query_tokens:
        return []

    # حد أعلى لعدد الصفوف المسحوبة (لتفادي استهلاك الذاكرة)
    result = await db.execute(
        select(KnowledgeEntry)
        .where(KnowledgeEntry.is_active == True)  # noqa: E712
        .limit(KEYWORD_SCAN_LIMIT)
    )

    entries = result.scalars().all()
    scored: List[tuple] = []

    for entry in entries:
        title = str(getattr(entry, "title", "") or "")
        content = str(getattr(entry, "content", "") or "")

        blob = f"{title} {content}"
        blob_tokens = set(_tokenize(blob))

        if not blob_tokens:
            continue

        overlap = query_tokens & blob_tokens
        if not overlap:
            continue

        # score أساسي
        score = float(len(overlap))

        # تعزيز عند التطابق في العنوان
        title_tokens = set(_tokenize(title))
        if title_tokens:
            title_overlap = len(query_tokens & title_tokens)
            # تطبيع بطول العنوان لتفادي تحيّز العناوين الطويلة
            score += 2.0 * (title_overlap / max(len(title_tokens), 1))

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

    # نستخدم RETRIEVAL_QUERY لأن هذا استعلام بحث
    vector = await embed_text(query, task_type=TASK_QUERY)

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
