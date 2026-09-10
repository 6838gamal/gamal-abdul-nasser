# app/agent/loop.py

"""
Agent Loop — حلقة الوكيل

هنا يحدث السحر:
1. نبني السياق.
2. نرسل إلى Gemini مع tools.
3. إذا استدعى أداة → ننفذها ونعيد النتيجة.
4. نكرر حتى يرد نصياً أو نتجاوز الحد.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.executor import execute_tool
from app.agent.prompt import build_system_prompt
from app.agent.tools_schema import TOOLS_SCHEMA
from app.core.config import settings
from app.models.lead import Lead
from app.repositories.message_repo import (
    add_message,
    get_recent_messages,
)
from app.services.summarizer import maybe_summarize

log = logging.getLogger("app")

GEMINI_MODEL = "gemini-2.5-flash"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{GEMINI_MODEL}:generateContent"
)

MAX_ITERATIONS = 5
MAX_OUTPUT_TOKENS = 700


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def build_memory_context(lead: Lead) -> str:
    """
    بناء سياق الذاكرة طويلة المدى.
    """

    lines = ["📋 ملف العميل الحالي:"]

    if lead.name:
        lines.append(f"- الاسم: {lead.name}")
    if lead.company:
        lines.append(f"- الشركة: {lead.company}")
    if lead.project_type:
        lines.append(f"- نوع المشروع: {lead.project_type}")
    if lead.problem:
        lines.append(f"- المشكلة: {lead.problem}")
    if lead.desired_solution:
        lines.append(f"- الحل المطلوب: {lead.desired_solution}")
    if lead.budget:
        lines.append(f"- الميزانية: {lead.budget}")
    if lead.timeline:
        lines.append(f"- الجدول: {lead.timeline}")
    if lead.contact:
        lines.append(f"- التواصل: {lead.contact}")

    lines.append(
        f"- المرحلة: {lead.stage.value if lead.stage else 'new'}"
    )
    lines.append(f"- النقاط: {lead.score}/100")

    if lead.summary:
        lines.append("")
        lines.append("📝 ملخص المحادثة السابقة:")
        lines.append(lead.summary)

    return "\n".join(lines)


def messages_to_contents(
    messages: List,
) -> List[Dict[str, Any]]:
    """
    تحويل رسائل DB إلى صيغة Gemini.
    """

    contents: List[Dict[str, Any]] = []

    for m in messages:
        if not m.content:
            continue

        role = "model" if m.role == "model" else "user"

        contents.append({
            "role": role,
            "parts": [{"text": m.content}],
        })

    return contents


# ══════════════════════════════════════════════════════════════════════
# Gemini Call
# ══════════════════════════════════════════════════════════════════════


async def call_gemini_with_tools(
    contents: List[Dict[str, Any]],
    system_prompt: str,
) -> Dict[str, Any]:
    """
    نداء Gemini مع function calling.
    """

    if (
        not settings.GEMINI_API_KEY
        or settings.GEMINI_API_KEY == "your-gemini-api-key-here"
    ):
        raise ValueError("GEMINI_API_KEY_NOT_CONFIGURED")

    payload: Dict[str, Any] = {
        "contents": contents,
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "tools": [{"function_declarations": TOOLS_SCHEMA}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "topP": 0.9,
            "topK": 40,
        },
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            GEMINI_URL,
            params={"key": settings.GEMINI_API_KEY},
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 400:
            try:
                err = response.json()
                msg = err.get("error", {}).get("message", "")
            except Exception:
                msg = ""

            if "key" in msg.lower():
                raise ValueError("GEMINI_API_KEY_INVALID")

            raise RuntimeError(f"Gemini 400: {msg}")

        if response.status_code == 403:
            raise ValueError("GEMINI_API_KEY_INVALID")

        if response.status_code == 429:
            raise RuntimeError("RATE_LIMIT_EXCEEDED")

        response.raise_for_status()

        return response.json()


# ══════════════════════════════════════════════════════════════════════
# Response Parsing
# ══════════════════════════════════════════════════════════════════════


def extract_parts(
    response: Dict[str, Any],
) -> List[Dict[str, Any]]:
    candidates = response.get("candidates", [])
    if not candidates:
        return []
    return candidates[0].get("content", {}).get("parts", [])


def extract_text(parts: List[Dict[str, Any]]) -> str:
    texts = []
    for p in parts:
        if isinstance(p, dict) and "text" in p:
            texts.append(str(p["text"]))
    return "\n".join(texts).strip()


def extract_function_calls(
    parts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    calls = []
    for p in parts:
        if isinstance(p, dict) and "functionCall" in p:
            calls.append(p["functionCall"])
    return calls


# ══════════════════════════════════════════════════════════════════════
# Main Loop
# ══════════════════════════════════════════════════════════════════════


async def run_agent(
    db: AsyncSession,
    lead: Lead,
    user_message: str,
) -> str:
    """
    تشغيل حلقة الوكيل.

    يعيد الرد النصي النهائي.
    """

    # 1) احفظ رسالة المستخدم
    await add_message(db, lead.id, "user", user_message)

    # 2) اجلب آخر الرسائل
    recent = await get_recent_messages(db, lead.id, limit=20)

    # 3) ابنِ السياق
    memory = build_memory_context(lead)
    system_prompt = build_system_prompt(memory)

    contents = messages_to_contents(recent)

    # 4) حلقة الوكيل
    for iteration in range(MAX_ITERATIONS):

        log.info(
            "Agent loop iteration %s for lead=%s",
            iteration + 1, lead.id,
        )

        response = await call_gemini_with_tools(
            contents, system_prompt
        )

        parts = extract_parts(response)

        if not parts:
            raise RuntimeError("EMPTY_GEMINI_RESPONSE")

        function_calls = extract_function_calls(parts)

        # ─────────────────────────────────
        # لا يوجد function call → رد نهائي
        # ─────────────────────────────────

        if not function_calls:
            reply = extract_text(parts)

            if not reply:
                reply = "عذراً، لم أتمكن من تجهيز رد. حاول مرة أخرى."

            await add_message(db, lead.id, "model", reply)

            # لخّص إن لزم
            await maybe_summarize(db, lead, recent)

            return reply

        # ─────────────────────────────────
        # نفّذ الأدوات
        # ─────────────────────────────────

        contents.append({
            "role": "model",
            "parts": parts,
        })

        tool_response_parts: List[Dict[str, Any]] = []

        for call in function_calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}

            log.info(
                "Tool call: %s args=%s",
                name, json.dumps(args, ensure_ascii=False)[:200],
            )

            result = await execute_tool(name, args, lead, db)

            await add_message(
                db,
                lead.id,
                "tool",
                content=None,
                tool_name=name,
                tool_payload=args,
                tool_result=result,
            )

            tool_response_parts.append({
                "functionResponse": {
                    "name": name,
                    "response": result,
                }
            })

        contents.append({
            "role": "user",
            "parts": tool_response_parts,
        })

    # تجاوز الحد
    log.warning("Agent loop exceeded max iterations for lead=%s", lead.id)

    fallback = (
        "أعتذر، لم أتمكن من إكمال المعالجة. "
        "هل يمكنك إعادة صياغة سؤالك؟"
    )

    await add_message(db, lead.id, "model", fallback)

    return fallback
