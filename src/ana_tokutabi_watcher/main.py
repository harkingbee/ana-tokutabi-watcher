from __future__ import annotations

import json
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import typer
from sqlalchemy.orm import Session

from ana_tokutabi_watcher.clients.ana_public_page_client import fetch_campaign_page
from ana_tokutabi_watcher.config import (
    AppConfig,
    get_database_url,
    get_discord_webhook_url,
    load_config,
)
from ana_tokutabi_watcher.database import get_session_factory
from ana_tokutabi_watcher.logging_config import get_logger, setup_logging
from ana_tokutabi_watcher.repositories import (
    compute_raw_hash,
    get_latest_snapshot,
    get_routes_for_snapshot,
    save_campaign_snapshot,
)
from ana_tokutabi_watcher.scheduler import is_booking_window_active
from ana_tokutabi_watcher.services.availability_checker import (
    BrowserAvailabilityChecker,
    SafeLinkOnlyAvailabilityChecker,
)
from ana_tokutabi_watcher.services.discord_notifier import (
    build_discord_payload,
    send_discord_notification,
    send_simple_text,
)
from ana_tokutabi_watcher.services.notification_deduplicator import (
    build_notification_key,
    mark_notified,
    should_notify,
)
from ana_tokutabi_watcher.services.route_normalizer import normalize_all_osaka_routes
from ana_tokutabi_watcher.services.toku_tabi_parser import parse_campaign_html
from ana_tokutabi_watcher.utils.dates import format_date_with_weekday, generate_dates

JST = ZoneInfo("Asia/Tokyo")
app = typer.Typer(add_completion=False, help="ANAトクたびマイル 大阪発着監視 CLI")

logger = get_logger(__name__)


def _get_config_and_logger(config_path: str | None) -> tuple[AppConfig, object]:
    cfg = load_config(config_path)
    # ログ設定
    from ana_tokutabi_watcher.config import get_log_format, get_log_level

    level = get_log_level(cfg)
    fmt = get_log_format(cfg)
    setup_logging(level=level, fmt=fmt)
    return cfg, get_logger("ana_tokutabi_watcher.main")


def _get_session(database_url: str | None = None) -> Session:
    url = database_url or get_database_url()
    factory = get_session_factory(url)
    return factory()


@app.command("fetch-routes")
def fetch_routes(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
    dry_run: bool = typer.Option(False, "--dry-run", help="保存せず表示のみ"),
) -> None:
    """公式ページから対象路線を取得して保存する。"""
    cfg, log = _get_config_and_logger(config_path)
    try:
        html, h = fetch_campaign_page(url=cfg.campaign_url)
    except Exception as e:
        log.error("fetch_failed", error=str(e))  # type: ignore[attr-defined]
        raise typer.Exit(1) from e

    parsed = parse_campaign_html(html)
    normalized = normalize_all_osaka_routes(parsed.routes_by_miles, parsed.travel_start, parsed.travel_end)

    # フィルタ: allowlist / blocklist
    allow = set(cfg.monitor.destination_allowlist)
    block = set(cfg.monitor.destination_blocklist)
    if allow:
        normalized = [
            r
            for r in normalized
            if any(code in allow for code in r["destination_airports"]) or r["destination_name"] in allow
        ]
    if block:
        normalized = [
            r
            for r in normalized
            if not any(code in block for code in r["destination_airports"]) and r["destination_name"] not in block
        ]

    log.info(  # type: ignore[attr-defined]
        "parsed_result",
        booking_start=str(parsed.booking_start),
        booking_end=str(parsed.booking_end),
        travel_start=str(parsed.travel_start),
        travel_end=str(parsed.travel_end),
        osaka_routes=len(normalized),
        headings=parsed.headings[:5],
    )

    if dry_run:
        print(json.dumps(normalized, ensure_ascii=False, indent=2))
        return

    raw_hash = compute_raw_hash(html)
    session = _get_session()
    try:
        routes_data = []
        for r in normalized:
            routes_data.append(
                {
                    "origin": r["origin_area"],
                    "destination": r["destination_name"],
                    "destination_code": r["destination_airports"][0] if r["destination_airports"] else None,
                    "miles": r["miles"],
                    "route_text": r["route_text"],
                }
            )
        snap = save_campaign_snapshot(
            session,
            booking_start=parsed.booking_start,
            booking_end=parsed.booking_end,
            travel_start=parsed.travel_start,
            travel_end=parsed.travel_end,
            raw_hash=raw_hash,
            routes_data=routes_data,
        )
        print(f"保存完了: snapshot_id={snap.id} 路線数={len(routes_data)}")
        for r in normalized:
            rp = f"{r['travel_period_start']}〜{r['travel_period_end']}"
            print(f"  - {r['route_text']} {r['miles']}マイル 搭乗期間:{rp}")
    finally:
        session.close()


@app.command("show-routes")
def show_routes(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
) -> None:
    """保存済みの最新路線を表示する。"""
    cfg, _ = _get_config_and_logger(config_path)
    _ = cfg
    session = _get_session()
    try:
        snap = get_latest_snapshot(session)
        if not snap:
            print("保存されたスナップショットがありません。fetch-routes を実行してください。")
            raise typer.Exit(0)
        routes = get_routes_for_snapshot(session, snap.id)
        print(f"スナップショットID: {snap.id}")
        print(f"取得時刻: {snap.fetched_at}")
        print(
            f"予約発券期間: {format_date_with_weekday(snap.booking_start)} 〜 "
            f"{format_date_with_weekday(snap.booking_end)}"
        )
        print(
            f"対象搭乗期間: {format_date_with_weekday(snap.travel_start)} 〜 "
            f"{format_date_with_weekday(snap.travel_end)}"
        )
        print(f"路線数: {len(routes)}")
        print("-" * 60)
        for r in routes:
            print(f"  {r.route_text}  {r.miles:,}マイル  ({r.origin} → {r.destination})")
    finally:
        session.close()


@app.command("check-availability")
def check_availability(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Discord送信せず表示のみ"),
) -> None:
    """空席監視を実行する（予約期間外はスキップ）。"""
    cfg, log = _get_config_and_logger(config_path)
    session = _get_session()
    try:
        snap = get_latest_snapshot(session)
        if not snap:
            print("スナップショットがありません。fetch-routes を先に実行してください。")
            raise typer.Exit(1)

        today = datetime.now(JST).date()
        if cfg.schedule.availability_check.enabled_during_booking_window_only:
            if not is_booking_window_active(snap.booking_start, snap.booking_end, today):
                msg = (
                    f"予約発券期間外のためスキップします"
                    f"（期間: {snap.booking_start}〜{snap.booking_end}, 今日: {today}）"
                )
                print(msg)
                log.info("skip_outside_booking_window", today=str(today))  # type: ignore[attr-defined]
                return

        routes = get_routes_for_snapshot(session, snap.id)
        if not routes:
            print("大阪発着の対象路線がありません。")
            return

        # 期間の日付を生成
        if snap.travel_start and snap.travel_end:
            travel_dates = generate_dates(snap.travel_start, snap.travel_end)
        else:
            # 期間不明なら直近7日間を対象
            travel_dates = generate_dates(today, date.fromordinal(today.toordinal() + 6))

        # チェッカー選択
        if cfg.availability_mode == "browser_public_only":
            checker: SafeLinkOnlyAvailabilityChecker | BrowserAvailabilityChecker = BrowserAvailabilityChecker(
                enabled=False
            )
            is_safe = True  # デフォルト無効なのでsafe扱い
        elif cfg.availability_mode == "custom_api":
            # custom_api はプロトコル枠のみ。実エンドポイント未設定ならsafeへフォールバック
            log.warning("custom_api_not_configured_fallback_to_safe")  # type: ignore[attr-defined]
            checker = SafeLinkOnlyAvailabilityChecker()
            is_safe = True
        else:
            checker = SafeLinkOnlyAvailabilityChecker()
            is_safe = True

        webhook_url = get_discord_webhook_url(cfg)
        username = cfg.discord.username
        max_n = cfg.monitor.max_notifications_per_run
        resend_hours = cfg.monitor.resend_after_hours
        min_sleep = cfg.rate_limit.min_seconds_between_requests
        max_req = cfg.rate_limit.max_requests_per_run

        sent = 0
        checked = 0

        # 到着地コード解決のため services/route_normalizer のマップを使う
        from ana_tokutabi_watcher.services.route_normalizer import CITY_TO_AIRPORTS

        for route in routes:
            dest_codes = CITY_TO_AIRPORTS.get(route.destination, [])
            # DBのdestination_codeを優先
            if route.destination_code:
                dest_codes = [route.destination_code]
            if not dest_codes:
                # コード不明でも検索URL生成はする
                dest_codes = ["UNKNOWN"]

            for travel_date in travel_dates:
                for dest_code in dest_codes[:1]:  # 代表1コードでリンク生成（重複回避）
                    if checked >= max_req:
                        log.info("max_requests_per_run_reached", max_req=max_req)  # type: ignore[attr-defined]
                        break
                    # 時間帯フィルタは safe_link_only ではリンク生成のみなのでスキップ

                    for origin_code in cfg.monitor.origins:
                        origin = origin_code
                        result = checker.check(
                            origin=origin,
                            destination=dest_code,
                            destination_name=route.destination,
                            travel_date=travel_date,
                            miles=route.miles,
                        )
                        checked += 1

                        # 重複排除
                        key = build_notification_key(
                            origin=origin,
                            destination=dest_code,
                            travel_date=travel_date.isoformat(),
                            flight_number=result.flight_number,
                            departure_time=result.departure_time,
                            arrival_time=result.arrival_time,
                            miles=route.miles,
                        )
                        current_status = result.status
                        if not should_notify(session, key, current_status, resend_after_hours=resend_hours):
                            log.info("skip_duplicate", key=key[:12])  # type: ignore[attr-defined]
                            continue

                        if sent >= max_n:
                            log.info("max_notifications_per_run_reached", max_n=max_n)  # type: ignore[attr-defined]
                            break

                        payload = build_discord_payload(result, username=username, is_safe_mode=is_safe)
                        if dry_run or cfg.monitor.max_notifications_per_run == 0:
                            print(json.dumps(payload, ensure_ascii=False, indent=2))
                        else:
                            if cfg.discord.enabled:
                                try:
                                    send_discord_notification(
                                        webhook_url,
                                        result,
                                        username=username,
                                        is_safe_mode=is_safe,
                                        dry_run=False,
                                    )
                                except Exception as e:
                                    log.error("notify_failed", error=str(e))  # type: ignore[attr-defined]
                                    continue
                            else:
                                print(json.dumps(payload, ensure_ascii=False, indent=2))

                        mark_notified(session, key, current_status)
                        sent += 1

                        if min_sleep > 0 and not dry_run:
                            time.sleep(min_sleep)

                    if sent >= max_n or checked >= max_req:
                        break
                if sent >= max_n or checked >= max_req:
                    break
            if sent >= max_n or checked >= max_req:
                break

        print(f"監視完了: checked={checked} sent={sent} safe_mode={is_safe}")
    finally:
        session.close()


@app.command("run-scheduler")
def run_scheduler(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
) -> None:
    """APSchedulerで常駐実行する。"""
    cfg, log = _get_config_and_logger(config_path)

    def fetch_job() -> None:
        log.info("scheduler_fetch_job_start")  # type: ignore[attr-defined]
        try:
            fetch_routes(config_path=config_path, dry_run=False)
        except SystemExit:
            pass
        except Exception as e:
            log.error("scheduler_fetch_job_failed", error=str(e))  # type: ignore[attr-defined]

    def check_job() -> None:
        log.info("scheduler_check_job_start")  # type: ignore[attr-defined]
        try:
            check_availability(config_path=config_path, dry_run=False)
        except SystemExit:
            pass
        except Exception as e:
            log.error("scheduler_check_job_failed", error=str(e))  # type: ignore[attr-defined]

    from ana_tokutabi_watcher.scheduler import create_scheduler

    scheduler = create_scheduler(cfg, fetch_job, check_job)
    scheduler.start()
    print("スケジューラー起動中... Ctrl+C で終了")
    log.info("scheduler_started")  # type: ignore[attr-defined]
    try:
        import time as _time

        while True:
            _time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("スケジューラーを停止しました。")


@app.command("test-discord")
def test_discord(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
    dry_run: bool = typer.Option(False, "--dry-run", help="送信せず表示"),
) -> None:
    """Discordへテスト通知を1回送る。"""
    cfg, _ = _get_config_and_logger(config_path)
    webhook_url = get_discord_webhook_url(cfg)
    if not webhook_url and not dry_run:
        print("DISCORD_WEBHOOK_URL が未設定です。.env を確認してください。")
        raise typer.Exit(1)
    content = "ANAトクたび監視: テスト通知です。正常に接続されています。"
    send_simple_text(webhook_url, content, username=cfg.discord.username, dry_run=dry_run)
    if not dry_run:
        print("テスト通知を送信しました。")


@app.command("dry-run")
def dry_run_cmd(
    config_path: str | None = typer.Option(None, "--config", help="config.yaml のパス"),
) -> None:
    """Discordへ送信せず、送信予定のEmbedを表示する。"""
    print("=== fetch-routes (dry-run) ===")
    try:
        fetch_routes(config_path=config_path, dry_run=True)
    except SystemExit:
        pass
    print("\n=== check-availability (dry-run) ===")
    try:
        check_availability(config_path=config_path, dry_run=True)
    except SystemExit:
        pass


if __name__ == "__main__":
    app()
