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
# ملاحظة: --lifespan ليس وسيطاً لـ Gunicorn.
# نستخدم app.uvicorn_worker.LifespanUvicornWorker لتفعيله.
# ─────────────────────────────────────────────────────
CMD ["gunicorn", "app.main:app", \
     "-k", "app.uvicorn_worker.LifespanUvicornWorker", \
     "-w", "2", \
     "-b", "0.0.0.0:8000", \
     "--capture-output", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--timeout", "120"]
