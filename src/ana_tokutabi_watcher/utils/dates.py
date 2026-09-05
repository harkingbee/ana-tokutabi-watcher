from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 日本語の日付パターン: 2026年4月3日(木) / 2026/04/03 / 4月3日 など
RE_JP_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_JP_DATE_SHORT = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_ISO_DATE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
RE_PERIOD = re.compile(
    r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}[-/]\d{1,2}[-/]\d{1,2})"
    r"\s*(?:（[^）]*）|\([^)]*\))?\s*"
    r"(?:[0-9]{1,2}:[0-9]{2})?\s*"
    r"[〜～\-－―—から]+"
    r"\s*(?:（[^）]*）|\([^)]*\))?\s*"
    r"(?:[0-9]{1,2}:[0-9]{2})?\s*"
    r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}[-/]\d{1,2}[-/]\d{1,2})"
)
# 「から」区切りを明示的に扱う（0:00/23:59などの時刻を含む場合に対応）
RE_PERIOD_KARA = re.compile(
    r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)(?:\s*（[^）]*）)?(?:\s*\d{1,2}:\d{2})?\s*から\s*"
    r"(?:\d{4}\s*年\s*)?(\d{1,2}\s*月\s*\d{1,2}\s*日)"
)
RE_PERIOD_TILDE = re.compile(
    r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)(?:\s*（[^）]*）)?\s*[〜～\-－―—]+\s*"
    r"(?:\d{4}\s*年\s*)?(\d{1,2}\s*月\s*\d{1,2}\s*日)"
)


def parse_jp_date(text: str, default_year: int | None = None) -> date | None:
    text = text.strip()
    m = RE_JP_DATE.search(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = RE_ISO_DATE.search(text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = RE_JP_DATE_SHORT.search(text)
    if m and default_year:
        return date(default_year, int(m.group(1)), int(m.group(2)))
    return None


def parse_period(text: str) -> tuple[date | None, date | None]:
    """「2026年4月3日〜2026年4月9日」「2026年8月26日0:00から9月1日23:59まで」などの期間をパース。"""
    # まず「から」区切りを試す（時刻付きの実ページ形式に対応）
    m = RE_PERIOD_KARA.search(text)
    if m:
        start_s, end_s = m.group(1), m.group(2)
        start = parse_jp_date(start_s)
        if start:
            # end_s は「9月1日」のように年なし → 開始年を補完
            # 月が開始より小さい場合は年跨ぎを考慮
            end = parse_jp_date(end_s, default_year=start.year)
            if end and end.month < start.month and start.month >= 10:
                # 年跨ぎ (例: 12月31日 から 1月5日)

                try:
                    end = date(start.year + 1, end.month, end.day)
                except ValueError:
                    pass
            if start and end:
                return start, end
    m = RE_PERIOD_TILDE.search(text)
    if m:
        start_s, end_s = m.group(1), m.group(2)
        start = parse_jp_date(start_s)
        if start:
            end = parse_jp_date(end_s, default_year=start.year)
            if start and end:
                return start, end
    # 汎用RE_PERIODでフォールバック
    m = RE_PERIOD.search(text)
    if not m:
        return None, None
    start_s, end_s = m.group(1), m.group(2)
    start = parse_jp_date(start_s)
    if start:
        end = parse_jp_date(end_s, default_year=start.year)
    else:
        end = parse_jp_date(end_s)
    return start, end


def extract_all_periods(text: str) -> list[tuple[date, date]]:
    """テキスト中の全期間を抽出（重複除去、順序保持）。"""
    periods: list[tuple[date, date]] = []
    seen: set[tuple[date, date]] = set()
    # 複数の正規表現を順に試す
    for pat in (RE_PERIOD_KARA, RE_PERIOD_TILDE, RE_PERIOD):
        for m in pat.finditer(text):
            s, e = parse_period(m.group(0))
            if s and e and (s, e) not in seen:
                seen.add((s, e))
                periods.append((s, e))
    # 出現順にソート（テキスト上の出現順を保持するため、開始日順ではなく発見順）
    return periods


def generate_dates(start: date, end: date) -> list[date]:
    if start > end:
        return []
    result: list[date] = []
    cur = start
    while cur <= end:
        result.append(cur)
        cur += timedelta(days=1)
    return result


def now_jst() -> datetime:
    return datetime.now(JST)


def is_within_booking_window(
    now: date, booking_start: date | None, booking_end: date | None
) -> bool:
    if booking_start is None or booking_end is None:
        return True  # 不明なら監視を継続（安全側）
    return booking_start <= now <= booking_end
