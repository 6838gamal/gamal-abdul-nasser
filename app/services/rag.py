# app/services/rag.py

"""
RAG — Retrieval Augmented Generation.

يبني السياق الكامل الذي يُرسل إلى LLM:
1. ملخص المحادثة السابق (lead.summary)
2. آخر N رسالة من المحادثة
3. نتائج بحث المعرفة (knowledge_search)
4. معلومات الـ lead (إن وُجدت)

الفصل يسمح بـ:
- اختبار السياق بشكل مستقل
- تغيير ترتيب/صيغة السياق في مكان واحد
- إعادة الاستخدام في مهام أخرى (مثل التلخيص)
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead
from app.models.message import Message
from app.services.knowledge_search import search_knowledge

log = logging.getLogger("app")

# حدود افتراضية
DEFAULT_RECENT_MESSAGES = 10
DEFAULT_KNOWLEDGE_LIMIT = 3
MAX_MESSAGE_CHARS = 800
MAX_SUMMARY_CHARS = 2000


# ══════════════════════════════════════════════════════════════════════
# Section builders
# ══════════════════════════════════════════════════════════════════════


def _format_summary_section(summary: str) -> str:
    """قسم الملخص السابق."""
    if not summary or not summary.strip():
        return ""

    summary = summary.strip()[:MAX_SUMMARY_CHARS]
    return f"## ملخص المحادثة السابق\n{summary}"


def _format_messages_section(messages: List[Message]) -> str:
    """قسم الرسائل الأخيرة."""
    if not messages:
        return ""

    lines: List[str] = []
    for m in messages:
        role = getattr(m, "role", "user") or "user"
        content = (getattr(m, "content", "") or "").strip()
        if not content:
            continue
        content = content[:MAX_MESSAGE_CHARS]
        lines.append(f"[{role}]: {content}")

    if not lines:
        return ""

    return "## آخر الرسائل\n" + "\n".join(lines)


def _format_knowledge_section(
    results: List[Dict[str, Any]],
) -> str:
    """قسم المعرفة المسترجَعة."""
    if not results:
        return ""

    lines: List[str] = []
    for i, item in enumerate(results, 1):
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        score = item.get("score")

        header = f"[{i}] {title}" if title else f"[{i}]"
        if score is not None:
            header += f" (score={score})"

        lines.append(header)
        if content:
            lines.append(content)
        lines.append("")

    return "## معلومات من قاعدة المعرفة\n" + "\n".join(lines).strip()


def _format_lead_section(lead: Lead) -> str:
    """قسم معلومات الـ lead."""
    if not lead:
        return ""

    parts: List[str] = []

    name = getattr(lead, "name", None)
    if name:
        parts.append(f"الاسم: {name}")

    email = getattr(lead, "email", None)
    if email:
        parts.append(f"البريد: {email}")

    phone = getattr(lead, "phone", None)
    if phone:
        parts.append(f"الهاتف: {phone}")

    status = getattr(lead, "status", None)
    if status:
        parts.append(f"الحالة: {status}")

    if not parts:
        return ""

    return "## معلومات العميل\n" + "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════
# Public
# ══════════════════════════════════════════════════════════════════════


async def build_context(
    db: AsyncSession,
    lead: Optional[Lead],
    messages: List[Message],
    query: str,
    *,
    recent_limit: int = DEFAULT_RECENT_MESSAGES,
    knowledge_limit: int = DEFAULT_KNOWLEDGE_LIMIT,
    include_knowledge: bool = True,
) -> str:
    """
    بناء السياق الكامل.

    Args:
        db: جلسة DB.
        lead: الـ lead (اختياري).
        messages: كل رسائل المحادثة (سنأخذ آخر N).
        query: استعلام المستخدم الحالي (لبحث المعرفة).
        recent_limit: عدد الرسائل الأخيرة.
        knowledge_limit: عدد نتائج المعرفة.
        include_knowledge: هل نضمّن نتائج البحث.

    Returns:
        نص السياق الجاهز للإرسال إلى LLM.
    """

    sections: List[str] = []

    # 1. معلومات العميل
    if lead:
        lead_section = _format_lead_section(lead)
        if lead_section:
            sections.append(lead_section)

    # 2. ملخص المحادثة السابق
    if lead:
        summary = getattr(lead, "summary", "") or ""
        summary_section = _format_summary_section(summary)
        if summary_section:
            sections.append(summary_section)

    # 3. آخر الرسائل
    recent = messages[-recent_limit:] if messages else []
    messages_section = _format_messages_section(recent)
    if messages_section:
        sections.append(messages_section)

    # 4. بحث المعرفة
    if include_knowledge and query:
        try:
            results = await search_knowledge(
                db,
                query,
                limit=knowledge_limit,
            )
            knowledge_section = _format_knowledge_section(results)
            if knowledge_section:
                sections.append(knowledge_section)
        except Exception as e:
            log.warning("Knowledge search failed in RAG: %s", e)

    if not sections:
        return ""

    return "\n\n".join(sections)


def build_prompt(
    context: str,
    user_message: str,
    *,
    system_prompt: Optional[str] = None,
) -> str:
    """
    دمج السياق + رسالة المستخدم في prompt نهائي.
    """

    default_system = (
        "أنت وكيل مبيعات محترف. أجب بالعربية بوضوح واختصار. "
        "استعن بالمعلومات المرفقة إن وُجدت، ولا تخترع معلومات."
    )

    sys = (system_prompt or default_system).strip()

    parts = [sys]

    if context and context.strip():
        parts.append("---\n" + context.strip())

    parts.append("---\n## رسالة المستخدم\n" + (user_message or "").strip())

    return "\n\n".join(parts)
