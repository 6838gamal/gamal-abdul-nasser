# app/repositories/lead_repo.py

"""
عمليات العميل المحتمل — Lead Repository
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStage
from app.models.visitor import Visitor

log = logging.getLogger("app")


# ══════════════════════════════════════════════════════════════════════
# حدود الحقول (تطابق أنواع الأعمدة في الموديل)
# ══════════════════════════════════════════════════════════════════════

FIELD_MAX_LENGTH = {
    "name": 120,
    "company": 120,
    "contact": 255,
    "project_type": 120,
    "problem": 4000,          # TEXT — حد عملي معقول
    "desired_solution": 4000, # TEXT
    "budget": 120,
    "timeline": 120,
}

ALLOWED_FIELDS = set(FIELD_MAX_LENGTH.keys())


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


def _normalize_stage(stage) -> LeadStage:
    """
    يحوّل أي تمثيل للمرحلة إلى عضو LeadStage.

    يقبل:
    - عضو LeadStage مباشرة
    - نص بقيمة العضو: "new", "qualifying", ...
    - نص باسم العضو: "NEW", "QUALIFYING", ...
    """
    if isinstance(stage, LeadStage):
        return stage

    if isinstance(stage, str):
        s = stage.strip()
        # جرّب القيمة أولاً (new)
        try:
            return LeadStage(s)
        except ValueError:
            pass
        # جرّب الاسم بأحرف كبيرة (NEW)
        try:
            return LeadStage[s.upper()]
        except KeyError:
            pass
        # جرّب الاسم كما هو (New)
        try:
            return LeadStage[s]
        except KeyError:
            pass

    raise ValueError(f"INVALID_STAGE: {stage!r}")


def compute_lead_score(lead: Lead) -> int:
    """
    حساب نقاط lead رقمياً (0-100) بدل التخمين من LLM.
    """

    score = 0

    for field, weight in WEIGHTS.items():
        if getattr(lead, field, None):
            score += weight

    # تطبيع المرحلة قبل البحث في STAGE_BONUS
    try:
        stage = _normalize_stage(lead.stage) if lead.stage is not None else LeadStage.NEW
    except ValueError:
        stage = LeadStage.NEW

    score += STAGE_BONUS.get(stage, 0)

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

    ملاحظة: لتفادي race condition، يُنصح بإضافة
    UniqueConstraint("visitor_id") في الموديل. بدون ذلك،
    قد يُنشأ أكثر من lead لنفس الزائر عند الطلبات المتزامنة.
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
        try:
            await db.commit()
        except IntegrityError:
            # ربما أنشأ طلب متزامن الـ lead للتو — أعد المحاولة
            await db.rollback()
            result = await db.execute(
                select(Lead)
                .where(Lead.visitor_id == visitor.id)
                .order_by(Lead.id.desc())
                .limit(1)
            )
            lead = result.scalar_one_or_none()
            if lead is None:
                raise
        else:
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
    حفظ حقل واحد في lead مع التحقق من الطول حسب نوع العمود.
    """

    if field not in ALLOWED_FIELDS:
        raise ValueError(f"FIELD_NOT_ALLOWED: {field}")

    if value is None:
        return

    value = str(value).strip()

    if not value:
        return

    max_len = FIELD_MAX_LENGTH[field]
    if len(value) > max_len:
        value = value[:max_len]
        log.warning(
            "lead=%s field=%s truncated to %d chars",
            lead.id, field, max_len,
        )

    setattr(lead, field, value)

    lead.score = compute_lead_score(lead)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("Failed to save lead field lead=%s field=%s", lead.id, field)
        raise

    await db.refresh(lead)


async def update_lead_stage(
    db: AsyncSession,
    lead: Lead,
    stage: str,
    reason: Optional[str] = None,
) -> None:
    """
    تحديث مرحلة lead.

    يقبل:
    - "new", "qualifying", ... (القيم)
    - "NEW", "QUALIFYING", ... (الأسماء)
    - عضو LeadStage
    """

    stage_enum = _normalize_stage(stage)

    lead.stage = stage_enum
    lead.score = compute_lead_score(lead)

    if reason:
        lead.handoff_reason = reason[:1000]

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        log.exception("Failed to update lead stage lead=%s stage=%s", lead.id, stage_enum)
        raise

    await db.refresh(lead)

    log.info("Lead %s stage updated to %s", lead.id, stage_enum.value)
