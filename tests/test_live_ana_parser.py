from pathlib import Path

from ana_tokutabi_watcher.services.route_normalizer import normalize_all_osaka_routes
from ana_tokutabi_watcher.services.toku_tabi_parser import (
    extract_all_campaign_blocks,
    parse_campaign_html,
)
from ana_tokutabi_watcher.utils.dates import parse_period


def test_live_fixture_parses_correctly():
    html = (Path(__file__).parent / "fixtures" / "live_ana_20260904.html").read_text(encoding="utf-8")
    parsed = parse_campaign_html(html)
    # 実ページでは 2026-08-26 予約、09-02 搭乗が現行
    assert parsed.booking_start is not None
    assert parsed.travel_start is not None
    assert parsed.booking_start.isoformat() == "2026-08-26"
    assert parsed.travel_start.isoformat() == "2026-09-02"
    # マイル別に路線が抽出される
    assert 3500 in parsed.routes_by_miles
    assert 5500 in parsed.routes_by_miles
    # 大阪関連が7件以上（東京⇔大阪含む）
    assert len(parsed.osaka_route_texts) >= 7
    assert "大阪⇔福岡" in parsed.osaka_route_texts
    assert "大阪⇔札幌（新千歳）" in parsed.osaka_route_texts or "大阪⇔秋田" in parsed.osaka_route_texts


def test_live_blocks_extraction():
    html = (Path(__file__).parent / "fixtures" / "live_ana_20260904.html").read_text(encoding="utf-8")
    blocks = extract_all_campaign_blocks(html)
    # 少なくとも2ブロック（9/2搭乗分と9/9搭乗分）が検出される
    assert len(blocks) >= 2
    travel_starts = [b["travel_start"] for b in blocks if b["travel_start"]]
    assert any(str(d) == "2026-09-02" for d in travel_starts)
    assert any(str(d) == "2026-09-09" for d in travel_starts)
    # 各ブロックの路線が正しく分離されている
    for b in blocks:
        if b["travel_start"] and str(b["travel_start"]) == "2026-09-02":
            assert 3500 in b["routes_by_miles"]
            assert any("大阪⇔福岡" in r for r in b["routes_by_miles"][3500])
        if b["travel_start"] and str(b["travel_start"]) == "2026-09-09":
            assert any("大阪⇔札幌（新千歳）" in r for lst in b["routes_by_miles"].values() for r in lst)


def test_live_osaka_normalization():
    html = (Path(__file__).parent / "fixtures" / "live_ana_20260904.html").read_text(encoding="utf-8")
    parsed = parse_campaign_html(html)
    normalized = normalize_all_osaka_routes(parsed.routes_by_miles, parsed.travel_start, parsed.travel_end)
    assert len(normalized) >= 5
    dests = {r["destination_name"] for r in normalized}
    assert "福岡" in dests
    # 正規化で大阪発着が正しく構築される
    for r in normalized:
        assert r["origin_area"] == "大阪"
        assert r["origin_airports"] == ["ITM", "KIX", "UKB"]
        assert r["miles"] in (3500, 5500, 6500, 7500)


def test_parse_period_kara_format():
    # 実ページの「0:00から〜23:59まで」形式
    s, e = parse_period("2026年8月26日（水）0:00から9月1日（火）23:59まで")
    assert s is not None and e is not None
    assert s.isoformat() == "2026-08-26"
    assert e.isoformat() == "2026-09-01"
    s2, e2 = parse_period("2026年9月2日（水）から9月8日（火）搭乗分")
    assert s2 is not None and e2 is not None
    assert s2.isoformat() == "2026-09-02"
    assert e2.isoformat() == "2026-09-08"
