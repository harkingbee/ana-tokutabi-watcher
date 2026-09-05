from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ana_tokutabi_watcher.repositories import get_notification_record, upsert_notification_record

JST = ZoneInfo("Asia/Tokyo")


def build_notification_key(
    origin: str,
    destination: str,
    travel_date: str,
    flight_number: str | None,
    departure_time: str | None,
    arrival_time: str | None,
    miles: int,
) -> str:
    raw = "|".join(
        [
            origin or "",
            destination or "",
            travel_date or "",
            flight_number or "",
            departure_time or "",
            arrival_time or "",
            str(miles),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def should_notify(
    session: Session,
    key: str,
    current_status: str,
    resend_after_hours: int = 24,
    now: datetime | None = None,
) -> bool:
    """重複排除ロジック。
    - 未通知なら通知する
    - 前回が「なし」→今回「あり」なら即時通知
    - 同じ空席の再通知は resend_after_hours 経過後のみ
    """
    if now is None:
        now = datetime.now(JST)
    rec = get_notification_record(session, key)
    if rec is None:
        return True
    # ステータス変化: 前回なし→今回あり は即時
    if rec.last_status in ("unavailable", "unknown", "none") and current_status in (
        "available",
        "link_only",
    ):
        return True
    # 同一ステータスの再通知は間隔を空ける
    last = rec.last_sent_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=JST)
    elapsed = now - last
    threshold = timedelta(hours=resend_after_hours)
    return elapsed >= threshold


def mark_notified(session: Session, key: str, status: str, now: datetime | None = None) -> None:
    if now is None:
        now = datetime.now(JST)
    upsert_notification_record(session, key, now, status=status)
