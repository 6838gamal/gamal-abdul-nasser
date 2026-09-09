# app/api/chat.py
"""وكيل الذكاء الاصطناعي — نقطة نهاية محادثة محسّنة مع معالجة الأخطاء."""
import logging
import httpx
from typing import Optional, List
from fastapi import APIRouter, Request, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.database.session import get_db
from app.models.knowledge import KnowledgeEntry
from app.models.chat import ChatLog

log = logging.getLogger("app")
router = APIRouter(prefix="/api")

# ─── إعدادات Gemini ──────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_INSTRUCTION = """أنت وكيل ذكاء اصطناعي متخصص يعمل على منصة جمال المقطري الشخصية.
جمال المقطري متخصص في: تطوير تطبيقات الويب، أتمتة الأعمال، وحلول الذكاء الاصطناعي.
خدماته تشمل: بناء الأنظمة الرقمية، أتمتة العمليات، تطوير بوتات الذكاء الاصطناعي، والاستشارات التقنية.

مهمتك:
- الرد بشكل مهني وودود باللغة العربية دائماً
- مساعدة الزوار في فهم خدمات المنصة والتواصل مع جمال
- الإجابة على أسئلة التقنية والأعمال المتعلقة بتخصصاته
- توجيه الزوار لحجز استشارة عند الاهتمام بالخدمات (رابط التواصل: /contact)
- الردود مختصرة وواضحة (3-5 جمل كحد أقصى لكل رد)
- لا تخترع معلومات لا تعرفها، وكن صادقاً"""

MAX_HISTORY = 20
MAX_MESSAGE_LENGTH = 2000

# ─── النماذج (Pydantic) ─────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str = Field(..., description="دور المرسل: 'user' أو 'model'")
    content: str = Field(..., max_length=MAX_MESSAGE_LENGTH, description="محتوى الرسالة")

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH, description="رسالة المستخدم")
    history: List[ChatMessage] = Field(default=[], description="سجل المحادثة السابق")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="رد الوكيل")
    status: str = Field(default="success", description="حالة الطلب")
    error_code: Optional[str] = Field(default=None, description="رمز الخطأ إن وجد")

# ─── الدوال المساعدة ─────────────────────────────────────────────
def sanitize_text(text: str) -> str:
    """تنقية النص من الأكواد الضارة والحد من الطول."""
    import html
    return html.escape(text.strip())[:MAX_MESSAGE_LENGTH]

async def load_knowledge_context(db: AsyncSession) -> str:
    """جلب المعرفة المفعّلة التي غذّاها المدير للوكيل الذكي."""
    try:
        entries = (await db.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.is_active == True)
            .order_by(KnowledgeEntry.created_at.desc())
        )).scalars().all()
        
        if not entries:
            return ""
        
        blocks = [f"- {e.title}:\n{e.content}" for e in entries]
        return "\n\n📚 معلومات إضافية من المدير:\n" + "\n\n".join(blocks)
    except Exception as e:
        log.warning(f"Failed to load knowledge context: {e}")
        return ""

async def log_chat_interaction(
    db: AsyncSession,
    visitor_id: str,
    message: str,
    reply: str,
    status: str,
    error_message: Optional[str] = None
):
    """تسجيل تفاعل المحادثة في قاعدة البيانات."""
    try:
        chat_log = ChatLog(
            visitor_id=visitor_id,
            message=message,
            reply=reply,
            status=status,
            error_message=error_message,
        )
        db.add(chat_log)
        await db.commit()
    except Exception as e:
        log.error(f"Failed to log chat interaction: {e}")
        await db.rollback()

async def ask_gemini(message: str, history: List[ChatMessage], db: AsyncSession) -> str:
    """إرسال طلب إلى Gemini API مع معالجة الأخطاء."""
    
    # التحقق من وجود مفتاح API
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key-here":
        raise ValueError("GEMINI_API_KEY_NOT_CONFIGURED")

    # تحميل المعرفة
    knowledge_context = await load_knowledge_context(db)
    system_prompt = SYSTEM_INSTRUCTION + knowledge_context

    # بناء المحتوى مع قص التاريخ
    contents = []
    limited_history = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history
    
    for m in limited_history:
        role = "model" if m.role == "model" else "user"
        contents.append({"role": role, "parts": [{"text": sanitize_text(m.content)}]})
    
    contents.append({"role": "user", "parts": [{"text": sanitize_text(message)}]})

    # إعداد الطلب مع system_instruction
    payload = {
        "contents": contents,
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 500,
            "topP": 0.95,
            "topK": 40,
        }
    }

    headers = {"Content-Type": "application/json"}
    params = {"key": settings.GEMINI_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GEMINI_URL, headers=headers, params=params, json=payload)
            
            # معالجة أخطاء HTTP
            if response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "طلب غير صحيح")
                if "API key" in error_msg or "key" in error_msg.lower():
                    raise ValueError("GEMINI_API_KEY_INVALID")
                raise RuntimeError(f"Gemini API error: {error_msg}")
            
            if response.status_code == 403:
                raise ValueError("GEMINI_API_KEY_INVALID")
            
            if response.status_code == 429:
                raise RuntimeError("RATE_LIMIT_EXCEEDED")
            
            response.raise_for_status()
            result = response.json()
            
            # استخراج النص من الاستجابة
            text = extract_text_from_response(result)
            if not text:
                return "⚠️ لم يتم العثور على رد من النموذج. يرجى المحاولة مرة أخرى."
            
            return text
            
    except httpx.TimeoutException:
        log.error("Gemini API timeout")
        raise RuntimeError("TIMEOUT")
    except ValueError as e:
        # إعادة رفع أخطاء القيم المحددة
        raise
    except httpx.HTTPStatusError as e:
        log.error(f"Gemini HTTP error: {e.response.status_code}")
        if e.response.status_code == 429:
            raise RuntimeError("RATE_LIMIT_EXCEEDED")
        raise RuntimeError(f"HTTP_ERROR_{e.response.status_code}")
    except Exception as e:
        log.exception(f"Unexpected error in Gemini call: {e}")
        raise

def extract_text_from_response(result: dict) -> str:
    """استخراج النص من استجابة Gemini بأمان."""
    try:
        candidates = result.get("candidates", [])
        if not candidates:
            return ""
        
        all_text = []
        for candidate in candidates:
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            for part in parts:
                if isinstance(part, dict) and "text" in part:
                    all_text.append(part["text"])
                elif isinstance(part, str):
                    all_text.append(part)
        
        return "\n".join(all_text).strip()
    except Exception as e:
        log.error(f"Error extracting text from Gemini response: {e}")
        return ""

def get_visitor_id(request: Request) -> str:
    """الحصول على معرف الزائر من الطلب."""
    # استخدام IP + User-Agent كمعرف مؤقت
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:50]
    return f"{client_ip}_{user_agent}"

def get_error_message(error: Exception) -> tuple[str, str]:
    """تحويل الاستثناء إلى رسالة خطأ مناسبة للمستخدم."""
    error_str = str(error)
    
    if "GEMINI_API_KEY_NOT_CONFIGURED" in error_str:
        return (
            "⚠️ مفتاح API غير مفعل. يرجى التواصل مع المدير لتفعيل الخدمة.",
            "API_KEY_NOT_CONFIGURED"
        )
    
    if "GEMINI_API_KEY_INVALID" in error_str:
        return (
            "⚠️ مفتاح API غير صحيح أو منتهي الصلاحية. يرجى التواصل مع المدير.",
            "API_KEY_INVALID"
        )
    
    if "RATE_LIMIT_EXCEEDED" in error_str:
        return (
            "⚠️ تم تجاوز حد الاستخدام اليومي. يرجى المحاولة بعد قليل أو التواصل مع المدير.",
            "RATE_LIMIT"
        )
    
    if "TIMEOUT" in error_str:
        return (
            "⏱️ انتهت مهلة الاتصال بخادم الذكاء الاصطناعي. يرجى المحاولة مرة أخرى.",
            "TIMEOUT"
        )
    
    if "HTTP_ERROR_500" in error_str or "HTTP_ERROR_503" in error_str:
        return (
            "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً. يرجى المحاولة لاحقاً.",
            "SERVICE_UNAVAILABLE"
        )
    
    return (
        "⚠️ عذراً، حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى أو التواصل مع المدير.",
        "UNKNOWN_ERROR"
    )

# ─── نقاط النهاية ──────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """نقطة نهاية للتحقق من صحة الخدمة."""
    api_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your-gemini-api-key-here")
    return {
        "status": "healthy",
        "api_configured": api_configured,
        "message": "API is running" if api_configured else "API key not configured"
    }

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    نقطة نهاية المحادثة مع وكيل الذكاء الاصطناعي.
    
    - يعالج أخطاء المفتاح وعدم التفعيل
    - يعيد محاولة الاتصال تلقائياً
    - يسجل جميع المحادثات للتحليل
    """
    # تنقية المدخلات
    clean_message = sanitize_text(req.message)
    clean_history = [
        ChatMessage(role=m.role, content=sanitize_text(m.content))
        for m in req.history
    ]

    # الحصول على معرف الزائر
    visitor_id = get_visitor_id(request)

    # تسجيل الطلب
    log.info(f"Chat from {visitor_id}: '{clean_message[:50]}...'")

    try:
        # محاولة الحصول على رد من Gemini
        reply = await ask_gemini(clean_message, clean_history, db)
        
        # تسجيل النجاح
        await log_chat_interaction(
            db, visitor_id, clean_message, reply, "success"
        )
        
        return ChatResponse(
            reply=reply,
            status="success"
        )

    except ValueError as e:
        # أخطاء التكوين (مفتاح API)
        error_msg, error_code = get_error_message(e)
        log.warning(f"Configuration error: {error_code} - {e}")
        
        await log_chat_interaction(
            db, visitor_id, clean_message, error_msg, "error", str(e)
        )
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code
            }
        )

    except RuntimeError as e:
        # أخطاء التشغيل (معدل الطلبات، مهلة)
        error_msg, error_code = get_error_message(e)
        log.error(f"Runtime error: {error_code} - {e}")
        
        await log_chat_interaction(
            db, visitor_id, clean_message, error_msg, "error", str(e)
        )
        
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if "RATE_LIMIT" in error_code else status.HTTP_500_INTERNAL_SERVER_ERROR
        return JSONResponse(
            status_code=status_code,
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code
            }
        )

    except Exception as e:
        # أخطاء غير متوقعة
        error_msg, error_code = get_error_message(e)
        log.exception(f"Unexpected error: {error_code} - {e}")
        
        await log_chat_interaction(
            db, visitor_id, clean_message, error_msg, "error", str(e)
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "reply": error_msg,
                "status": "error",
                "error_code": error_code
            }
        )
