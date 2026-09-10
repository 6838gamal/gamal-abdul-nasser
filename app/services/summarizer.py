# app/services/summarizer.py

"""
تلخيص المحادثة — Conversation Summarizer

يُستدعى كل N رسائل لتحديث lead.summary.
"""

import logging
from typing import List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lead import Lead
from app.models.message import Message

log = logging.getLogger("app")

SUMMARY_INTERVAL = 20
GEMINI_MODEL = "gemini-2.5-flash"

SUMMARIZE_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{GEMINI_MODEL}:generateContent"
)


def format_messages(messages: List[Message]) -> str:
    lines = []
    for m in messages:
        role = m.role
        content = (m.content or "")[:500]
        if content:
            lines.append(f"[{role}]: {content}")
    return "\n".join(lines)


async def maybe_summarize(
    db: AsyncSession,
    lead: Lead,
    messages: List[Message],
) -> None:
    """
    لخّص المحادثة إذا تجاوزت العتبة.
    """

    if len(messages) < SUMMARY_INTERVAL:
        return

    if len(messages) % SUMMARY_INTERVAL != 0:
        return

    if not settings.GEMINI_API_KEY:
        return

    recent = messages[-40:]

    prompt = (
        "لخّص المحادثة التالية بين زائر ووكيل مبيعات في 4 أسطر "
        "بالعربية. ركز على: المشكلة، المشروع، الميزانية، الجدول، "
        "الحالة الحالية، وأي معلومات تواصل.\n\n"
        + format_messages(recent)
    )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SUMMARIZE_URL,
                params={"key": settings.GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 300,
                    },
                },
            )

            response.raise_for_status()
            data = response.json()

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        if text:
            lead.summary = text.strip()[:2000]
            await db.commit()

            log.info("Summary updated for lead=%s", lead.id)

    except Exception as e:
        log.warning("Summarization failed: %s", e)
