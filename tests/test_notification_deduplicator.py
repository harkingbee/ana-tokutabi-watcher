from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ana_tokutabi_watcher.models import Base
from ana_tokutabi_watcher.services.notification_deduplicator import (
    build_notification_key,
    mark_notified,
    should_notify,
)

JST = ZoneInfo("Asia/Tokyo")


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    return factory()


def test_build_notification_key_deterministic():
    k1 = build_notification_key("ITM", "CTS", "2026-04-10", "NH123", "08:00", "09:40", 5500)
    k2 = build_notification_key("ITM", "CTS", "2026-04-10", "NH123", "08:00", "09:40", 5500)
    assert k1 == k2
    assert len(k1) == 64


def test_should_notify_first_time():
    session = _make_session()
    key = build_notification_key("ITM", "CTS", "2026-04-10", None, None, None, 5500)
    assert should_notify(session, key, "link_only", resend_after_hours=24) is True


def test_should_notify_duplicate_within_window():
    session = _make_session()
    key = build_notification_key("ITM", "CTS", "2026-04-10", None, None, None, 5500)
    now = datetime.now(JST)
    mark_notified(session, key, "link_only", now=now)
    # 1時間後は再通知しない
    assert (
        should_notify(
            session, key, "link_only", resend_after_hours=24, now=now + timedelta(hours=1)
        )
        is False
    )
    # 25時間後は再通知する
    assert (
        should_notify(
            session, key, "link_only", resend_after_hours=24, now=now + timedelta(hours=25)
        )
        is True
    )


def test_status_change_none_to_available_notifies_immediately():
    session = _make_session()
    key = build_notification_key("ITM", "CTS", "2026-04-10", None, None, None, 5500)
    now = datetime.now(JST)
    mark_notified(session, key, "unavailable", now=now)
    # 1時間後でも available になれば通知
    assert (
        should_notify(
            session, key, "available", resend_after_hours=24, now=now + timedelta(hours=1)
        )
        is True
    )
    assert (
        should_notify(
            session, key, "link_only", resend_after_hours=24, now=now + timedelta(hours=1)
        )
        is True
    )
