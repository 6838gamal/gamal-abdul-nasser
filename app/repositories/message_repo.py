# app/repositories/message_repo.py

"""
عمليات الرسائل — Message Repository
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message

log = logging.getLogger("app")


async def add_message(
    db: AsyncSession,
    lead_id: int,
    role: str,
    content: Optional[str] = None,
    *,
    tool_name: Optional[str] = None,
    tool_payload: Optional[Dict[str, Any]] = None,
    tool_result: Optional[Dict[str, Any]] = None,
) -> Message:
    """
    إضافة رسالة جديدة.
    """

    message = Message(
        lead_id=lead_id,
        role=role,
        content=content,
        tool_name=tool_name,
        tool_payload=(
            json.dumps(tool_payload, ensure_ascii=False)
            if tool_payload
            else None
        ),
        tool_result=(
            json.dumps(tool_result, ensure_ascii=False)
            if tool_result
            else None
        ),
    )

    db.add(message)
    await db.commit()
    await db.refresh(message)

    return message


async def get_recent_messages(
    db: AsyncSession,
    lead_id: int,
    limit: int = 20,
) -> List[Message]:
    """
    جلب آخر N رسالة للمحادثة.
    """

    result = await db.execute(
        select(Message)
        .where(Message.lead_id == lead_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )

    messages = list(result.scalars().all())
    messages.reverse()

    return messages


async def get_message_count(
    db: AsyncSession,
    lead_id: int,
) -> int:
    """
    عدد الرسائل في محادثة lead.
    """

    from sqlalchemy import func as sqlfunc

    result = await db.execute(
        select(sqlfunc.count(Message.id)).where(
            Message.lead_id == lead_id
        )
    )

    return int(result.scalar() or 0)
