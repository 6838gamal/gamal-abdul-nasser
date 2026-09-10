# app/agent/executor.py

"""
منفّذ الأدوات — Tool Executor

كل استدعاء أداة من Gemini يمر من هنا.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStage
from app.repositories.lead_repo import (
    save_lead_field,
    update_lead_stage,
)
from app.repositories.message_repo import add_message
from app.services.knowledge_search import search_knowledge
from app.services.notifications import notify_owner

log = logging.getLogger("app")


# ══════════════════════════════════════════════════════════════════════
# Intent Detection
# ══════════════════════════════════════════════════════════════════════


def _infer_intent(text: str) -> Optional[str]:
    """
    استنتاج intent من النص.
    """

    if not text:
        return None

    t = text.lower()

    # تكامل
    if any(w in t for w in [
        "ربط", "تكامل", "integration",
        "شوبيفاي", "shopify", "واتساب", "whatsapp",
        "woocommerce", "salla", "zid",
    ]):
        return "integration"

    # AI
    if any(w in t for w in [
        "ai", "ذكاء", "وكيل", "agent", "chatbot", "بوت",
        "rag", "معرفة", "embeddings",
    ]):
        return "ai_solution"

    # أتمتة أعمال
    if any(w in t for w in [
        "نظام", "تطبيق", "منصة", "متابعة", "إدارة",
        "أتمتة", "automation", "crm", "erp",
    ]):
        return "business_automation"

    # تطوير ويب
    if any(w in t for w in [
        "موقع", "ويب", "web", "متجر", "ecommerce",
        "تجارة إلكترونية",
    ]):
        return "web_development"

    # استشارات
    if any(w in t for w in [
        "استشارة", "consulting", "نصيحة", "رأي",
    ]):
        return "consulting"

    return None


# ══════════════════════════════════════════════════════════════════════
# Next Action Inference
# ══════════════════════════════════════════════════════════════════════


# ترتيب الحقول حسب الأولوية
FIELD_TO_ACTION = {
    "name": "ask_about_project",
    "company": "ask_about_project",
    "project_type": "ask_about_problem",
    "problem": "ask_about_timeline",
    "desired_solution": "ask_about_budget",
    "budget": "ask_about_timeline",
    "timeline": "ask_for_contact",
    "contact": "direct_to_contact",
}


def _infer_next_action(lead: Lead, field: str) -> Optional[str]:
    """
    استنتاج الإجراء التالي بناءً على الحقل المُحدَّث.
    """

    # إذا حصلنا على contact → direct
    if lead.contact:
        return "direct_to_contact"

    # إذا حصلنا على timeline → اطلب contact
    if lead.timeline and not lead.contact:
        return "ask_for_contact"

    # إذا حصلنا على budget → اطلب timeline
    if lead.budget and not lead.timeline:
        return "ask_about_timeline"

    # إذا حصلنا على desired_solution → اطلب budget
    if lead.desired_solution and not lead.budget:
        return "ask_about_budget"

    # fallback حسب الحقل
    return FIELD_TO_ACTION.get(field)


# ══════════════════════════════════════════════════════════════════════
# Tool Executor
# ══════════════════════════════════════════════════════════════════════


async def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    lead: Lead,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    تنفيذ أداة وإرجاع نتيجة JSON.

    كل النتائج يجب أن تكون JSON-serializable.
    """

    try:

        # ═════════════════════════════════════════
        # save_lead_info
        # ═════════════════════════════════════════

        if tool_name == "save_lead_info":
            field = args.get("field")
            value = args.get("value")

            if not field or not value:
                return {"ok": False, "error": "missing field or value"}

            await save_lead_field(db, lead, field, value)

            # ─── حدّث intent تلقائياً ─────────
            if field in ("problem", "desired_solution", "project_type"):
                inferred_intent = _infer_intent(str(value))
                if inferred_intent:
                    lead.intent = inferred_intent

            # ─── حدّث next_action تلقائياً ─────
            next_action = _infer_next_action(lead, field)
            if next_action:
                lead.next_action = next_action

            await db.commit()
            await db.refresh(lead)

            log.info(
                "Saved lead field: lead=%s %s=%s score=%s intent=%s next=%s",
                lead.id, field, str(value)[:60],
                lead.score, lead.intent, lead.next_action,
            )

            return {
                "ok": True,
                "field": field,
                "score": lead.score,
                "intent": lead.intent,
                "next_action": lead.next_action,
            }

        # ═════════════════════════════════════════
        # update_lead_stage
        # ═════════════════════════════════════════

        if tool_name == "update_lead_stage":
            stage = args.get("stage")
            reason = args.get("reason")

            if not stage:
                return {"ok": False, "error": "missing stage"}

            await update_lead_stage(db, lead, stage, reason)

            log.info(
                "Updated lead stage: lead=%s stage=%s score=%s",
                lead.id, stage, lead.score,
            )

            return {
                "ok": True,
                "stage": stage,
                "score": lead.score,
            }

        # ═════════════════════════════════════════
        # search_knowledge
        # ═════════════════════════════════════════

        if tool_name == "search_knowledge":
            query = args.get("query", "")

            if not query:
                return {"ok": False, "error": "missing query"}

            results = await search_knowledge(db, query, limit=3)

            return {
                "ok": True,
                "count": len(results),
                "results": results,
            }

        # ═════════════════════════════════════════
        # request_human_handoff
        # ═════════════════════════════════════════

        if tool_name == "request_human_handoff":
            reason = args.get("reason", "")
            urgency = args.get("urgency", "medium")

            # أولاً: CONTACT_REQUESTED
            await update_lead_stage(
                db, lead, "contact_requested", reason,
            )

            # ثم HANDED_OFF
            lead.stage = LeadStage.HANDED_OFF
            await db.commit()
            await db.refresh(lead)

            # إشعار
            await notify_owner(
                lead=lead,
                message=(
                    f"🔔 طلب تحويل بشري\n"
                    f"السبب: {reason}\n"
                    f"الأولوية: {urgency}"
                ),
                urgency=urgency,
            )

            log.warning(
                "Human handoff requested: lead=%s reason=%s",
                lead.id, reason,
            )

            return {
                "ok": True,
                "message": "تم إشعار الفريق، سيتم التواصل قريباً",
            }

        # ═════════════════════════════════════════
        # notify_owner
        # ═════════════════════════════════════════

        if tool_name == "notify_owner":
            message = args.get("message", "")
            urgency = args.get("urgency", "low")

            if not message:
                return {"ok": False, "error": "missing message"}

            await notify_owner(
                lead=lead,
                message=message,
                urgency=urgency,
            )

            return {"ok": True}

        # ═════════════════════════════════════════
        # unknown tool
        # ═════════════════════════════════════════

        log.warning("Unknown tool requested: %s", tool_name)

        return {
            "ok": False,
            "error": f"unknown_tool: {tool_name}",
        }

    except ValueError as e:
        log.warning("Tool validation error: %s", e)
        return {"ok": False, "error": str(e)}

    except Exception as e:
        log.exception("Tool execution failed: %s", e)
        return {"ok": False, "error": "tool_execution_failed"}
