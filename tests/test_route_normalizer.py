from datetime import date

from ana_tokutabi_watcher.services.route_normalizer import (
    normalize_all_osaka_routes,
    normalize_osaka_route,
)


def test_normalize_osaka_route_basic():
    r = normalize_osaka_route("大阪⇔札幌（新千歳）", 5500, date(2026, 4, 9), date(2026, 4, 15))
    assert r is not None
    assert r["origin_area"] == "大阪"
    assert r["origin_airports"] == ["ITM"]
    assert r["destination_name"] == "札幌（新千歳）"
    assert r["destination_airports"] == ["CTS"]
    assert r["miles"] == 5500
    assert r["route_text"] == "大阪⇔札幌（新千歳）"


def test_normalize_osaka_reverse():
    r = normalize_osaka_route("札幌（新千歳）⇔大阪", 4500, None, None)
    assert r is not None
    assert r["destination_name"] == "札幌（新千歳）"
    assert r["route_text"] == "大阪⇔札幌（新千歳）"


def test_normalize_non_osaka_returns_none():
    r = normalize_osaka_route("東京（羽田）⇔札幌（新千歳）", 3000, None, None)
    assert r is None


def test_normalize_all_osaka_routes():
    routes_by_miles = {
        3000: ["大阪⇔福岡", "東京（羽田）⇔札幌（新千歳）"],
        4500: ["大阪⇔札幌（新千歳）"],
    }
    result = normalize_all_osaka_routes(routes_by_miles, date(2026, 4, 9), date(2026, 4, 15))
    assert len(result) == 2
    dests = {r["destination_name"] for r in result}
    assert "福岡" in dests
    assert "札幌（新千歳）" in dests


def test_normalize_fukuoka_maps_correctly():
    r = normalize_osaka_route("大阪⇔福岡", 3000, None, None)
    assert r is not None
    assert r["destination_airports"] == ["FUK"]
