from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ana_tokutabi_watcher.config import AppConfig
from ana_tokutabi_watcher.logging_config import get_logger

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def create_scheduler(config: AppConfig, fetch_fn, check_fn) -> BackgroundScheduler:  # type: ignore[no-untyped-def]
    scheduler = BackgroundScheduler(timezone=config.timezone)

    # 水曜の路線取得ジョブ
    w = config.schedule.weekly_route_fetch
    # メイン
    scheduler.add_job(
        fetch_fn,
        trigger=CronTrigger(day_of_week=w.day_of_week, hour=w.hour, minute=w.minute, timezone=JST),
        id="weekly_route_fetch_main",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    # リトライ（00:01, 00:05, 00:15）
    for idx, t in enumerate(w.retries):
        try:
            hh, mm = t.split(":")
            scheduler.add_job(
                fetch_fn,
                trigger=CronTrigger(
                    day_of_week=w.day_of_week, hour=int(hh), minute=int(mm), timezone=JST
                ),
                id=f"weekly_route_fetch_retry_{idx}",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
        except Exception as e:
            logger.warning("invalid_retry_time", retry=t, error=str(e))

    # 毎時00分の空席監視（予約発券期間中のみ、は check_fn 内で判定）
    avail = config.schedule.availability_check
    scheduler.add_job(
        check_fn,
        trigger=CronTrigger(minute=avail.minute, timezone=JST),
        id="hourly_availability_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    return scheduler


def is_booking_window_active(
    booking_start: date | None, booking_end: date | None, today: date | None = None
) -> bool:
    if booking_start is None or booking_end is None:
        return True
    if today is None:
        today = datetime.now(JST).date()
    return booking_start <= today <= booking_end
