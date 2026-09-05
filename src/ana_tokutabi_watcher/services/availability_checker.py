from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ana_tokutabi_watcher.utils.urls import build_safe_search_url


@dataclass
class AvailabilityResult:
    origin: str
    destination: str
    destination_name: str
    travel_date: date
    miles: int
    status: str  # "available" | "unavailable" | "unknown" | "link_only"
    flight_number: str | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    search_url: str = ""
    raw_summary: str = ""


class AvailabilityCheckerProtocol(Protocol):
    def check(
        self,
        origin: str,
        destination: str,
        destination_name: str,
        travel_date: date,
        miles: int,
    ) -> AvailabilityResult: ...


class SafeLinkOnlyAvailabilityChecker:
    """空席自動確認はせず、公式検索URLを生成する安全モード。"""

    def check(
        self,
        origin: str,
        destination: str,
        destination_name: str,
        travel_date: date,
        miles: int,
    ) -> AvailabilityResult:
        url = build_safe_search_url(origin=origin, destination=destination, travel_date=travel_date, miles=miles)
        summary = f"{origin}→{destination} {travel_date.isoformat()} {miles}マイル (要手動確認)"
        return AvailabilityResult(
            origin=origin,
            destination=destination,
            destination_name=destination_name,
            travel_date=travel_date,
            miles=miles,
            status="link_only",
            search_url=url,
            raw_summary=summary,
        )


class BrowserAvailabilityChecker:
    """将来のPlaywright連携用。デフォルト無効。"""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._fallback = SafeLinkOnlyAvailabilityChecker()

    def check(
        self,
        origin: str,
        destination: str,
        destination_name: str,
        travel_date: date,
        miles: int,
    ) -> AvailabilityResult:
        if not self.enabled:
            return self._fallback.check(origin, destination, destination_name, travel_date, miles)
        # CAPTCHA/bot検知時は即時フォールバック
        raise NotImplementedError("browser_public_only は未実装です。safe_link_only を使用してください。")
