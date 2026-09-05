from pathlib import Path

from ana_tokutabi_watcher.services.toku_tabi_parser import parse_campaign_html


def test_parser_extracts_periods_and_routes():
    html = (Path(__file__).parent / "fixtures" / "sample_tokutabi.html").read_text(encoding="utf-8")
    parsed = parse_campaign_html(html)
    assert parsed.booking_start is not None
    assert parsed.booking_end is not None
    assert parsed.travel_start is not None
    assert parsed.travel_end is not None
    assert parsed.booking_start.isoformat() == "2026-04-01"
    assert parsed.booking_end.isoformat() == "2026-04-07"
    assert parsed.travel_start.isoformat() == "2026-04-09"
    assert parsed.travel_end.isoformat() == "2026-04-15"
    # 大阪関連路線が抽出される
    assert any("大阪" in r for r in parsed.osaka_route_texts)
    assert len(parsed.osaka_route_texts) >= 3
    # マイル別
    assert 3000 in parsed.routes_by_miles or 4500 in parsed.routes_by_miles


def test_parser_handles_empty_html():
    parsed = parse_campaign_html("<html><body><p>準備中</p></body></html>")
    assert parsed.osaka_route_texts == []
    assert parsed.booking_start is None


def test_parser_headings_captured():
    html = (Path(__file__).parent / "fixtures" / "sample_tokutabi.html").read_text(encoding="utf-8")
    parsed = parse_campaign_html(html)
    assert any("トクたび" in h for h in parsed.headings)
