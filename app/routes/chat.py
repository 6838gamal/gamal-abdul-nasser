"""وكيل الذكاء الاصطناعي — نقطة نهاية المحادثة."""
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings

log = logging.getLogger("app")
router = APIRouter(prefix="/api")

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


# ─── النماذج ────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str          # "user" | "model"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


def _extract_text(result: dict) -> str:
    """استخراج النص من استجابة Gemini بأي بنية محتملة."""
    candidates = result.get("candidates")
    if not candidates:
        return ""

    text_output = ""
    for candidate in candidates:
        content = candidate.get("content", [])
        if isinstance(content, dict):
            content = [content]
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    parts = item.get("parts")
                    if isinstance(parts, list):
                        for part in parts:
                            if isinstance(part, dict) and "text" in part:
                                text_output += part["text"] + "\n"
                    if item.get("type") in ("text", "output_text") and "text" in item:
                        text_output += item["text"] + "\n"
                elif isinstance(item, str):
                    text_output += item + "\n"
        elif isinstance(content, str):
            text_output += content + "\n"

    return text_output.strip()


async def _ask_gemini(message: str, history: list[ChatMessage]) -> str:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط")

    contents = [{"role": "user", "parts": [{"text": SYSTEM_INSTRUCTION}]},
                {"role": "model", "parts": [{"text": "حسناً، سأتصرف كوكيل الذكاء الاصطناعي لمنصة جمال المقطري."}]}]
    for m in history:
        role = "model" if m.role == "model" else "user"
        contents.append({"role": role, "parts": [{"text": m.content}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    headers = {"Content-Type": "application/json"}
    params = {"key": settings.GEMINI_API_KEY}
    payload = {"contents": contents}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GEMINI_URL, headers=headers, params=params, json=payload)
        response.raise_for_status()
        result = response.json()

    text = _extract_text(result)
    if not text:
        return "⚠️ لم يتم العثور على نص في الرد."
    return text


# ─── نقطة النهاية ────────────────────────────────────────────────
@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    try:
        reply = await _ask_gemini(req.message, req.history)
        return {"reply": reply}

    except Exception as exc:
        log.exception("Chat error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"reply": "عذراً، حدث خطأ مؤقت. يرجى المحاولة مرة أخرى."},
        )
