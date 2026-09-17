# app/services/llm_client.py

"""
Gemini Client — عميل موحّد لـ Google Gemini API.

يوفر:
- generate:      توليد نص (generateContent)
- embed:         embedding لنص واحد
- embed_batch:   embedding لعدة نصوص

مع:
- retry تلقائي (exponential backoff)
- rate limiting بسيط
- logging موحّد
- استخراج آمن للنتائج
"""

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

log = logging.getLogger("app")


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

GENERATE_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768

MAX_TEXT_LENGTH = 8000
MAX_RETRIES = 4
BASE_BACKOFF = 1.0
MAX_BACKOFF = 30.0

# حالات HTTP التي نعيد المحاولة عليها
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _api_key() -> Optional[str]:
    return getattr(settings, "GEMINI_API_KEY", None) or None


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff مع jitter."""
    delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
    return delay + random.uniform(0, delay * 0.3)


def _vector_to_pg(vector: List[float]) -> str:
    """تحويل list إلى صيغة pgvector."""
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


# ══════════════════════════════════════════════════════════════════════
# Client
# ══════════════════════════════════════════════════════════════════════


class GeminiClient:
    """
    عميل Gemini موحّد. يمكن استخدامه كـ singleton.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or _api_key()
        self._timeout = timeout

    # ----------------------------------------------------------------
    # Internal POST with retry
    # ----------------------------------------------------------------

    async def _post(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        POST إلى Gemini API مع retry تلقائي.

        يُرجع JSON dict أو None عند الفشل النهائي.
        """

        if not self._api_key:
            log.warning("GEMINI_API_KEY not set")
            return None

        last_error: Optional[str] = None
        effective_timeout = timeout or self._timeout

        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=effective_timeout
                ) as client:
                    response = await client.post(
                        url,
                        params={"key": self._api_key},
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                # نجاح
                if response.status_code == 200:
                    return response.json()

                # فشل قابل لإعادة المحاولة
                if response.status_code in RETRYABLE_STATUS:
                    last_error = (
                        f"HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    log.warning(
                        "Gemini retryable error (attempt %d/%d): %s",
                        attempt + 1,
                        MAX_RETRIES,
                        last_error,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(_backoff_delay(attempt))
                        continue
                    return None

                # فشل غير قابل لإعادة المحاولة
                log.error(
                    "Gemini API error %s: %s",
                    response.status_code,
                    response.text[:300],
                )
                return None

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning(
                    "Gemini network error (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    last_error,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(_backoff_delay(attempt))
                    continue
                return None

            except Exception as e:
                log.exception("Gemini unexpected error: %s", e)
                return None

        log.error("Gemini failed after retries: %s", last_error)
        return None

    # ----------------------------------------------------------------
    # Generate
    # ----------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_output_tokens: int = 500,
        model: str = GENERATE_MODEL,
    ) -> Optional[str]:
        """
        توليد نص. يُرجع النص أو None عند الفشل.
        """

        if not prompt or not prompt.strip():
            return None

        url = f"{GEMINI_BASE}/models/{model}:generateContent"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt.strip()[:MAX_TEXT_LENGTH]}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        data = await self._post(url, payload)
        if not data:
            return None

        # استخراج آمن
        candidates = data.get("candidates") or []
        if not candidates:
            log.warning("Gemini returned no candidates")
            return None

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            log.warning("Gemini returned no parts")
            return None

        text = (parts[0].get("text") or "").strip()
        return text or None

    # ----------------------------------------------------------------
    # Embed (single)
    # ----------------------------------------------------------------

    async def embed(
        self,
        text_input: str,
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        model: str = EMBEDDING_MODEL,
    ) -> Optional[List[float]]:
        """
        embedding لنص واحد. يُرجع list[float] أو None.
        """

        if not text_input or not text_input.strip():
            return None

        url = f"{GEMINI_BASE}/models/{model}:embedContent"

        clean = text_input.strip()[:MAX_TEXT_LENGTH]

        payload = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": clean}]},
            "taskType": task_type,
        }

        data = await self._post(url, payload)
        if not data:
            return None

        values = (data.get("embedding") or {}).get("values")

        if not values:
            log.warning("Embedding returned no values")
            return None

        if len(values) != EMBEDDING_DIM:
            log.warning(
                "Unexpected embedding dim: %d (expected %d)",
                len(values),
                EMBEDDING_DIM,
            )
            return None

        return values

    # ----------------------------------------------------------------
    # Embed (batch)
    # ----------------------------------------------------------------

    async def embed_batch(
        self,
        texts: List[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        model: str = EMBEDDING_MODEL,
    ) -> List[Optional[List[float]]]:
        """
        embedding لعدة نصوص في طلب واحد.
        يُرجع list بنفس الطول، بعض العناصر قد تكون None.
        """

        if not texts:
            return []

        clean_texts = [
            (t or "").strip()[:MAX_TEXT_LENGTH] or " "
            for t in texts
        ]

        url = f"{GEMINI_BASE}/models/{model}:batchEmbedContents"

        requests_payload = [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
            }
            for t in clean_texts
        ]

        payload = {"requests": requests_payload}

        data = await self._post(url, payload, timeout=60.0)
        if not data:
            return [None] * len(texts)

        embeddings = data.get("embeddings") or []

        if len(embeddings) != len(texts):
            log.warning(
                "Batch size mismatch: got %d, expected %d",
                len(embeddings),
                len(texts),
            )
            return [None] * len(texts)

        results: List[Optional[List[float]]] = []
        for e in embeddings:
            values = (e or {}).get("values")
            if values and len(values) == EMBEDDING_DIM:
                results.append(values)
            else:
                results.append(None)

        return results


# ══════════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════════

_client: Optional[GeminiClient] = None


def get_client() -> GeminiClient:
    """إرجاع singleton للعميل."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
