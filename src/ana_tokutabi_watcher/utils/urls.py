from __future__ import annotations

import urllib.parse
from datetime import date

# ANAのURLは仕様変更されやすいので独立モジュール化
ANA_TOKUTABI_PAGE = "https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/"
ANA_AWARD_SEARCH_ENTRY = "https://www.ana.co.jp/ja/jp/search/domestic/award/"
ANA_AMC_LOGIN = "https://www.ana.co.jp/ja/jp/amc/"

# 空港コード（国内線で使う可能性のあるコード）
AIRPORT_CODE_MAP: dict[str, list[str]] = {
    "札幌": ["CTS", "OKD"],
    "新千歳": ["CTS"],
    "札幌（新千歳）": ["CTS"],
    "札幌(新千歳)": ["CTS"],
    "東京": ["HND", "NRT"],
    "羽田": ["HND"],
    "成田": ["NRT"],
    "大阪": ["ITM"],
    "伊丹": ["ITM"],
    "関西": ["KIX"],
    "神戸": ["UKB"],
    "名古屋": ["NGO", "NKM"],
    "中部": ["NGO"],
    "福岡": ["FUK"],
    "那覇": ["OKA"],
    "沖縄": ["OKA"],
}


def build_safe_search_url(
    origin: str = "ITM",
    destination: str = "CTS",
    travel_date: date | None = None,
    miles: int | None = None,
) -> str:
    """ANA公式の特典航空券検索入口URLを返す。
    詳細なクエリパラメータは不安定なため、入口URL + 参考情報を付与する。
    可能な場合は日付等のクエリを付加するが、大量検証はしない。
    """
    # 基本は入口URLを返す
    base = ANA_AWARD_SEARCH_ENTRY
    if travel_date:
        # 参考クエリを付与（ANA側が無視しても入口として機能する）
        params = {
            "origin": origin,
            "destination": destination,
            "date": travel_date.isoformat(),
        }
        if miles:
            params["miles"] = str(miles)
        qs = urllib.parse.urlencode(params)
        return f"{base}?{qs}"
    return base


def build_tokutabi_url() -> str:
    return ANA_TOKUTABI_PAGE
