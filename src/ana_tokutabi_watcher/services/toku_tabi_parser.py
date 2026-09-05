from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from ana_tokutabi_watcher.utils.dates import extract_all_periods, parse_period

RE_MILES = re.compile(r"(\d{1,2},?\d{3})\s*マイル")
RE_ROUTE_LINE = re.compile(r".*⇔.*|.*～.*|.*→.*|.*←.*")
RE_OSAKA = re.compile(r"大阪")


@dataclass
class ParsedCampaign:
    booking_start: date | None
    booking_end: date | None
    travel_start: date | None
    travel_end: date | None
    routes_by_miles: dict[int, list[str]]  # miles -> route_texts
    all_route_texts: list[str]
    osaka_route_texts: list[str]
    headings: list[str]
    raw_hash: str


def _extract_text(soup: BeautifulSoup) -> str:
    return soup.get_text(separator="\n")


def _parse_periods(text: str) -> dict[str, tuple[date | None, date | None]]:
    """テキスト全体から予約期間と搭乗期間を抽出。実ページの「から〜まで」形式に対応。"""
    result: dict[str, tuple[date | None, date | None]] = {}
    patterns = {
        "booking": ["予約発券期間"],
        "travel": ["対象搭乗期間", "搭乗期間"],
    }
    raw_lines = text.splitlines()
    # 空行を除去したインデックス付きリスト（実ページは空行が多いため）
    filtered = [(idx, ln.strip()) for idx, ln in enumerate(raw_lines) if ln.strip()]
    # フィルタ後のテキストで判定（見出しと日付が離れていても検出できるように）
    filtered_texts = [t for _, t in filtered]
    for pos, (_, line) in enumerate(filtered):
        for key, keywords in patterns.items():
            if key in result:
                continue
            if any(kw in line for kw in keywords):
                # 見出し以降のウィンドウで期間を探す（前方に含まれる別期間の誤検出を防ぐ）
                window = "\n".join(filtered_texts[pos : pos + 6])
                start, end = parse_period(window)
                if start and end:
                    result[key] = (start, end)
                else:
                    s, e = parse_period(line)
                    if s and e:
                        result[key] = (s, e)
                if key not in result and pos + 1 < len(filtered_texts):
                    for offset in (1, 2, 3, 4):
                        if pos + offset < len(filtered_texts):
                            s2, e2 = parse_period(filtered_texts[pos + offset])
                            if s2 and e2:
                                result[key] = (s2, e2)
                                break
                        if pos + offset + 1 < len(filtered_texts):
                            combined = (
                                filtered_texts[pos + offset]
                                + "から"
                                + filtered_texts[pos + offset + 1]
                            )
                            s3, e3 = parse_period(combined)
                            if s3 and e3:
                                result[key] = (s3, e3)
                                break

    # フォールバック: テキスト全体から期間候補を抽出
    if "booking" not in result or "travel" not in result:
        periods = extract_all_periods(text)
        # 「20YY年MM月DD日」のダミー期間を除外
        filtered = [(s, e) for s, e in periods if s.year != 20 or e.year != 20]
        # ダミーが混ざっている場合は除外後のリストを優先
        candidates = filtered if filtered else periods
        if candidates:
            if "booking" not in result and len(candidates) >= 1:
                result["booking"] = candidates[0]
            if "travel" not in result:
                if len(candidates) >= 2:
                    result["travel"] = candidates[1]
                elif (
                    len(candidates) == 1
                    and "booking" in result
                    and candidates[0] != result["booking"]
                ):
                    result["travel"] = candidates[0]

    # 実ページでは2つのキャンペーンブロック（9/2-9/8 と 9/9-9/15）が同居する
    # 最初のブロックのみを採用すると古い期間になる可能性があるため、
    # 「予約発券期間」が複数見つかる場合は最も未来の搭乗期間を優先するロジックを
    # 呼び出し側で扱えるよう、テキスト全体の全期間もログ用に保持する
    return result


def extract_all_campaign_blocks(
    html: str,
) -> list[dict[str, object]]:
    """HTMLから複数のキャンペーンブロック（予約期間+搭乗期間+路線）を抽出する。
    実ページでは2週間分が同居するため、ブロック単位での分解が精度向上に寄与する。
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocks: list[dict[str, object]] = []
    # 「予約発券期間」を起点にブロックを検出
    booking_indices = [i for i, ln in enumerate(lines) if "予約発券期間" in ln]
    for bi, idx in enumerate(booking_indices):
        end_idx = booking_indices[bi + 1] if bi + 1 < len(booking_indices) else len(lines)
        block_lines = lines[idx:end_idx]
        block_text = "\n".join(block_lines)
        b_start, b_end = parse_period(block_text)
        # 搭乗期間はブロック内で「対象搭乗期間」の後
        t_start: date | None = None
        t_end: date | None = None
        for j, bl in enumerate(block_lines):
            if "対象搭乗期間" in bl or "搭乗期間" in bl:
                window = "\n".join(block_lines[j : j + 6])
                t_start, t_end = parse_period(window)
                if t_start and t_end:
                    break
        # ブロック内のマイルと路線
        block_routes: dict[int, list[str]] = {}
        mile_indices = []
        for k, bl in enumerate(block_lines):
            m = RE_MILES.search(bl)
            if m:
                miles_val = int(m.group(1).replace(",", ""))
                if 2000 <= miles_val <= 15000:
                    mile_indices.append((k, miles_val))
        for mi, (s_idx, miles_val) in enumerate(mile_indices):
            e_idx = mile_indices[mi + 1][0] if mi + 1 < len(mile_indices) else len(block_lines)
            segment = block_lines[s_idx + 1 : e_idx]
            routes: list[str] = []
            for seg_line in segment:
                has_route = "⇔" in seg_line and len(seg_line) < 40
                has_jp = bool(re.search(r"[ぁ-んァ-ン一-龥]", seg_line))
                if has_route and has_jp:
                    # ノイズ除外
                    noise = ["表します", "指します", "発着を表", "マイル", "期間"]
                    if any(kw in seg_line for kw in noise):
                        continue
                    if seg_line.count("⇔") != 1:
                        continue
                    routes.append(seg_line.strip())
            if routes:
                block_routes.setdefault(miles_val, []).extend(routes)
        if b_start or t_start or block_routes:
            blocks.append(
                {
                    "booking_start": b_start,
                    "booking_end": b_end,
                    "travel_start": t_start,
                    "travel_end": t_end,
                    "routes_by_miles": block_routes,
                }
            )
    return blocks


def parse_campaign_html(html: str) -> ParsedCampaign:
    soup = BeautifulSoup(html, "lxml")
    text = _extract_text(soup)
    raw_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    # 見出し一覧（診断用）
    headings: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
        t = tag.get_text(strip=True)
        if t:
            headings.append(t[:100])

    # 期間抽出
    periods = _parse_periods(text)
    booking_start, booking_end = periods.get("booking", (None, None))
    travel_start, travel_end = periods.get("travel", (None, None))

    # 高精度: まずHTML構造ベースで路線を抽出（li.asw-list__item > p）
    routes_by_miles: dict[int, list[str]] = {}
    all_route_texts: list[str] = []

    # HTML構造ベース抽出（実ページ: ul.asw-list > li.asw-list__item > p）
    try:
        current_miles: int | None = None
        # 見出しとリストを順に走査（liは内部pと重複するためp/hのみを対象）
        for elem in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
            tag_text = elem.get_text(strip=True)
            if not tag_text:
                continue
            m = RE_MILES.search(tag_text)
            if m and elem.name in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
                if elem.name.startswith("h") or ("マイル" in tag_text and len(tag_text) < 30):
                    miles_val = int(m.group(1).replace(",", ""))
                    if 2000 <= miles_val <= 15000:
                        current_miles = miles_val
                        continue
            if current_miles and "⇔" in tag_text and elem.name == "p":
                if len(tag_text) < 50 and re.search(r"[ぁ-んァ-ン一-龥]", tag_text):
                    noise_kw = [
                        "マイル",
                        "期間",
                        "ご利用条件",
                        "対象外",
                        "変更",
                        "表します",
                        "指します",
                        "可能",
                        "運航",
                        "席数",
                        "了承",
                    ]  # noqa: E501
                    if not any(kw in tag_text for kw in noise_kw):
                        if tag_text.count("⇔") == 1 and len(tag_text) < 40:
                            # 重複除外
                            if tag_text not in routes_by_miles.get(current_miles, []):
                                routes_by_miles.setdefault(current_miles, []).append(tag_text)
                                all_route_texts.append(tag_text)
    except Exception:
        pass

    # テキストベース抽出はHTML抽出が不十分な場合のみ実行（重複回避）
    if len(all_route_texts) < 5:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        mile_indices: list[tuple[int, int]] = []
        for idx, line in enumerate(lines):
            m = RE_MILES.search(line)
            if m:
                miles_val = int(m.group(1).replace(",", ""))
                if 2000 <= miles_val <= 15000:
                    mile_indices.append((idx, miles_val))
        for mi, (start_idx, miles_val) in enumerate(mile_indices):
            end_idx = mile_indices[mi + 1][0] if mi + 1 < len(mile_indices) else len(lines)
            segment = lines[start_idx + 1 : end_idx]
            routes: list[str] = []
            for line in segment:
                if "⇔" in line or "～" in line or "→" in line:
                    if len(line) < 120 and len(line) > 2:
                        if re.search(r"[ぁ-んァ-ン一-龥]", line):
                            # ノイズ除外: 説明文は除外
                            if any(
                                kw in line
                                for kw in [
                                    "変更",
                                    "表します",
                                    "指します",
                                    "可能",
                                    "運航",
                                    "席数",
                                    "了承",
                                    "マイル",
                                ]
                            ):
                                continue
                            routes.append(line.strip())
                            all_route_texts.append(line.strip())
                elif "大阪" in line and len(line) < 80:
                    if not any(
                        kw in line
                        for kw in ["マイル", "期間", "予約", "搭乗", "ご案内", "変更", "可能"]
                    ):
                        if line.strip() not in routes:
                            routes.append(line.strip())
                            all_route_texts.append(line.strip())
            if routes:
                routes_by_miles.setdefault(miles_val, []).extend(routes)

    # フォールバック: HTML構造抽出で空の場合のみテキストベース抽出
    if not routes_by_miles:
        # 方法1: マイル見出しを順に走査し、次のマイル見出しまでの路線を収集
        mile_indices: list[tuple[int, int]] = []
        for idx, line in enumerate(lines):
            m = RE_MILES.search(line)
            if m:
                miles_val = int(m.group(1).replace(",", ""))
                if 2000 <= miles_val <= 15000:
                    mile_indices.append((idx, miles_val))
        for mi, (start_idx, miles_val) in enumerate(mile_indices):
            end_idx = mile_indices[mi + 1][0] if mi + 1 < len(mile_indices) else len(lines)
            segment = lines[start_idx + 1 : end_idx]
            routes: list[str] = []
            for line in segment:
                if "⇔" in line or "～" in line or "→" in line:
                    if len(line) < 120 and len(line) > 2:
                        if re.search(r"[ぁ-んァ-ン一-龥]", line):
                            routes.append(line.strip())
                            all_route_texts.append(line.strip())
                elif "大阪" in line and len(line) < 80:
                    if not any(kw in line for kw in ["マイル", "期間", "予約", "搭乗", "ご案内"]):
                        if line.strip() not in routes:
                            routes.append(line.strip())
                            all_route_texts.append(line.strip())
            if routes:
                routes_by_miles.setdefault(miles_val, []).extend(routes)
    # それでも空なら「大阪⇔」のみ抽出
    if not routes_by_miles:
        for line in lines:
            if "大阪" in line and ("⇔" in line or "～" in line):
                if len(line) < 120:
                    all_route_texts.append(line.strip())
        if all_route_texts:
            miles_candidates = [int(m.replace(",", "")) for m in RE_MILES.findall(text)]
            fallback_miles = miles_candidates[0] if miles_candidates else 5500
            routes_by_miles[fallback_miles] = list(dict.fromkeys(all_route_texts))

    # ブロック単位の精度補正: 実ページでは2週間分が同居するため、
    # 検出した travel_start に一致するブロックの路線のみを採用することで精度向上
    try:
        blocks = extract_all_campaign_blocks(html)
        if blocks and travel_start and booking_start:
            for b in blocks:
                if (
                    b.get("travel_start") == travel_start
                    and b.get("booking_start") == booking_start
                ):
                    # 該当ブロックの路線で上書き（ブロック内の路線がより正確）
                    block_routes = b.get("routes_by_miles")  # type: ignore[assignment]
                    if block_routes:
                        # ブロック内の路線は既に正確に分離されているため採用
                        # ただしブロック内の路線が空の場合はマージ結果を保持
                        filtered_routes: dict[int, list[str]] = {}
                        for miles, rts in block_routes.items():  # type: ignore[union-attr]
                            filtered_routes[miles] = rts  # type: ignore[assignment]
                        # ブロック採用時は全路線と大阪路線を再構築
                        if any(filtered_routes.values()):
                            routes_by_miles = filtered_routes
                            all_route_texts = [r for lst in filtered_routes.values() for r in lst]
                    break
    except Exception:
        pass

    # 大阪関連のみ抽出
    osaka_route_texts: list[str] = []
    for routes in routes_by_miles.values():
        for r in routes:
            if "大阪" in r:
                osaka_route_texts.append(r)
    # 全体からの大阪抽出（重複除去）
    osaka_route_texts = list(dict.fromkeys(osaka_route_texts))

    return ParsedCampaign(
        booking_start=booking_start,
        booking_end=booking_end,
        travel_start=travel_start,
        travel_end=travel_end,
        routes_by_miles=routes_by_miles,
        all_route_texts=list(dict.fromkeys(all_route_texts)),
        osaka_route_texts=osaka_route_texts,
        headings=headings,
        raw_hash=raw_hash,
    )
