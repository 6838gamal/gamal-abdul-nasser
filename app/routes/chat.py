"""وكيل الذكاء الاصطناعي — نقطة نهاية المحادثة."""
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import google.generativeai as genai

from app.core.config import settings

log = logging.getLogger("app")
router = APIRouter(prefix="/api")

# ─── إعداد الجيميناي ────────────────────────────────────────────
_model = None

def _get_model():
    global _model
    if _model is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY غير مضبوط")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction="""أنت وكيل ذكاء اصطناعي متخصص يعمل على منصة جمال المقطري الشخصية.
جمال المقطري متخصص في: تطوير تطبيقات الويب، أتمتة الأعمال، وحلول الذكاء الاصطناعي.
خدماته تشمل: بناء الأنظمة الرقمية، أتمتة العمليات، تطوير بوتات الذكاء الاصطناعي، والاستشارات التقنية.

مهمتك:
- الرد بشكل مهني وودود باللغة العربية دائماً
- مساعدة الزوار في فهم خدمات المنصة والتواصل مع جمال
- الإجابة على أسئلة التقنية والأعمال المتعلقة بتخصصاته
- توجيه الزوار لحجز استشارة عند الاهتمام بالخدمات (رابط التواصل: /contact)
- الردود مختصرة وواضحة (3-5 جمل كحد أقصى لكل رد)
- لا تخترع معلومات لا تعرفها، وكن صادقاً""",
        )
    return _model


# ─── النماذج ────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str          # "user" | "model"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# ─── نقطة النهاية ────────────────────────────────────────────────
@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    try:
        model = _get_model()

        # تحويل السجل إلى صيغة Gemini
        history = [
            {"role": m.role, "parts": [m.content]}
            for m in req.history
        ]

        session = model.start_chat(history=history)
        response = session.send_message(req.message)
        return {"reply": response.text}

    except Exception as exc:
        log.exception("Chat error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"reply": "عذراً، حدث خطأ مؤقت. يرجى المحاولة مرة أخرى."},
        )
