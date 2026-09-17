# app/services/summarizer.py

"""
تلخيص المحادثة — Conversation Summarizer

يُستدعى كل N رسائل لتحديث lead.summary.

التحسينات:
- تتبّع آخر عدد رسائل تم تلخيصه (last_summarized_count)
- تمرير الملخص السابق كسياق لتحديثه بدلاً من إعادة توليده
- استخدام llm_client الموحّد
- رفع maxOutputTokens إلى 500
"""

import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.message import Message
from app.services.llm_client import get_client

log = logging.getLogger("app")

SUMMARY_INTERVAL = 20
RECENT_MESSAGES_LIMIT = 40
MAX_SUMMARY_LENGTH = 2000
MIN_SUMMARY_LENGTH = 20


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def format_messages(messages: List[Message]) -> str:
    """
    تنسيق الرسائل إلى نص للتلخيص.
    """
    lines = []
    for m in messages:
        role = m.role
        content = (m.content or "")[:500]
        if content:
            lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


def _build_prompt(
    previous_summary: str,
    messages_text: str,
) -> str:
    """
    بناء prompt للتلخيص، مع مراعاة الملخص السابق إن وُجد.
    """
    if previous_summary:
        return (
            "لديك ملخص سابق لمحادثة بين زائر ووكيل مبيعات.\n"
            "حدّث هذا الملخص بناءً على الرسائل الجديدة، "
            "مع الحفاظ على المعلومات المهمة السابقة.\n\n"
            f"الملخص السابق:\n{previous_summary}\n\n"
            "الرسائل الجديدة:\n"
            f"{messages_text}\n\n"
            "اكتب الملخص المحدّث في 4 أسطر بالعربية. "
            "ركّز على: المشكلة، المشروع، الميزانية، الجدول، "
            "الحالة الحالية، وأي معلومات تواصل."
        )

    return (
        "لخّص المحادثة التالية بين زائر ووكيل مبيعات في 4 أسطر "
        "بالعربية. ركز على: المشكلة، المشروع، الميزانية، الجدول، "
        "الحالة الحالية، وأي معلومات تواصل.\n\n"
        f"{messages_text}"
    )


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════


async def maybe_summarize(
    db: AsyncSession,
    lead: Lead,
    messages: List[Message],
) -> None:
    """
    لخّص المحادثة إذا تجاوزت العتبة منذ آخر تلخيص.
    """

    # عدد الرسائل الحالي
    total = len(messages)

    if total < SUMMARY_INTERVAL:
        return

    # آخر عدد تم تلخيصه (افتراضي 0 إن لم يكن الحقل موجوداً)
    last_count = int(getattr(lead, "last_summarized_count", 0) or 0)

    # إذا لم نصل للعتبة بعد
    if total - last_count < SUMMARY_INTERVAL:
        return

    # آخر N رسالة فقط (لتفادي prompt ضخم)
    recent = messages[-RECENT_MESSAGES_LIMIT:]

    messages_text = format_messages(recent)

    if not messages_text.strip():
        return

    previous_summary = (getattr(lead, "summary", "") or "").strip()

    prompt = _build_prompt(previous_summary, messages_text)

    client = get_client()

    try:
        text_result = await client.generate(
            prompt,
            temperature=0.3,
            max_output_tokens=500,
        )

        if not text_result:
            log.warning(
                "Summarization returned empty for lead=%s",
                lead.id,
            )
            return

        cleaned = text_result.strip()[:MAX_SUMMARY_LENGTH]

        if len(cleaned) < MIN_SUMMARY_LENGTH:
            log.warning(
                "Summarization too short for lead=%s (%d chars)",
                lead.id,
                len(cleaned),
            )
            return

        lead.summary = cleaned

        # تحديث العدّاد لتجنّب التلخيص المتكرر
        try:
            lead.last_summarized_count = total
        except AttributeError:
            # الحقل غير موجود في الموديل — نتجاهل بصمت
            pass

        await db.commit()

        log.info(
            "Summary updated for lead=%s (messages=%d)",
            lead.id,
            total,
        )

    except Exception as e:
        log.warning("Summarization failed for lead=%s: %s", lead.id, e)
        try:
            await db.rollback()
        except Exception:
            pass
