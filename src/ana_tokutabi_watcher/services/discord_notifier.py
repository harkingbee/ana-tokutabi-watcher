from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from ana_tokutabi_watcher.logging_config import get_logger
from ana_tokutabi_watcher.services.availability_checker import AvailabilityResult

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def build_discord_embed(
    result: AvailabilityResult,
    username: str = "ANAトクたび監視",
    is_safe_mode: bool = True,
) -> dict:
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    route_label = f"{result.origin} ⇔ {result.destination_name or result.destination}"
    travel_date_str = result.travel_date.isoformat()

    fields = [
        {"name": "路線", "value": route_label, "inline": True},
        {"name": "出発日", "value": travel_date_str, "inline": True},
        {"name": "必要マイル", "value": f"{result.miles:,} マイル", "inline": True},
    ]
    if result.departure_time or result.arrival_time:
        time_val = f"{result.departure_time or '-'} → {result.arrival_time or '-'}"
        fields.append({"name": "時刻", "value": time_val, "inline": True})
    if result.flight_number:
        fields.append({"name": "便名", "value": result.flight_number, "inline": True})
    fields.append({"name": "検知時刻", "value": now_jst, "inline": True})

    description = "空席・必要マイルは変動するため、ANA公式サイトで最終確認してください。"
    if is_safe_mode or result.status == "link_only":
        description = "自動空席確認は行わず、対象路線を検出しました。リンク先で空席をご確認ください。\n" + description
        title = "ANAトクたびマイル：対象路線を検知（要手動確認）"
        color = 0x3498DB  # blue
    elif result.status == "available":
        title = "ANAトクたびマイル：空席を検知"
        color = 0x2ECC71  # green
    else:
        title = "ANAトクたびマイル：空席確認結果"
        color = 0x95A5A6

    embed: dict = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": "ANAトクたび監視 • 情報は公式サイトで最終確認してください"},
    }
    if result.search_url:
        embed["url"] = result.search_url
        fields.append({"name": "ANA公式で確認", "value": result.search_url, "inline": False})

    return embed


def build_discord_payload(
    result: AvailabilityResult,
    username: str = "ANAトクたび監視",
    is_safe_mode: bool = True,
) -> dict:
    embed = build_discord_embed(result, username=username, is_safe_mode=is_safe_mode)
    return {
        "username": username,
        "embeds": [embed],
    }


def send_discord_notification(
    webhook_url: str,
    result: AvailabilityResult,
    username: str = "ANAトクたび監視",
    is_safe_mode: bool = True,
    dry_run: bool = False,
) -> dict | None:
    payload = build_discord_payload(result, username=username, is_safe_mode=is_safe_mode)
    if dry_run:
        logger.info("discord_dry_run", payload=json.dumps(payload, ensure_ascii=False))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    if not webhook_url:
        logger.warning("discord_webhook_url_missing_skip")
        return None

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("discord_sent", status_code=resp.status_code)
            return payload
    except Exception as e:
        logger.error("discord_send_failed", error=str(e))
        raise


def send_simple_text(webhook_url: str, content: str, username: str = "ANAトクたび監視", dry_run: bool = False) -> None:
    payload = {"username": username, "content": content}
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if not webhook_url:
        logger.warning("discord_webhook_url_missing_skip_simple")
        return
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()
