# app/services/embeddings.py

"""
Embeddings Service — Google Gemini Embedding API.

يوفر:
- embed_text: نص واحد
- embed_batch: عدة نصوص
- embed_knowledge_entry: إدخال معرفة
- embed_message: رسالة
- embed_all_knowledge: كل الإدخالات الناقصة
"""

import logging
from typing import List, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import KnowledgeEntry
from app.models.message import Message

log = logging.getLogger("app")

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768
MAX_TEXT_LENGTH = 2048
BATCH_SIZE = 20

EMBEDDING_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{EMBEDDING_MODEL}:embedContent"
)

BATCH_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{EMBEDDING_MODEL}:batchEmbedContents"
)


# ══════════════════════════════════════════════════════════════════════
# Core
# ══════════════════════════════════════════════════════════════════════


def _vector_to_pg(vector: List[float]) -> str:
    """تحويل list إلى صيغة pgvector."""
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


async def embed_text(text_input: str) -> Optional[List[float]]:
    """
    تحويل نص إلى embedding vector (768-dim).
    """

    if not text_input or not text_input.strip():
        return None

    if not settings.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY not set")
        return None

    clean = text_input.strip()[:MAX_TEXT_LENGTH]

    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {"parts": [{"text": clean}]},
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                EMBEDDING_URL,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                log.error(
                    "Embedding API error %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None

            data = response.json()
            values = data.get("embedding", {}).get("values")

            if not values or len(values) != EMBEDDING_DIM:
                log.warning(
                    "Unexpected embedding dim: %s",
                    len(values) if values else 0,
                )
                return None

            return values

    except Exception as e:
        log.exception("embed_text failed: %s", e)
        return None


async def embed_batch(
    texts: List[str],
) -> List[Optional[List[float]]]:
    """
    تحويل عدة نصوص في طلب واحد.
    """

    if not texts:
        return []

    if not settings.GEMINI_API_KEY:
        return [None] * len(texts)

    clean_texts = [
        (t or "").strip()[:MAX_TEXT_LENGTH] or " "
        for t in texts
    ]

    requests_payload = [
        {
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": t}]},
        }
        for t in clean_texts
    ]

    payload = {"requests": requests_payload}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                BATCH_URL,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                log.error(
                    "Batch embedding error %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                return [None] * len(texts)

            data = response.json()
            embeddings = data.get("embeddings", [])

            if len(embeddings) != len(texts):
                log.warning(
                    "Batch size mismatch: got %d, expected %d",
                    len(embeddings),
                    len(texts),
                )
                return [None] * len(texts)

            return [
                e.get("values") if e else None
                for e in embeddings
            ]

    except Exception as e:
        log.exception("embed_batch failed: %s", e)
        return [None] * len(texts)


# ══════════════════════════════════════════════════════════════════════
# Knowledge
# ══════════════════════════════════════════════════════════════════════


async def embed_knowledge_entry(
    db: AsyncSession,
    entry: KnowledgeEntry,
) -> bool:
    """
    حساب embedding لإدخال معرفة وحفظه في DB.
    """

    blob = f"{entry.title or ''}\n{entry.content or ''}".strip()

    if not blob:
        return False

    vector = await embed_text(blob)

    if not vector:
        return False

    vector_str = _vector_to_pg(vector)

    try:
        await db.execute(
            text("""
                UPDATE knowledge_entries
                SET embedding = CAST(:vec AS vector)
                WHERE id = :id
            """),
            {"vec": vector_str, "id": entry.id},
        )
        await db.commit()
        return True

    except Exception as e:
        log.error("Failed to save embedding for entry %s: %s", entry.id, e)
        await db.rollback()
        return False


async def embed_all_knowledge(
    db: AsyncSession,
) -> dict:
    """
    حساب embeddings لكل الإدخالات التي ليس لها embedding.

    يُرجع dict: {total, embedded, failed}
    """

    result = await db.execute(
        text("""
            SELECT id, title, content
            FROM knowledge_entries
            WHERE is_active = true
              AND embedding IS NULL
            ORDER BY id
        """)
    )

    rows = result.fetchall()

    if not rows:
        return {"total": 0, "embedded": 0, "failed": 0}

    log.info("Embedding %d entries in batches of %d", len(rows), BATCH_SIZE)

    embedded = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        texts = [
            f"{r[1] or ''}\n{r[2] or ''}".strip()
            for r in batch
        ]

        vectors = await embed_batch(texts)

        for row, vec in zip(batch, vectors):
            if not vec:
                failed += 1
                continue

            try:
                await db.execute(
                    text("""
                        UPDATE knowledge_entries
                        SET embedding = CAST(:vec AS vector)
                        WHERE id = :id
                    """),
                    {"vec": _vector_to_pg(vec), "id": row[0]},
                )
                embedded += 1

            except Exception as e:
                log.error("Failed to save embedding for %s: %s", row[0], e)
                failed += 1

        await db.commit()

    log.info("Embedded %d/%d (%d failed)", embedded, len(rows), failed)

    return {
        "total": len(rows),
        "embedded": embedded,
        "failed": failed,
    }


# ══════════════════════════════════════════════════════════════════════
# Messages
# ══════════════════════════════════════════════════════════════════════


async def embed_message(
    db: AsyncSession,
    message: Message,
) -> bool:
    """
    حساب embedding لرسالة (إن لم يكن موجوداً).
    """

    if not message.content:
        return False

    # تحقق إذا كان موجوداً
    existing = await db.execute(
        text("SELECT 1 FROM message_embeddings WHERE message_id = :id"),
        {"id": message.id},
    )

    if existing.scalar():
        return True

    vector = await embed_text(message.content)

    if not vector:
        return False

    try:
        await db.execute(
            text("""
                INSERT INTO message_embeddings (message_id, embedding)
                VALUES (:mid, CAST(:vec AS vector))
            """),
            {"mid": message.id, "vec": _vector_to_pg(vector)},
        )
        await db.commit()
        return True

    except Exception as e:
        log.error("Failed to save message embedding %s: %s", message.id, e)
        await db.rollback()
        return False
