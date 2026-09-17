# app/services/agent.py

"""
Agent — المنسّق الرئيسي لمعالجة رسائل المستخدم.

التدفّق:
1. حفظ رسالة المستخدم
2. حساب embedding للرسالة (اختياري، غير حاجب)
3. بناء السياق (RAG)
4. استدعاء LLM
5. حفظ رد الوكيل
6. محاولة التلخيص (maybe_summarize)

الفصل يسمح بـ:
- اختبار كل خطوة بشكل مستقل
- إضافة/إزالة خطوات بسهولة
- إعادة الاستخدام في قنوات مختلفة (API, WebSocket, ...)
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.message import Message
from app.services.embeddings import embed_message
from app.services.llm_client import get_client
from app.services.rag import build_context, build_prompt
from app.services.summarizer import maybe_summarize

log = logging.getLogger("app")

# حدود
MAX_HISTORY = 50
MAX_REPLY_TOKENS = 800


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


async def _load_history(
    db: AsyncSession,
    lead_id: int,
    limit: int = MAX_HISTORY,
) -> list[Message]:
    """
    تحميل آخر N رسالة للمحادثة مرتّبة زمنياً.
    """

    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )

    rows = result.scalars().all()

    # نرجعها بترتيب تصاعدي (الأقدم أولاً)
    return list(reversed(rows))


async def _save_message(
    db: AsyncSession,
    lead_id: int,
    role: str,
    content: str,
) -> Message:
    """
    حفظ رسالة جديدة.
    """

    msg = Message(
        lead_id=lead_id,
        role=role,
        content=content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════


async def handle_message(
    db: AsyncSession,
    lead: Lead,
    user_message: str,
    *,
    system_prompt: Optional[str] = None,
    include_knowledge: bool = True,
) -> Optional[str]:
    """
    معالجة رسالة مستخدم كاملة.

    Returns:
        نص رد الوكيل، أو None عند الفشل.
    """

    if not user_message or not user_message.strip():
        log.warning("Empty user message for lead=%s", getattr(lead, "id", None))
        return None

    user_message = user_message.strip()
    lead_id = lead.id

    # 1. حفظ رسالة المستخدم
    try:
        user_msg = await _save_message(
            db, lead_id, role="user", content=user_message
        )
    except Exception as e:
        log.exception("Failed to save user message: %s", e)
        return None

    # 2. embedding للرسالة (غير حاجب — لا نُفشل العملية إن فشل)
    try:
        await embed_message(db, user_msg)
    except Exception as e:
        log.warning("Message embedding failed (non-fatal): %s", e)

    # 3. تحميل السياق
    try:
        history = await _load_history(db, lead_id)
    except Exception as e:
        log.exception("Failed to load history: %s", e)
        history = [user_msg]

    # 4. بناء السياق (RAG)
    try:
        context = await build_context(
            db,
            lead,
            history,
            query=user_message,
            include_knowledge=include_knowledge,
        )
    except Exception as e:
        log.warning("RAG context build failed: %s", e)
        context = ""

    prompt = build_prompt(
        context,
        user_message,
        system_prompt=system_prompt,
    )

    # 5. استدعاء LLM
    client = get_client()

    reply_text = await client.generate(
        prompt,
        temperature=0.4,
        max_output_tokens=MAX_REPLY_TOKENS,
    )

    if not reply_text:
        log.warning("LLM returned empty reply for lead=%s", lead_id)
        return None

    reply_text = reply_text.strip()

    # 6. حفظ رد الوكيل
    try:
        await _save_message(
            db, lead_id, role="assistant", content=reply_text
        )
    except Exception as e:
        log.exception("Failed to save assistant message: %s", e)
        # نُرجع الرد رغم فشل الحفظ
        return reply_text

    # 7. محاولة التلخيص (غير حاجب)
    try:
        # نُعيد تحميل القائمة لتشمل الرسالتين الجديدتين
        updated_history = await _load_history(db, lead_id)
        await maybe_summarize(db, lead, updated_history)
    except Exception as e:
        log.warning("Summarization step failed (non-fatal): %s", e)

    return reply_text
