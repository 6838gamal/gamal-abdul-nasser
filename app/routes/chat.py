# app/api/chat.py

"""
وكيل الذكاء الاصطناعي — AI Sales Agent
نقطة نهاية المحادثة مع:
- Knowledge Base
- تحليل نية الزائر
- تأهيل العميل المحتمل
- Lead scoring
- تحديد الإجراء التالي
- تسجيل المحادثات
- معالجة أخطاء Gemini
"""

import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.models.knowledge import KnowledgeEntry
from app.models.chat import ChatLog


# ══════════════════════════════════════════════════════════════════════
# Logging / Router
# ══════════════════════════════════════════════════════════════════════

log = logging.getLogger("app")

router = APIRouter(prefix="/api")


# ══════════════════════════════════════════════════════════════════════
# Gemini Configuration
# ══════════════════════════════════════════════════════════════════════

GEMINI_MODEL = "gemini-2.5-flash"

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1beta/models/{GEMINI_MODEL}:generateContent"
)


# ══════════════════════════════════════════════════════════════════════
# General Settings
# ══════════════════════════════════════════════════════════════════════

MAX_HISTORY = 20
MAX_MESSAGE_LENGTH = 2000
MAX_KNOWLEDGE_LENGTH = 30000
MAX_SYSTEM_PROMPT_LENGTH = 50000

MAX_OUTPUT_TOKENS = 700


# ══════════════════════════════════════════════════════════════════════
# System Instructions
# ══════════════════════════════════════════════════════════════════════

SYSTEM_INSTRUCTION = """
أنت وكيل مبيعات ذكي (AI Sales Agent) يعمل على الموقع الشخصي لجمال المقطري.

معلومات صاحب الموقع:
- الاسم: جمال المقطري
- المجال: هندسة البرمجيات وحلول الذكاء الاصطناعي والأتمتة.
- التخصصات الرئيسية:
  1. تطوير تطبيقات الويب.
  2. بناء الأنظمة الرقمية.
  3. أتمتة الأعمال والعمليات.
  4. حلول الذكاء الاصطناعي.
  5. AI Agents.
  6. RAG وKnowledge Base.
  7. APIs وBackends.
  8. التكامل بين الأنظمة والخدمات.
  9. الاستشارات والحلول التقنية.

هدفك الأساسي ليس مجرد الدردشة.

هدفك:
1. فهم مشكلة الزائر الحقيقية.
2. معرفة ما الذي يريد بناءه أو تحسينه.
3. ربط المشكلة بالخدمة المناسبة.
4. شرح الحل بطريقة تجارية بسيطة، وليس بمصطلحات تقنية غير ضرورية.
5. إذا كان الزائر مهتماً فعلياً، تأهيله كعميل محتمل.
6. جمع المعلومات تدريجياً أثناء المحادثة، وليس طرح استبيان طويل في رسالة واحدة.
7. تحديد مدى جدية العميل.
8. دفع العميل نحو الخطوة التالية المناسبة.

أثناء المحادثة حاول فهم:
- نوع المشروع أو النشاط.
- المشكلة الحالية.
- الحل المطلوب.
- حجم العمل أو نطاقه إن أمكن.
- الميزانية إذا كان من المناسب السؤال عنها.
- الجدول الزمني.
- وسيلة التواصل إذا أراد العميل المتابعة.
- اسم العميل أو الشركة إذا شاركه.

قواعد المبيعات:
- لا تضغط على الزائر.
- لا تسأل عن كل المعلومات دفعة واحدة.
- اسأل سؤالاً واحداً أو سؤالين فقط عندما تحتاج إلى معلومات إضافية.
- إذا كان السؤال عاماً، أجب أولاً ثم انتقل للتأهيل.
- إذا لم يكن الزائر عميلاً محتملاً، لا تحاول إجباره على شراء خدمة.
- إذا كان لديه مشروع واضح ومشكلة حقيقية، ركز على فهم المشكلة والخطوة التالية.
- لا تخترع أسعاراً أو مواعيد أو خبرات أو عملاء أو نتائج غير موجودة في قاعدة المعرفة.
- إذا لم تعرف معلومة، قل بوضوح إن المعلومة غير متاحة.
- لا تدّعي أنك شخص بشري.
- لا تدّعي أنك تحدثت مع جمال أو أرسلت إليه شيئاً إذا لم يتم تنفيذ ذلك فعلياً.
- لا تقل إن الطلب تم تسجيله كعميل محتمل إلا إذا كان النظام قد سجله فعلياً.

أسلوب الرد:
- اللغة العربية هي اللغة الأساسية.
- يمكن استخدام المصطلحات التقنية الإنجليزية عند الحاجة.
- كن مهنياً وواضحاً وودوداً.
- اجعل الرد مختصراً.
- لا تستخدم فقرات طويلة.
- لا تستخدم أكثر من 5 جمل تقريباً في الرد الطبيعي.
- لا تكرر نفس المعلومات التي قالها الزائر.
- ركز على المشكلة والنتيجة.

التعامل مع العملاء:
إذا قال الزائر مثلاً:
"أريد نظاماً لمتابعة العملاء"
لا تبدأ مباشرة بشرح FastAPI أو PostgreSQL.
اسأله عن طريقة العمل الحالية والمشكلة التي يريد حلها.

إذا قال:
"عندي مطعم وتضيع طلبات العملاء من الواتساب"
تعامل مع ذلك كإشارة إلى مشكلة تجارية حقيقية.
يمكنك اقتراح نظام لإدارة المحادثات والطلبات والمتابعة، ثم اسأل عن حجم الطلبات أو طريقة العمل الحالية.

إذا قال:
"أريد AI Agent"
لا تكتفِ بشرح AI Agents.
اسأل: ما المهمة التي تريد أن يقوم بها الوكيل؟ وما البيانات أو الأنظمة التي يحتاج للوصول إليها؟

الرابط الأساسي للتواصل:
 /contact

عندما يصبح العميل مهتماً فعلياً، يمكنك توجيهه إلى صفحة التواصل.
""".strip()


# ══════════════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════════════


class ChatMessage(BaseModel):
    """
    رسالة واحدة داخل سجل المحادثة.
    """

    role: str = Field(
        ...,
        description="دور المرسل: user أو model",
    )

    content: str = Field(
        ...,
        max_length=MAX_MESSAGE_LENGTH,
        description="محتوى الرسالة",
    )


class ChatRequest(BaseModel):
    """
    طلب المحادثة.
    """

    message: str = Field(
        ...,
        max_length=MAX_MESSAGE_LENGTH,
        description="رسالة المستخدم الحالية",
    )

    history: List[ChatMessage] = Field(
        default_factory=list,
        description="سجل المحادثة السابق",
    )


class LeadData(BaseModel):
    """
    بيانات العميل المحتمل المستخرجة من المحادثة.

    هذه البيانات لا تتطلب وجود Lead model في قاعدة البيانات حالياً.
    سنستخدمها في المرحلة التالية لربطها بجدول Leads.
    """

    intent: str = Field(
        default="general",
        description="نية الزائر",
    )

    lead_status: str = Field(
        default="unknown",
        description="حالة العميل المحتمل",
    )

    lead_score: str = Field(
        default="cold",
        description="درجة العميل: hot / warm / cold",
    )

    project_type: Optional[str] = Field(
        default=None,
        description="نوع المشروع",
    )

    problem: Optional[str] = Field(
        default=None,
        description="المشكلة أو الألم",
    )

    desired_solution: Optional[str] = Field(
        default=None,
        description="الحل المطلوب",
    )

    budget: Optional[str] = Field(
        default=None,
        description="الميزانية إن ذكرت",
    )

    timeline: Optional[str] = Field(
        default=None,
        description="الجدول الزمني إن ذكر",
    )

    contact: Optional[str] = Field(
        default=None,
        description="بيانات التواصل إن ذكرها العميل",
    )

    company: Optional[str] = Field(
        default=None,
        description="اسم الشركة إن ذكر",
    )

    name: Optional[str] = Field(
        default=None,
        description="اسم العميل إن ذكر",
    )

    next_action: str = Field(
        default="continue_conversation",
        description="الإجراء التالي المقترح",
    )


class ChatResponse(BaseModel):
    """
    استجابة الـ API.

    reply هو الحقل الأساسي الذي تستخدمه واجهة الدردشة الحالية.
    الحقول الأخرى إضافية ويمكن للواجهة استخدامها لاحقاً.
    """

    reply: str = Field(
        ...,
        description="رد الوكيل",
    )

    status: str = Field(
        default="success",
        description="حالة الطلب",
    )

    error_code: Optional[str] = Field(
        default=None,
        description="رمز الخطأ إن وجد",
    )

    intent: Optional[str] = Field(
        default=None,
        description="نية الزائر",
    )

    lead_status: Optional[str] = Field(
        default=None,
        description="حالة العميل المحتمل",
    )

    lead_score: Optional[str] = Field(
        default=None,
        description="درجة العميل المحتمل",
    )

    lead: Optional[LeadData] = Field(
        default=None,
        description="بيانات العميل المحتمل",
    )


# ══════════════════════════════════════════════════════════════════════
# Text Helpers
# ══════════════════════════════════════════════════════════════════════


def sanitize_text(text: str) -> str:
    """
    تنقية النص من HTML والأكواد المحتملة والحد من الطول.
    """

    if not text:
        return ""

    cleaned = html.escape(str(text).strip())

    return cleaned[:MAX_MESSAGE_LENGTH]


def normalize_role(role: str) -> str:
    """
    تحويل الدور إلى القيم التي يفهمها Gemini.
    """

    role = (role or "").strip().lower()

    if role in {"assistant", "model", "ai"}:
        return "model"

    return "user"


def clean_optional(value: Any) -> Optional[str]:
    """
    تنظيف قيمة اختيارية وإرجاع None عند عدم وجود قيمة حقيقية.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value[:500]


# ══════════════════════════════════════════════════════════════════════
# Knowledge Base
# ══════════════════════════════════════════════════════════════════════


async def load_knowledge_context(
    db: AsyncSession,
) -> str:
    """
    جلب المعرفة المفعّلة التي أضافها المدير للوكيل.

    ملاحظة:
    هذه ليست RAG semantic search بعد.
    حالياً يتم تحميل الإدخالات المفعّلة كما كان في النظام السابق.
    """

    try:
        result = await db.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.is_active == True)
            .order_by(KnowledgeEntry.created_at.desc())
        )

        entries = result.scalars().all()

        if not entries:
            return ""

        blocks: List[str] = []
        current_length = 0

        for entry in entries:
            title = str(getattr(entry, "title", "") or "")
            content = str(getattr(entry, "content", "") or "")

            if not content:
                continue

            block = f"- {title}:\n{content}"

            if current_length + len(block) > MAX_KNOWLEDGE_LENGTH:
                break

            blocks.append(block)
            current_length += len(block)

        if not blocks:
            return ""

        return (
            "\n\n"
            "════════════════════════════════════\n"
            "📚 معلومات موثوقة من قاعدة المعرفة\n"
            "════════════════════════════════════\n"
            + "\n\n".join(blocks)
        )

    except Exception as e:
        log.warning(
            "Failed to load knowledge context: %s",
            e,
        )

        return ""


# ══════════════════════════════════════════════════════════════════════
# Visitor Identification
# ══════════════════════════════════════════════════════════════════════


def get_visitor_id(request: Request) -> str:
    """
    إنشاء معرف مؤقت للزائر.

    ملاحظة:
    هذا ليس نظام هوية دائم.
    لاحقاً يمكن استبداله بـ session ID أو visitor UUID.
    """

    client_ip = (
        request.client.host
        if request.client
        else "unknown"
    )

    user_agent = request.headers.get(
        "user-agent",
        "unknown",
    )[:100]

    return f"{client_ip}_{user_agent}"


# ══════════════════════════════════════════════════════════════════════
# Chat Logging
# ══════════════════════════════════════════════════════════════════════


async def log_chat_interaction(
    db: AsyncSession,
    visitor_id: str,
    message: str,
    reply: str,
    status_value: str,
    error_message: Optional[str] = None,
):
    """
    تسجيل المحادثة في قاعدة البيانات.
    """

    try:
        chat_log = ChatLog(
            visitor_id=visitor_id,
            message=message,
            reply=reply,
            status=status_value,
            error_message=error_message,
        )

        db.add(chat_log)

        await db.commit()

    except Exception as e:
        log.error(
            "Failed to log chat interaction: %s",
            e,
        )

        await db.rollback()


# ══════════════════════════════════════════════════════════════════════
# Gemini Request
# ══════════════════════════════════════════════════════════════════════


async def call_gemini(
    *,
    message: str,
    history: List[ChatMessage],
    system_prompt: str,
) -> Dict[str, Any]:
    """
    إرسال طلب إلى Gemini وإرجاع JSON الناتج.
    """

    if (
        not settings.GEMINI_API_KEY
        or settings.GEMINI_API_KEY
        == "your-gemini-api-key-here"
    ):
        raise ValueError(
            "GEMINI_API_KEY_NOT_CONFIGURED"
        )

    contents: List[Dict[str, Any]] = []

    limited_history = (
        history[-MAX_HISTORY:]
        if len(history) > MAX_HISTORY
        else history
    )

    for item in limited_history:

        content = sanitize_text(
            item.content
        )

        if not content:
            continue

        contents.append(
            {
                "role": normalize_role(item.role),
                "parts": [
                    {
                        "text": content
                    }
                ],
            }
        )

    clean_message = sanitize_text(message)

    contents.append(
        {
            "role": "user",
            "parts": [
                {
                    "text": clean_message
                }
            ],
        }
    )

    payload: Dict[str, Any] = {
        "contents": contents,

        "system_instruction": {
            "parts": [
                {
                    "text": system_prompt
                }
            ]
        },

        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "topP": 0.9,
            "topK": 40,

            # نطلب من النموذج JSON حتى نستطيع
            # فصل رد المستخدم عن بيانات التأهيل.
            "responseMimeType": "application/json",
        },
    }

    headers = {
        "Content-Type": "application/json",
    }

    params = {
        "key": settings.GEMINI_API_KEY,
    }

    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.post(
                GEMINI_URL,
                headers=headers,
                params=params,
                json=payload,
            )

            # ──────────────────────────────────────────
            # HTTP 400
            # ──────────────────────────────────────────

            if response.status_code == 400:

                try:
                    error_data = response.json()

                except Exception:
                    error_data = {}

                error_msg = (
                    error_data
                    .get("error", {})
                    .get(
                        "message",
                        "طلب غير صحيح",
                    )
                )

                if (
                    "API key" in error_msg
                    or "key" in error_msg.lower()
                ):
                    raise ValueError(
                        "GEMINI_API_KEY_INVALID"
                    )

                raise RuntimeError(
                    f"Gemini API error: {error_msg}"
                )

            # ──────────────────────────────────────────
            # HTTP 403
            # ──────────────────────────────────────────

            if response.status_code == 403:

                raise ValueError(
                    "GEMINI_API_KEY_INVALID"
                )

            # ──────────────────────────────────────────
            # HTTP 429
            # ──────────────────────────────────────────

            if response.status_code == 429:

                raise RuntimeError(
                    "RATE_LIMIT_EXCEEDED"
                )

            response.raise_for_status()

            try:
                result = response.json()

            except Exception as e:

                log.error(
                    "Failed to decode Gemini JSON response: %s",
                    e,
                )

                raise RuntimeError(
                    "INVALID_GEMINI_RESPONSE"
                )

            return result

    except httpx.TimeoutException:

        log.error(
            "Gemini API timeout"
        )

        raise RuntimeError(
            "TIMEOUT"
        )

    except ValueError:

        raise

    except httpx.HTTPStatusError as e:

        log.error(
            "Gemini HTTP error: %s",
            e.response.status_code,
        )

        if e.response.status_code == 429:

            raise RuntimeError(
                "RATE_LIMIT_EXCEEDED"
            )

        raise RuntimeError(
            f"HTTP_ERROR_{e.response.status_code}"
        )

    except httpx.RequestError as e:

        log.error(
            "Gemini connection error: %s",
            e,
        )

        raise RuntimeError(
            "CONNECTION_ERROR"
        )

    except Exception as e:

        log.exception(
            "Unexpected error in Gemini call: %s",
            e,
        )

        raise


# ══════════════════════════════════════════════════════════════════════
# Gemini Response Extraction
# ══════════════════════════════════════════════════════════════════════


def extract_text_from_response(
    result: Dict[str, Any],
) -> str:
    """
    استخراج النص من استجابة Gemini.
    """

    try:

        candidates = result.get(
            "candidates",
            [],
        )

        if not candidates:
            return ""

        all_text: List[str] = []

        for candidate in candidates:

            content = candidate.get(
                "content",
                {},
            )

            parts = content.get(
                "parts",
                [],
            )

            for part in parts:

                if (
                    isinstance(part, dict)
                    and "text" in part
                ):

                    text = part.get(
                        "text"
                    )

                    if text:
                        all_text.append(
                            str(text)
                        )

                elif isinstance(
                    part,
                    str,
                ):

                    all_text.append(
                        part
                    )

        return "\n".join(
            all_text
        ).strip()

    except Exception as e:

        log.error(
            "Error extracting text from Gemini response: %s",
            e,
        )

        return ""


# ══════════════════════════════════════════════════════════════════════
# JSON Parsing
# ══════════════════════════════════════════════════════════════════════


def extract_json_object(
    text: str,
) -> Optional[Dict[str, Any]]:
    """
    محاولة استخراج JSON object من النص.

    يدعم أيضاً الحالات التي يضع فيها النموذج JSON
    داخل ```json ... ```.
    """

    if not text:
        return None

    cleaned = text.strip()

    # إزالة Markdown fences
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    cleaned = cleaned.strip()

    # محاولة مباشرة
    try:

        data = json.loads(
            cleaned
        )

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    # محاولة العثور على أول object
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        return None

    candidate = cleaned[
        start:end + 1
    ]

    try:

        data = json.loads(
            candidate
        )

        if isinstance(data, dict):
            return data

    except Exception as e:

        log.warning(
            "Failed to parse Gemini JSON: %s",
            e,
        )

    return None


# ══════════════════════════════════════════════════════════════════════
# Lead Analysis
# ══════════════════════════════════════════════════════════════════════


def normalize_lead_data(
    data: Optional[Dict[str, Any]],
) -> LeadData:
    """
    تحويل بيانات النموذج إلى LeadData آمنة.
    """

    if not isinstance(data, dict):
        return LeadData()

    intent = clean_optional(
        data.get("intent")
    ) or "general"

    lead_status = clean_optional(
        data.get("lead_status")
    ) or "unknown"

    lead_score = clean_optional(
        data.get("lead_score")
    ) or "cold"

    next_action = clean_optional(
        data.get("next_action")
    ) or "continue_conversation"

    # حماية القيم الأساسية
    valid_scores = {
        "hot",
        "warm",
        "cold",
    }

    if lead_score.lower() not in valid_scores:
        lead_score = "cold"

    return LeadData(
        intent=intent[:100],

        lead_status=lead_status[:100],

        lead_score=lead_score.lower(),

        project_type=clean_optional(
            data.get("project_type")
        ),

        problem=clean_optional(
            data.get("problem")
        ),

        desired_solution=clean_optional(
            data.get("desired_solution")
        ),

        budget=clean_optional(
            data.get("budget")
        ),

        timeline=clean_optional(
            data.get("timeline")
        ),

        contact=clean_optional(
            data.get("contact")
        ),

        company=clean_optional(
            data.get("company")
        ),

        name=clean_optional(
            data.get("name")
        ),

        next_action=next_action[:200],
    )


# ══════════════════════════════════════════════════════════════════════
# Sales Prompt
# ══════════════════════════════════════════════════════════════════════


def build_sales_prompt(
    knowledge_context: str,
) -> str:
    """
    بناء تعليمات Sales Agent.

    نطلب من Gemini أن يرجع:
    reply + lead information
    في JSON واحد.
    """

    output_instruction = """

════════════════════════════════════
تعليمات إخراج النظام
════════════════════════════════════

يجب أن يكون ردك JSON صالحاً فقط، بدون Markdown وبدون ```.

استخدم هذا الشكل بالضبط:

{
  "reply": "الرد العربي الذي سيظهر للزائر",
  "lead": {
    "intent": "general",
    "lead_status": "unknown",
    "lead_score": "cold",
    "project_type": null,
    "problem": null,
    "desired_solution": null,
    "budget": null,
    "timeline": null,
    "contact": null,
    "company": null,
    "name": null,
    "next_action": "continue_conversation"
  }
}

قواعد lead_score:

cold:
- سؤال عام.
- لا يوجد مشروع واضح.
- لا توجد مشكلة تجارية واضحة.
- الزائر يستكشف فقط.

warm:
- لديه مشروع أو مشكلة واضحة.
- مهتم بحل عملي.
- توجد نية مبدئية للتنفيذ.
- لكنه لم يصل بعد إلى مرحلة اتخاذ قرار واضحة.

hot:
- لديه مشروع واضح.
- يريد التنفيذ أو عرضاً أو استشارة.
- لديه مشكلة حقيقية يريد حلها.
- يسأل عن البدء أو السعر أو المدة أو طريقة التعاقد.
- قدم بيانات تواصل أو طلب التواصل.

قواعد lead_status:

unknown:
- لا توجد معلومات كافية.

qualified:
- توجد مشكلة واضحة وحاجة لخدمة مناسبة.

contact_requested:
- طلب العميل التواصل أو المتابعة.

ready_to_buy:
- أظهر نية قوية للبدء أو التنفيذ.

not_a_lead:
- السؤال لا يتعلق بخدمة يمكن تقديمها.

قواعد intent:

استخدم قيمة مناسبة مثل:
- general
- service_inquiry
- web_development
- business_automation
- ai_solution
- ai_agent
- chatbot
- rag
- document_intelligence
- integration
- consulting
- pricing
- project_request
- support
- other

مهم جداً:

لا تخترع:
- budget
- timeline
- contact
- name
- company

إذا لم يذكرها العميل، استخدم null.

لا تستنتج ميزانية أو بيانات شخصية من كلام غير صريح.

next_action يجب أن تكون إحدى القيم التالية قدر الإمكان:
- continue_conversation
- ask_about_problem
- ask_about_project
- ask_about_timeline
- ask_about_budget
- ask_for_contact
- recommend_service
- direct_to_contact
- human_handoff

لا تطلب بيانات التواصل مبكراً.
أولاً افهم المشكلة والقيمة المطلوبة.
"""

    prompt = (
        SYSTEM_INSTRUCTION
        + "\n\n"
        + output_instruction
    )

    if knowledge_context:
        prompt += "\n\n" + knowledge_context

    return prompt[
        :MAX_SYSTEM_PROMPT_LENGTH
    ]


# ══════════════════════════════════════════════════════════════════════
# Main AI Function
# ══════════════════════════════════════════════════════════════════════


async def ask_sales_agent(
    message: str,
    history: List[ChatMessage],
    db: AsyncSession,
) -> tuple[str, LeadData]:
    """
    تشغيل Sales Agent وإرجاع:
    - الرد النصي
    - بيانات Lead
    """

    knowledge_context = (
        await load_knowledge_context(
            db
        )
    )

    system_prompt = build_sales_prompt(
        knowledge_context
    )

    result = await call_gemini(
        message=message,
        history=history,
        system_prompt=system_prompt,
    )

    raw_text = extract_text_from_response(
        result
    )

    if not raw_text:

        raise RuntimeError(
            "EMPTY_GEMINI_RESPONSE"
        )

    parsed = extract_json_object(
        raw_text
    )

    # ──────────────────────────────────────
    # الحالة المثالية: JSON صالح
    # ──────────────────────────────────────

    if parsed:

        reply = (
            parsed.get("reply")
            or parsed.get("response")
            or ""
        )

        lead_raw = parsed.get(
            "lead"
        )

        if not isinstance(
            lead_raw,
            dict,
        ):
            lead_raw = {}

        lead_data = normalize_lead_data(
            lead_raw
        )

        reply = str(
            reply
        ).strip()

        if reply:

            return (
                reply,
                lead_data,
            )

    # ──────────────────────────────────────
    # Fallback
    # ──────────────────────────────────────
    #
    # إذا أعاد النموذج نصاً عادياً بدلاً من JSON،
    # لا نفشل المحادثة.
    # ──────────────────────────────────────

    fallback_reply = raw_text.strip()

    if not fallback_reply:

        fallback_reply = (
            "عذراً، لم أتمكن من تجهيز الرد حالياً. "
            "يرجى المحاولة مرة أخرى."
        )

    return (
        fallback_reply,
        LeadData(),
    )


# ══════════════════════════════════════════════════════════════════════
# Error Handling
# ══════════════════════════════════════════════════════════════════════


def get_error_message(
    error: Exception,
) -> tuple[str, str]:
    """
    تحويل الاستثناء إلى رسالة مناسبة للمستخدم.
    """

    error_str = str(error)

    if (
        "GEMINI_API_KEY_NOT_CONFIGURED"
        in error_str
    ):
        return (
            "⚠️ مفتاح Gemini API غير مفعل حالياً. "
            "يرجى التواصل مع المدير لتفعيل الخدمة.",
            "API_KEY_NOT_CONFIGURED",
        )

    if (
        "GEMINI_API_KEY_INVALID"
        in error_str
    ):
        return (
            "⚠️ مفتاح Gemini API غير صحيح أو منتهي الصلاحية. "
            "يرجى التواصل مع المدير.",
            "API_KEY_INVALID",
        )

    if (
        "RATE_LIMIT_EXCEEDED"
        in error_str
    ):
        return (
            "⚠️ تم تجاوز حد استخدام خدمة الذكاء الاصطناعي. "
            "يرجى المحاولة بعد قليل.",
            "RATE_LIMIT",
        )

    if "TIMEOUT" in error_str:

        return (
            "⏱️ انتهت مهلة الاتصال بخادم الذكاء الاصطناعي. "
            "يرجى المحاولة مرة أخرى.",
            "TIMEOUT",
        )

    if (
        "CONNECTION_ERROR"
        in error_str
    ):
        return (
            "⚠️ تعذر الاتصال بخدمة الذكاء الاصطناعي حالياً. "
            "يرجى المحاولة مرة أخرى.",
            "CONNECTION_ERROR",
        )

    if (
        "HTTP_ERROR_500"
        in error_str
        or "HTTP_ERROR_502"
        in error_str
        or "HTTP_ERROR_503"
        in error_str
        or "HTTP_ERROR_504"
        in error_str
    ):
        return (
            "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً. "
            "يرجى المحاولة لاحقاً.",
            "SERVICE_UNAVAILABLE",
        )

    if (
        "EMPTY_GEMINI_RESPONSE"
        in error_str
    ):
        return (
            "⚠️ لم يتم الحصول على رد من نموذج الذكاء الاصطناعي. "
            "يرجى المحاولة مرة أخرى.",
            "EMPTY_RESPONSE",
        )

    if (
        "INVALID_GEMINI_RESPONSE"
        in error_str
    ):
        return (
            "⚠️ حدثت مشكلة في معالجة استجابة الذكاء الاصطناعي. "
            "يرجى المحاولة مرة أخرى.",
            "INVALID_RESPONSE",
        )

    return (
        "⚠️ عذراً، حدث خطأ غير متوقع. "
        "يرجى المحاولة مرة أخرى أو التواصل مع المدير.",
        "UNKNOWN_ERROR",
    )


# ══════════════════════════════════════════════════════════════════════
# Health Check
# ══════════════════════════════════════════════════════════════════════


@router.get("/health")
async def health_check():
    """
    نقطة نهاية للتحقق من صحة الخدمة.
    """

    api_configured = bool(
        settings.GEMINI_API_KEY
        and settings.GEMINI_API_KEY
        != "your-gemini-api-key-here"
    )

    return {
        "status": "healthy",
        "api_configured": api_configured,
        "agent": "ai-sales-agent",
        "model": GEMINI_MODEL,
        "message": (
            "API is running"
            if api_configured
            else "API key not configured"
        ),
    }


# ══════════════════════════════════════════════════════════════════════
# Chat Endpoint
# ══════════════════════════════════════════════════════════════════════


@router.post(
    "/chat",
    response_model=ChatResponse,
)
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    نقطة نهاية المحادثة مع AI Sales Agent.

    الوظائف:
    - تنظيف المدخلات.
    - تحميل Knowledge Base.
    - تشغيل Gemini.
    - تحليل العميل المحتمل.
    - تسجيل المحادثة.
    - إعادة الرد والـ lead metadata.
    """

    # ══════════════════════════════════════
    # Sanitize Message
    # ══════════════════════════════════════

    clean_message = sanitize_text(
        req.message
    )

    if not clean_message:

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "reply": (
                    "يرجى كتابة رسالتك أولاً "
                    "حتى أتمكن من مساعدتك."
                ),
                "status": "error",
                "error_code": "EMPTY_MESSAGE",
            },
        )

    # ══════════════════════════════════════
    # Sanitize History
    # ══════════════════════════════════════

    clean_history: List[ChatMessage] = []

    for item in req.history:

        content = sanitize_text(
            item.content
        )

        if not content:
            continue

        clean_history.append(
            ChatMessage(
                role=normalize_role(
                    item.role
                ),
                content=content,
            )
        )

    # ══════════════════════════════════════
    # Visitor ID
    # ══════════════════════════════════════

    visitor_id = get_visitor_id(
        request
    )

    log.info(
        "AI Sales Agent request from %s: '%s...'",
        visitor_id,
        clean_message[:80],
    )

    # ══════════════════════════════════════
    # Call Agent
    # ══════════════════════════════════════

    try:

        reply, lead_data = (
            await ask_sales_agent(
                clean_message,
                clean_history,
                db,
            )
        )

        # ══════════════════════════════════
        # Log Conversation
        # ══════════════════════════════════

        await log_chat_interaction(
            db=db,
            visitor_id=visitor_id,
            message=clean_message,
            reply=reply,
            status_value="success",
        )

        # ══════════════════════════════════
        # Sales Logging
        # ══════════════════════════════════

        log.info(
            (
                "Sales lead analysis | "
                "visitor=%s intent=%s "
                "score=%s status=%s "
                "next=%s"
            ),
            visitor_id,
            lead_data.intent,
            lead_data.lead_score,
            lead_data.lead_status,
            lead_data.next_action,
        )

        # ══════════════════════════════════
        # API Response
        # ══════════════════════════════════

        return ChatResponse(
            reply=reply,
            status="success",
            intent=lead_data.intent,
            lead_status=lead_data.lead_status,
            lead_score=lead_data.lead_score,
            lead=lead_data,
        )

    # ══════════════════════════════════════
    # Configuration Errors
    # ══════════════════════════════════════

    except ValueError as e:

        error_msg, error_code = (
            get_error_message(e)
        )

        log.warning(
            "Configuration error: %s - %s",
            error_code,
            e,
        )

        await log_chat_interaction(
            db=db,
            visitor_id=visitor_id,
            message=clean_message,
            reply=error_msg,
            status_value="error",
            error_message=str(e),
        )

        return JSONResponse(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code,
            },
        )

    # ══════════════════════════════════════
    # Runtime Errors
    # ══════════════════════════════════════

    except RuntimeError as e:

        error_msg, error_code = (
            get_error_message(e)
        )

        log.error(
            "Runtime error: %s - %s",
            error_code,
            e,
        )

        await log_chat_interaction(
            db=db,
            visitor_id=visitor_id,
            message=clean_message,
            reply=error_msg,
            status_value="error",
            error_message=str(e),
        )

        if error_code == "RATE_LIMIT":

            status_code = (
                status.HTTP_429_TOO_MANY_REQUESTS
            )

        elif error_code in {
            "TIMEOUT",
            "CONNECTION_ERROR",
            "SERVICE_UNAVAILABLE",
        }:

            status_code = (
                status.HTTP_503_SERVICE_UNAVAILABLE
            )

        else:

            status_code = (
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return JSONResponse(
            status_code=status_code,
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code,
            },
        )

    # ══════════════════════════════════════
    # Unexpected Errors
    # ══════════════════════════════════════

    except Exception as e:

        error_msg, error_code = (
            get_error_message(e)
        )

        log.exception(
            "Unexpected Sales Agent error: %s - %s",
            error_code,
            e,
        )

        await log_chat_interaction(
            db=db,
            visitor_id=visitor_id,
            message=clean_message,
            reply=error_msg,
            status_value="error",
            error_message=str(e),
        )

        return JSONResponse(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code,
            },
        )
