# app/api/chat.py

"""
وكيل الذكاء الاصطناعي — AI Sales Agent
نقطة نهاية المحادثة مع:
- Knowledge Base
- تحليل نية الزائر
- تأهيل العميل المحتمل
- Lead scoring رقمي
- تحديد الإجراء التالي
- تسجيل المحادثات
- Agent Loop مع Function Calling
- Visitor دائم عبر UUID
- معالجة أخطاء Gemini
"""

import html
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import run_agent
from app.core.config import settings
from app.database.session import get_db
from app.repositories.lead_repo import (
    get_or_create_lead_for_visitor,
    score_to_label,
)
from app.repositories.visitor_repo import get_or_create_visitor


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

MAX_MESSAGE_LENGTH = 2000
MAX_VISITOR_UID_LENGTH = 64
MIN_VISITOR_UID_LENGTH = 8


# ══════════════════════════════════════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    """
    طلب المحادثة.

    visitor_uid: UUID دائم من الفرونت (localStorage).
    message: رسالة المستخدم الحالية.
    """

    message: str = Field(
        ...,
        max_length=MAX_MESSAGE_LENGTH,
        description="رسالة المستخدم الحالية",
    )

    visitor_uid: str = Field(
        ...,
        min_length=MIN_VISITOR_UID_LENGTH,
        max_length=MAX_VISITOR_UID_LENGTH,
        description="معرّف الزائر الدائم",
    )


class LeadSnapshot(BaseModel):
    """
    لقطة من حالة العميل المحتمل.
    تُعاد للفرونت لعرض الحالة أو التتبع.
    """

    stage: str = Field(
        default="new",
        description="مرحلة العميل في الـ funnel",
    )

    score: int = Field(
        default=0,
        description="نقاط العميل (0-100)",
    )

    score_label: str = Field(
        default="cold",
        description="تصنيف العميل: hot / warm / cold",
    )

    name: Optional[str] = Field(
        default=None,
        description="اسم العميل",
    )

    company: Optional[str] = Field(
        default=None,
        description="اسم الشركة",
    )

    contact: Optional[str] = Field(
        default=None,
        description="بيانات التواصل",
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

    next_action: Optional[str] = Field(
        default=None,
        description="الإجراء التالي المقترح",
    )


class ChatResponse(BaseModel):
    """
    استجابة الـ API.

    reply: الحقل الأساسي الذي تستخدمه واجهة الدردشة.
    lead: لقطة اختيارية لحالة العميل.
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

    lead: Optional[LeadSnapshot] = Field(
        default=None,
        description="حالة العميل المحتمل",
    )


# ══════════════════════════════════════════════════════════════════════
# Text Helpers
# ══════════════════════════════════════════════════════════════════════


def sanitize_text(text: str) -> str:
    """
    تنقية النص من HTML والحد من الطول.
    """

    if not text:
        return ""

    cleaned = html.escape(str(text).strip())

    return cleaned[:MAX_MESSAGE_LENGTH]


def clean_visitor_uid(uid: str) -> str:
    """
    تنظيف visitor_uid.
    """

    if not uid:
        return ""

    return str(uid).strip()[:MAX_VISITOR_UID_LENGTH]


def get_client_ip(request: Request) -> str:
    """
    استخراج IP العميل بأمان.
    """

    if request.client and request.client.host:
        return request.client.host

    # محاولة X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for", "")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return ""


# ══════════════════════════════════════════════════════════════════════
# Snapshot Builder
# ══════════════════════════════════════════════════════════════════════


def snapshot_from_lead(lead) -> LeadSnapshot:
    """
    بناء LeadSnapshot من كائن Lead.
    """

    score = lead.score or 0

    return LeadSnapshot(
        stage=(
            lead.stage.value
            if lead.stage
            else "new"
        ),
        score=score,
        score_label=score_to_label(score),
        name=lead.name,
        company=lead.company,
        contact=lead.contact,
        project_type=lead.project_type,
        problem=lead.problem,
        desired_solution=lead.desired_solution,
        budget=lead.budget,
        timeline=lead.timeline,
        next_action=lead.next_action,
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

    if (
        "INVALID_VISITOR_UID"
        in error_str
    ):
        return (
            "⚠️ معرّف الزائر غير صالح. "
            "يرجى تحديث الصفحة.",
            "INVALID_VISITOR_UID",
        )

    return (
        "⚠️ عذراً، حدث خطأ غير متوقع. "
        "يرجى المحاولة مرة أخرى أو التواصل مع المدير.",
        "UNKNOWN_ERROR",
    )


def error_json(
    message: str,
    code: str,
    http_status: int,
) -> JSONResponse:
    """
    بناء استجابة خطأ موحّدة.
    """

    return JSONResponse(
        status_code=http_status,
        content={
            "reply": message,
            "status": "error",
            "error_code": code,
            "lead": None,
        },
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

    الخطوات:
    1. تنظيف المدخلات.
    2. إنشاء/جلب Visitor دائم.
    3. إنشاء/جلب Lead.
    4. تشغيل Agent Loop (مع tools).
    5. حفظ كل الرسائل والأدوات.
    6. إرجاع الرد + لقطة Lead.
    """

    # ══════════════════════════════════════
    # 1) Sanitize Message
    # ══════════════════════════════════════

    clean_message = sanitize_text(req.message)

    if not clean_message:

        return error_json(
            "يرجى كتابة رسالتك أولاً حتى أتمكن من مساعدتك.",
            "EMPTY_MESSAGE",
            status.HTTP_400_BAD_REQUEST,
        )

    # ══════════════════════════════════════
    # 2) Sanitize Visitor UID
    # ══════════════════════════════════════

    visitor_uid = clean_visitor_uid(req.visitor_uid)

    if len(visitor_uid) < MIN_VISITOR_UID_LENGTH:

        return error_json(
            "معرّف الزائر غير صالح.",
            "INVALID_VISITOR_UID",
            status.HTTP_400_BAD_REQUEST,
        )

    # ══════════════════════════════════════
    # 3) Get or Create Visitor
    # ══════════════════════════════════════

    try:

        visitor = await get_or_create_visitor(
            db,
            visitor_uid,
            ip=get_client_ip(request),
            user_agent=request.headers.get(
                "user-agent", ""
            ),
            locale=request.headers.get(
                "accept-language", ""
            )[:16],
            referrer=request.headers.get(
                "referer", ""
            ),
        )

    except ValueError as e:

        log.warning(
            "Invalid visitor uid: %s", e
        )

        return error_json(
            "معرّف الزائر غير صالح.",
            "INVALID_VISITOR_UID",
            status.HTTP_400_BAD_REQUEST,
        )

    # ══════════════════════════════════════
    # 4) Get or Create Lead
    # ══════════════════════════════════════

    try:

        lead = await get_or_create_lead_for_visitor(
            db, visitor
        )

    except Exception as e:

        log.exception(
            "Failed to get/create lead: %s", e
        )

        return error_json(
            "⚠️ حدث خطأ في تهيئة المحادثة.",
            "LEAD_INIT_FAILED",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log.info(
        "Chat request | visitor=%s lead=%s msg='%s'",
        visitor.visitor_uid,
        lead.id,
        clean_message[:80],
    )

    # ══════════════════════════════════════
    # 5) Run Agent Loop
    # ══════════════════════════════════════

    try:

        reply = await run_agent(
            db=db,
            lead=lead,
            user_message=clean_message,
        )

        # إعادة تحميل lead بعد التحديثات
        await db.refresh(lead)

        # ══════════════════════════════════
        # Sales Logging
        # ══════════════════════════════════

        log.info(
            (
                "Agent reply | visitor=%s lead=%s "
                "stage=%s score=%s reply='%s'"
            ),
            visitor.visitor_uid,
            lead.id,
            lead.stage.value if lead.stage else "?",
            lead.score,
            reply[:80],
        )

        # ══════════════════════════════════
        # API Response
        # ══════════════════════════════════

        return ChatResponse(
            reply=reply,
            status="success",
            lead=snapshot_from_lead(lead),
        )

    # ══════════════════════════════════════
    # Configuration Errors (ValueError)
    # ══════════════════════════════════════

    except ValueError as e:

        error_msg, error_code = get_error_message(e)

        log.warning(
            "Configuration error: %s - %s",
            error_code,
            e,
        )

        return error_json(
            error_msg,
            error_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # ══════════════════════════════════════
    # Runtime Errors
    # ══════════════════════════════════════

    except RuntimeError as e:

        error_msg, error_code = get_error_message(e)

        log.error(
            "Runtime error: %s - %s",
            error_code,
            e,
        )

        if error_code == "RATE_LIMIT":

            http_status = (
                status.HTTP_429_TOO_MANY_REQUESTS
            )

        elif error_code in {
            "TIMEOUT",
            "CONNECTION_ERROR",
            "SERVICE_UNAVAILABLE",
        }:

            http_status = (
                status.HTTP_503_SERVICE_UNAVAILABLE
            )

        else:

            http_status = (
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return error_json(
            error_msg,
            error_code,
            http_status,
        )

    # ══════════════════════════════════
    # Unexpected Errors
    # ══════════════════════════════════

    except Exception as e:

        error_msg, error_code = get_error_message(e)

        log.exception(
            "Unexpected Sales Agent error: %s - %s",
            error_code,
            e,
        )

        return error_json(
            error_msg,
            error_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
