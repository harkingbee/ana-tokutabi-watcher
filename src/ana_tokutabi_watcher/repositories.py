from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ana_tokutabi_watcher.models import CampaignSnapshot, NotificationRecord, TokuTabiRoute


def compute_raw_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_campaign_snapshot(
    session: Session,
    booking_start: object,
    booking_end: object,
    travel_start: object,
    travel_end: object,
    raw_hash: str,
    routes_data: list[dict],
) -> CampaignSnapshot:
    snap = CampaignSnapshot(
        fetched_at=datetime.now(UTC),
        booking_start=booking_start,
        booking_end=booking_end,
        travel_start=travel_start,
        travel_end=travel_end,
        raw_hash=raw_hash,
    )
    session.add(snap)
    session.flush()
    for r in routes_data:
        route = TokuTabiRoute(
            campaign_snapshot_id=snap.id,
            origin=r.get("origin", "大阪"),
            destination=r.get("destination", ""),
            destination_code=r.get("destination_code"),
            miles=r.get("miles", 0),
            route_text=r.get("route_text", ""),
        )
        session.add(route)
    session.commit()
    session.refresh(snap)
    return snap


def get_latest_snapshot(session: Session) -> CampaignSnapshot | None:
    stmt = select(CampaignSnapshot).order_by(CampaignSnapshot.id.desc()).limit(1)
    return session.execute(stmt).scalars().first()


def list_snapshots(session: Session, limit: int = 50) -> list[CampaignSnapshot]:
    """新しい順にスナップショットを返す（複数週が同時に存在しうるため一覧取得用）。"""
    stmt = select(CampaignSnapshot).order_by(CampaignSnapshot.id.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def get_snapshot_by_travel_period_and_hash(
    session: Session, travel_start: object, travel_end: object, raw_hash: str
) -> CampaignSnapshot | None:
    """同じ搭乗期間・同じページ内容(raw_hash)のスナップショットが既にあるか調べる（重複保存防止用）。"""
    stmt = (
        select(CampaignSnapshot)
        .where(
            CampaignSnapshot.travel_start == travel_start,
            CampaignSnapshot.travel_end == travel_end,
            CampaignSnapshot.raw_hash == raw_hash,
        )
        .order_by(CampaignSnapshot.id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def get_routes_for_snapshot(session: Session, snapshot_id: int) -> list[TokuTabiRoute]:
    stmt = select(TokuTabiRoute).where(TokuTabiRoute.campaign_snapshot_id == snapshot_id)
    return list(session.execute(stmt).scalars().all())


def get_notification_record(session: Session, key: str) -> NotificationRecord | None:
    stmt = select(NotificationRecord).where(NotificationRecord.notification_key == key)
    return session.execute(stmt).scalars().first()


def upsert_notification_record(session: Session, key: str, now: datetime, status: str = "sent") -> NotificationRecord:
    rec = get_notification_record(session, key)
    if rec:
        rec.last_sent_at = now
        rec.last_status = status
    else:
        rec = NotificationRecord(
            notification_key=key,
            first_sent_at=now,
            last_sent_at=now,
            last_status=status,
        )
        session.add(rec)
    session.commit()
    return rec
