# app/repositories/visitor_repo.py

"""
عمليات الزائر — Visitor Repository
"""

import hashlib
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visitor import Visitor

log = logging.getLogger("app")


def hash_ip(ip: str) -> str:
    """تجزئة IP للحفاظ على الخصوصية."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


async def get_or_create_visitor(
    db: AsyncSession,
    visitor_uid: str,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    locale: Optional[str] = None,
    referrer: Optional[str] = None,
) -> Visitor:
    """
    جلب الزائر أو إنشاؤه إذا لم يكن موجوداً.
    """

    if not visitor_uid or len(visitor_uid) < 8:
        raise ValueError("INVALID_VISITOR_UID")

    result = await db.execute(
        select(Visitor).where(Visitor.visitor_uid == visitor_uid)
    )

    visitor = result.scalar_one_or_none()

    if visitor is None:
        visitor = Visitor(
            visitor_uid=visitor_uid,
            ip_hash=hash_ip(ip or ""),
            user_agent=(user_agent or "")[:255] or None,
            locale=(locale or "")[:16] or None,
            referrer=(referrer or "")[:500] or None,
        )
        db.add(visitor)
        await db.commit()
        await db.refresh(visitor)

        log.info("New visitor created: %s", visitor_uid)

    return visitor
