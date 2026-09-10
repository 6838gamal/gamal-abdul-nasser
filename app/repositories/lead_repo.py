# app/repositories/lead_repo.py

"""
عمليات العميل المحتمل — Lead Repository
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStage
from app.models.visitor import Visitor

log = logging.getLogger("app")


# ══════════════════════════════════════════════════════════════════════
# Lead Scoring
# ══════════════════════════════════════════════════════════════════════

WEIGHTS = {
    "problem": 20,
    "desired_solution": 10,
    "project_type": 10,
    "budget": 15,
    "timeline": 10,
    "contact": 20,
    "company": 5,
    "name": 5,
}

STAGE_BONUS = {
    LeadStage.NEW: 0,
    LeadStage.QUALIFYING: 5,
    LeadStage.QUALIFIED: 10,
    LeadStage.CONTACT_REQUESTED: 15,
    LeadStage.READY_TO_BUY: 20,
    LeadStage.HANDED_OFF: 20,
    LeadStage.LOST: -30,
}


def compute_lead_score(lead: Lead) -> int:
    """
    حساب نقاط lead رقمياً (0-100) بدل التخمين من LLM.
    """

    score = 0

    for field, weight in WEIGHTS.items():
        if getattr(lead, field, None):
            score += weight

    score += STAGE_BONUS.get(lead.stage, 0)

    return max(0, min(score, 100))


def score_to_label(score: int) -> str:
    """تحويل النقاط إلى تصنيف مقروء."""

    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


# ══════════════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════════════


async def get_or_create_lead_for_visitor(
    db: AsyncSession,
    visitor: Visitor,
) -> Lead:
    """
    جلب lead الزائر أو إنشاء واحد جديد.
    حالياً: lead واحد لكل زائر.
    """

    result = await db.execute(
        select(Lead)
        .where(Lead.visitor_id == visitor.id)
        .order_by(Lead.id.desc())
        .limit(1)
    )

    lead = result.scalar_one_or_none()

    if lead is None:
        lead = Lead(
            visitor_id=visitor.id,
            stage=LeadStage.NEW,
            score=0,
        )
        db.add(lead)
        await db.commit()
        await db.refresh(lead)

        log.info("New lead created for visitor=%s", visitor.visitor_uid)

    return lead


async def get_lead_by_id(
    db: AsyncSession,
    lead_id: int,
) -> Optional[Lead]:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id)
    )
    return result.scalar_one_or_none()


async def save_lead_field(
    db: AsyncSession,
    lead: Lead,
    field: str,
    value: str,
) -> None:
    """
    حفظ حقل واحد في lead مع التحقق.
    """

    allowed = {
        "name",
        "company",
        "contact",
        "project_type",
        "problem",
        "desired_solution",
        "budget",
        "timeline",
    }

    if field not in allowed:
        raise ValueError(f"FIELD_NOT_ALLOWED: {field}")

    if value is None:
        return

    value = str(value).strip()[:1000]

    if not value:
        return

    setattr(lead, field, value)

    lead.score = compute_lead_score(lead)

    await db.commit()
    await db.refresh(lead)


async def update_lead_stage(
    db: AsyncSession,
    lead: Lead,
    stage: str,
    reason: Optional[str] = None,
) -> None:
    """
    تحديث مرحلة lead.
    """

    try:
        stage_enum = LeadStage(stage)
    except ValueError:
        raise ValueError(f"INVALID_STAGE: {stage}")

    lead.stage = stage_enum
    lead.score = compute_lead_score(lead)

    if reason:
        lead.handoff_reason = reason[:1000]

    await db.commit()
    await db.refresh(lead)
