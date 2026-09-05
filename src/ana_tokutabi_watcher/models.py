from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CampaignSnapshot(Base):
    __tablename__ = "campaign_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    booking_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    booking_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    travel_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    travel_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    routes: Mapped[list[TokuTabiRoute]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class TokuTabiRoute(Base):
    __tablename__ = "toku_tabi_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_snapshots.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. 大阪
    destination: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. 札幌（新千歳）
    destination_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    miles: Mapped[int] = mapped_column(Integer, nullable=False)
    route_text: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign: Mapped[CampaignSnapshot] = relationship(back_populates="routes")


class AvailabilityObservation(Base):
    __tablename__ = "availability_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("toku_tabi_routes.id"), nullable=True)
    travel_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    flight_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationRecord(Base):
    __tablename__ = "notification_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    first_sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent")
