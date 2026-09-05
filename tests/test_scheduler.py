from datetime import date

from ana_tokutabi_watcher.config import AppConfig
from ana_tokutabi_watcher.scheduler import create_scheduler, is_booking_window_active


def test_is_booking_window_active_inside():
    assert is_booking_window_active(date(2026, 4, 1), date(2026, 4, 7), date(2026, 4, 3)) is True


def test_is_booking_window_active_outside():
    assert is_booking_window_active(date(2026, 4, 1), date(2026, 4, 7), date(2026, 4, 10)) is False


def test_is_booking_window_unknown_returns_true():
    assert is_booking_window_active(None, None, date(2026, 4, 10)) is True


def test_create_scheduler_has_jobs():
    cfg = AppConfig()
    scheduler = create_scheduler(cfg, lambda: None, lambda: None)
    job_ids = {j.id for j in scheduler.get_jobs()}
    assert "weekly_route_fetch_main" in job_ids
    assert "hourly_availability_check" in job_ids
    # retries
    assert "weekly_route_fetch_retry_0" in job_ids
