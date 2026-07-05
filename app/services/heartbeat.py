"""خدمة زاوية التنشيط: تحقق دوري من يقظة قاعدة البيانات/السيرفر."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.database.session import AsyncSessionLocal
from app.models.heartbeat import HeartbeatLog

log = logging.getLogger("app.heartbeat")

INTERVAL_SECONDS = 7 * 60  # 7 دقائق
MAX_LOG_ROWS = 200  # الاحتفاظ بآخر 200 سجل فقط لتفادي تضخم الجدول


class HeartbeatState:
    def __init__(self) -> None:
        self.app_started_at: datetime = datetime.now(timezone.utc)
        self.last_checked_at: datetime | None = None
        self.last_success: bool | None = None
        self.next_run_at: datetime | None = None
        self.total_checks: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0
        self.last_error: str | None = None
        self.running: bool = False


state = HeartbeatState()
_task: asyncio.Task | None = None


async def _ping_once() -> None:
    started = time.perf_counter()
    success = True
    error: str | None = None
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        success = False
        error = str(exc)[:500]
        log.warning("⚠️  فشل نبض التحقق من قاعدة البيانات: %s", exc)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    now = datetime.now(timezone.utc)
    state.last_checked_at = now
    state.last_success = success
    state.total_checks += 1
    if success:
        state.success_count += 1
        state.last_error = None
    else:
        state.failure_count += 1
        state.last_error = error

    try:
        async with AsyncSessionLocal() as db:
            db.add(HeartbeatLog(success=success, latency_ms=latency_ms, error=error))
            await db.commit()
            # تنظيف السجلات القديمة (الاحتفاظ بآخر MAX_LOG_ROWS فقط)
            old_ids = (await db.execute(
                text(
                    "SELECT id FROM heartbeat_logs ORDER BY checked_at DESC "
                    "OFFSET :limit"
                ),
                {"limit": MAX_LOG_ROWS},
            )).scalars().all()
            if old_ids:
                await db.execute(
                    text("DELETE FROM heartbeat_logs WHERE id = ANY(:ids)"),
                    {"ids": list(old_ids)},
                )
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("تعذر تسجيل نبض التحقق في قاعدة البيانات: %s", exc)


async def _loop() -> None:
    state.running = True
    log.info("✓ بدأت خدمة زاوية التنشيط (كل %s دقائق)", INTERVAL_SECONDS // 60)
    try:
        while True:
            await _ping_once()
            state.next_run_at = datetime.now(timezone.utc).timestamp() + INTERVAL_SECONDS
            state.next_run_at = datetime.fromtimestamp(state.next_run_at, tz=timezone.utc)
            await asyncio.sleep(INTERVAL_SECONDS)
    except asyncio.CancelledError:
        state.running = False
        log.info("تم إيقاف خدمة زاوية التنشيط")
        raise


def start() -> None:
    global _task
    if _task is None or _task.done():
        state.app_started_at = datetime.now(timezone.utc)
        state.next_run_at = datetime.now(timezone.utc)
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
