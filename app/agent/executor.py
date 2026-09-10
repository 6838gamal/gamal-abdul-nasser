# app/agent/executor.py

"""
منفّذ الأدوات — Tool Executor

كل استدعاء أداة من Gemini يمر من هنا.
"""

import logging
from typing import Any, Dict

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


async def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    lead: Lead,
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    تنفيذ أداة وإرجاع نتيجة JSON.

    كل النتائج يجب أن تكون JSON-serializable
    لأنها ستُرسَل إلى Gemini.
    """

    try:

        # ─────────────────────────────────────
        # save_lead_info
        # ─────────────────────────────────────

        if tool_name == "save_lead_info":
            field = args.get("field")
            value = args.get("value")

            if not field or not value:
                return {"ok": False, "error": "missing field or value"}

            await save_lead_field(db, lead, field, value)

            log.info(
                "Saved lead field: lead=%s %s=%s",
                lead.id, field, str(value)[:60],
            )

            return {
                "ok": True,
                "field": field,
                "score": lead.score,
            }

        # ─────────────────────────────────────
        # update_lead_stage
        # ─────────────────────────────────────

        if tool_name == "update_lead_stage":
            stage = args.get("stage")
            reason = args.get("reason")

            if not stage:
                return {"ok": False, "error": "missing stage"}

            await update_lead_stage(db, lead, stage, reason)

            log.info(
                "Updated lead stage: lead=%s stage=%s",
                lead.id, stage,
            )

            return {
                "ok": True,
                "stage": stage,
                "score": lead.score,
            }

        # ─────────────────────────────────────
        # search_knowledge
        # ─────────────────────────────────────

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

        # ─────────────────────────────────────
        # request_human_handoff
        # ─────────────────────────────────────

        if tool_name == "request_human_handoff":
            reason = args.get("reason", "")
            urgency = args.get("urgency", "medium")

            await update_lead_stage(
                db, lead, "contact_requested", reason
            )

            lead.stage = LeadStage.HANDED_OFF
            await db.commit()

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

        # ─────────────────────────────────────
        # notify_owner
        # ─────────────────────────────────────

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

        # ─────────────────────────────────────
        # unknown tool
        # ─────────────────────────────────────

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
