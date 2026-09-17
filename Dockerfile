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
# أمر التشغيل:
#   -k uvicorn.workers.UvicornWorker  → ASGI worker
#   --lifespan on                      → يفعّل lifespan(app)
#   --capture-output                   → يلتقط stdout/stderr من الـ workers
#   --access-logfile -                 → access logs إلى stdout
#   --error-logfile -                  → error logs إلى stderr
#   --log-level info                   → مستوى السجلات
#   -w 4                               → 4 workers
# ─────────────────────────────────────────────────────
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "-b", "0.0.0.0:8000", \
     "--lifespan", "on", \
     "--capture-output", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--timeout", "120"]
