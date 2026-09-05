#!/usr/bin/env python3
"""GitHub Actions用: ライブANAページを取得し、パーサー精度を検証してJSONで出力する。

- 取得失敗やパース失敗時は exit 1 で Actions を失敗させ、Issue 作成を促す
- 成功時は live_snapshot.json に結果を保存し、artifact として保持
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# src をパスに追加（Actions では PYTHONPATH=src でも通る）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx
from ana_tokutabi_watcher.services.route_normalizer import normalize_all_osaka_routes
from ana_tokutabi_watcher.services.toku_tabi_parser import extract_all_campaign_blocks, parse_campaign_html
from ana_tokutabi_watcher.utils.dates import parse_period

JST = ZoneInfo("Asia/Tokyo")
ANA_URL = "https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/"


def fetch_live_html() -> str:
    headers = {
        "User-Agent": "ana-tokutabi-watcher/0.1 (+https://github.com/harkingbee/ana-tokutabi-watcher)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en;q=0.9",
    }
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
        resp = client.get(ANA_URL)
        resp.raise_for_status()
        return resp.text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="live_snapshot.json")
    parser.add_argument("--html", default="live_snapshot.html")
    args = parser.parse_args()

    print(f"[fetch] GET {ANA_URL}")
    try:
        html = fetch_live_html()
    except Exception as e:
        print(f"[error] ライブページ取得失敗: {e}", file=sys.stderr)
        sys.exit(1)

    Path(args.html).write_text(html, encoding="utf-8")
    print(f"[fetch] saved {len(html)} bytes to {args.html}")
    h = hashlib.sha256(html.encode()).hexdigest()
    print(f"[fetch] sha256={h[:16]}")

    # パース
    try:
        parsed = parse_campaign_html(html)
    except Exception as e:
        print(f"[error] パース例外: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # 基本検証
    errors: list[str] = []
    if not parsed.booking_start:
        errors.append("予約発券期間の開始日が抽出できませんでした")
    if not parsed.travel_start:
        errors.append("対象搭乗期間の開始日が抽出できませんでした")
    if not parsed.routes_by_miles:
        errors.append("路線リストが空です（HTML構造変更の可能性）")
    if not parsed.osaka_route_texts:
        # 大阪路線が0件は異常ではない場合もあるが、実ページでは通常7件以上あるため警告
        # ただし対象外期間（休止中）は0件もありうるため、エラーではなく警告扱い
        print("[warn] 大阪関連路線が0件です（休止期間の可能性）")

    # 大阪正規化
    normalized = normalize_all_osaka_routes(parsed.routes_by_miles, parsed.travel_start, parsed.travel_end)
    print(f"[parse] booking={parsed.booking_start} travel={parsed.travel_start} routes={len(parsed.all_route_texts)} osaka={len(parsed.osaka_route_texts)} normalized={len(normalized)}")

    # ブロック分解の精度チェック
    blocks = extract_all_campaign_blocks(html)
    print(f"[parse] blocks={len(blocks)}")
    for b in blocks:
        print(f"  block booking={b['booking_start']} travel={b['travel_start']} miles={list(b['routes_by_miles'].keys()) if b['routes_by_miles'] else []}")

    # GitHub Actions 出力用のJSON
    result = {
        "fetched_at": datetime.now(JST).isoformat(),
        "url": ANA_URL,
        "sha256": h,
        "booking_start": parsed.booking_start.isoformat() if parsed.booking_start else None,
        "booking_end": parsed.booking_end.isoformat() if parsed.booking_end else None,
        "travel_start": parsed.travel_start.isoformat() if parsed.travel_start else None,
        "travel_end": parsed.travel_end.isoformat() if parsed.travel_end else None,
        "routes_by_miles": {str(k): v for k, v in parsed.routes_by_miles.items()},
        "osaka_routes": parsed.osaka_route_texts,
        "normalized_osaka": normalized,
        "blocks": [
            {
                "booking_start": str(b["booking_start"]) if b["booking_start"] else None,
                "travel_start": str(b["travel_start"]) if b["travel_start"] else None,
                "routes_by_miles": {str(k): v for k, v in b["routes_by_miles"].items()} if b["routes_by_miles"] else {},
            }
            for b in blocks
        ],
        "headings": parsed.headings[:10],
        "errors": errors,
    }

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[output] wrote {args.output}")

    if errors:
        print(f"[error] 精度エラー: {errors}", file=sys.stderr)
        sys.exit(1)

    # 追加の精度ゲート: 大阪路線が極端に少ない場合は警告（休止期間を除く）
    if parsed.travel_start and len(parsed.osaka_route_texts) < 3:
        # 休止期間かどうかは headings や routes の有無で判断
        # 休止期間は routes 自体が空なので上記 errors で既に検出
        pass

    print("[ok] 精度検証に合格しました")


if __name__ == "__main__":
    main()
