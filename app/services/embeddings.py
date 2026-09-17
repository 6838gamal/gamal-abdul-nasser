# app/services/embeddings.py

"""
Embeddings Service — Google Gemini Embedding API.

يوفر:
- embed_text: نص واحد
- embed_batch: عدة نصوص
- embed_knowledge_entry: إدخال معرفة
- embed_all_knowledge: كل الإدخالات الناقصة
- embed_message: رسالة

يعتمد على llm_client.GeminiClient لتفادي التكرار،
ويستخدم task_type المناسب لتحسين دقة البحث.
"""

import logging
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeEntry
from app.models.message import Message
from app.services.llm_client import (
    EMBEDDING_DIM,
    get_client,
)

log = logging.getLogger("app")

BATCH_SIZE = 20

# أنواع المهام حسب Gemini API
TASK_DOCUMENT = "RETRIEVAL_DOCUMENT"
TASK_QUERY = "RETRIEVAL_QUERY"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _vector_to_pg(vector: List[float]) -> str:
    """تحويل list إلى صيغة pgvector."""
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


def _is_valid_vector(vec: Optional[List[float]]) -> bool:
    """التحقق من صحة الـ vector وأبعاده."""
    return bool(vec) and len(vec) == EMBEDDING_DIM


# ══════════════════════════════════════════════════════════════════════
# Core
# ══════════════════════════════════════════════════════════════════════


async def embed_text(
    text_input: str,
    *,
    task_type: str = TASK_DOCUMENT,
) -> Optional[List[float]]:
    """
    تحويل نص إلى embedding vector (768-dim).

    Args:
        text_input: النص المراد تحويله.
        task_type: نوع المهمة (RETRIEVAL_DOCUMENT أو RETRIEVAL_QUERY).

    Returns:
        list[float] بطول 768، أو None عند الفشل.
    """

    if not text_input or not text_input.strip():
        return None

    client = get_client()
    return await client.embed(text_input, task_type=task_type)


async def embed_batch(
    texts: List[str],
    *,
    task_type: str = TASK_DOCUMENT,
) -> List[Optional[List[float]]]:
    """
    تحويل عدة نصوص في طلب واحد.

    Returns:
        list بنفس الطول، بعض العناصر قد تكون None.
    """

    if not texts:
        return []

    client = get_client()
    return await client.embed_batch(texts, task_type=task_type)


# ══════════════════════════════════════════════════════════════════════
# Knowledge
# ══════════════════════════════════════════════════════════════════════


async def embed_knowledge_entry(
    db: AsyncSession,
    entry: KnowledgeEntry,
) -> bool:
    """
    حساب embedding لإدخال معرفة وحفظه في DB.

    Returns:
        True عند النجاح، False عند الفشل.
    """

    blob = f"{entry.title or ''}\n{entry.content or ''}".strip()

    if not blob:
        return False

    vector = await embed_text(blob, task_type=TASK_DOCUMENT)

    if not _is_valid_vector(vector):
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
        log.error(
            "Failed to save embedding for entry %s: %s",
            entry.id,
            e,
        )
        await db.rollback()
        return False


async def embed_all_knowledge(
    db: AsyncSession,
) -> dict:
    """
    حساب embeddings لكل الإدخالات التي ليس لها embedding.

    Returns:
        dict: {total, embedded, failed}
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

    log.info(
        "Embedding %d entries in batches of %d",
        len(rows),
        BATCH_SIZE,
    )

    embedded = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        texts = [
            f"{r[1] or ''}\n{r[2] or ''}".strip()
            for r in batch
        ]

        vectors = await embed_batch(texts, task_type=TASK_DOCUMENT)

        for row, vec in zip(batch, vectors):
            if not _is_valid_vector(vec):
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
                log.error(
                    "Failed to save embedding for %s: %s",
                    row[0],
                    e,
                )
                failed += 1

        await db.commit()

    log.info(
        "Embedded %d/%d (%d failed)",
        embedded,
        len(rows),
        failed,
    )

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

    Returns:
        True إذا كان موجوداً أو تم حفظه، False عند الفشل.
    """

    if not message.content or not message.content.strip():
        return False

    # تحقق إذا كان موجوداً
    existing = await db.execute(
        text("SELECT 1 FROM message_embeddings WHERE message_id = :id"),
        {"id": message.id},
    )

    if existing.scalar():
        return True

    vector = await embed_text(message.content, task_type=TASK_DOCUMENT)

    if not _is_valid_vector(vector):
        return False

    try:
        await db.execute(
            text("""
                INSERT INTO message_embeddings (message_id, embedding)
                VALUES (:mid, CAST(:vec AS vector))
                ON CONFLICT (message_id) DO NOTHING
            """),
            {"mid": message.id, "vec": _vector_to_pg(vector)},
        )
        await db.commit()
        return True

    except Exception as e:
        log.error(
            "Failed to save message embedding %s: %s",
            message.id,
            e,
        )
        await db.rollback()
        return False
