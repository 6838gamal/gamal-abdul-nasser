# app/services/notifications.py

"""
إشعارات المالك — Owner Notifications

حالياً: logging فقط.
لاحقاً: email / telegram / whatsapp.
"""

import logging
from typing import Optional

from app.models.lead import Lead

log = logging.getLogger("app.notifications")


async def notify_owner(
    lead: Lead,
    message: str,
    urgency: str = "medium",
) -> None:
    """
    إرسال إشعار للمالك.

    TODO: ربط مع Telegram/Email/WhatsApp.
    """

    log.warning(
        "🔔 OWNER NOTIFICATION [%s] | lead=%s | name=%s | contact=%s | score=%s | stage=%s | msg=%s",
        urgency.upper(),
        lead.id,
        lead.name or "?",
        lead.contact or "?",
        lead.score,
        lead.stage.value if lead.stage else "?",
        message,
    )

    # مثال على التنفيذ لاحقاً:
    # if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
    #     async with httpx.AsyncClient() as client:
    #         await client.post(
    #             f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
    #             json={
    #                 "chat_id": settings.TELEGRAM_CHAT_ID,
    #                 "text": f"🔔 {message}\n\nLead: {lead.id}\nScore: {lead.score}",
    #             },
    #         )
