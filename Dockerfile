FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads /app/logs

EXPOSE 8000

# ─────────────────────────────────────────────────────
# Uvicorn مباشرة:
#   - يدعم --lifespan on أصلياً
#   - lifespan يشغّل _ensure_chat_tables تلقائياً
#   - --workers 1 كافٍ لـ plan: starter
# ─────────────────────────────────────────────────────
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--lifespan", "on", \
     "--workers", "1", \
     "--log-level", "info", \
     "--access-log"]
