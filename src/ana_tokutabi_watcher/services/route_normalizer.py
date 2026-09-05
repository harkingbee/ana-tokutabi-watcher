from __future__ import annotations

import re
from datetime import date

# 都市名 → 空港コード（複数空港を持つ都市は複数コード）
CITY_TO_AIRPORTS: dict[str, list[str]] = {
    "札幌": ["CTS"],
    "新千歳": ["CTS"],
    "札幌（新千歳）": ["CTS"],
    "札幌(新千歳)": ["CTS"],
    "稚内": ["WKJ"],
    "釧路": ["KUH"],
    "函館": ["HKD"],
    "女満別": ["MMB"],
    "中標津": ["SHB"],
    "旭川": ["AKJ"],
    "帯広": ["OBO"],
    "青森": ["AOJ"],
    "秋田": ["AXT"],
    "庄内": ["SYO"],
    "仙台": ["SDJ"],
    "新潟": ["KIJ"],
    "福島": ["FKS"],
    "東京": ["HND", "NRT"],
    "羽田": ["HND"],
    "成田": ["NRT"],
    "大阪": ["ITM"],  # 本ツールでは大阪発着は伊丹空港(ITM)のみを監視対象とする
    "伊丹": ["ITM"],
    "関西": ["KIX"],
    "神戸": ["UKB"],
    "能登": ["NTQ"],
    "小松": ["KMQ"],
    "富山": ["TOY"],
    "名古屋": ["NGO", "NKM"],
    "中部": ["NGO"],
    "静岡": ["FSZ"],
    "鳥取": ["TTJ"],
    "米子": ["YGJ"],
    "萩・石見": ["IWJ"],
    "萩石見": ["IWJ"],
    "岡山": ["OKJ"],
    "広島": ["HIJ"],
    "岩国": ["IWK"],
    "山口宇部": ["UBJ"],
    "松山": ["MYJ"],
    "高松": ["TAK"],
    "高知": ["KCZ"],
    "徳島": ["TKS"],
    "福岡": ["FUK"],
    "佐賀": ["HSG"],
    "長崎": ["NGS"],
    "対馬": ["TSJ"],
    "大分": ["OIT"],
    "熊本": ["KMJ"],
    "宮崎": ["KMI"],
    "鹿児島": ["KOJ"],
    "那覇": ["OKA"],
    "沖縄": ["OKA"],
    "石垣": ["ISG"],
    "宮古": ["MMY"],
}

# 大阪として扱う空港（関西空港/神戸空港は対象外、伊丹空港のみ）
OSAKA_AIRPORTS = ["ITM"]
OSAKA_LABEL = "大阪"


def _strip_noise(text: str) -> str:
    return text.strip().replace("　", " ").replace(" ", "")


def _extract_city_names(route_text: str) -> tuple[str | None, str | None]:
    """「大阪⇔札幌（新千歳）」から (大阪, 札幌（新千歳）) を抽出。"""
    # セパレータで分割
    for sep in ["⇔", "～", "→", "←", "−", "-", "—"]:
        if sep in route_text:
            parts = route_text.split(sep)
            if len(parts) >= 2:
                a = parts[0].strip()
                b = parts[1].strip()
                # 余分な記号を除去
                a = re.sub(r"^[・\s]+|[・\s]+$", "", a)
                b = re.sub(r"^[・\s]+|[・\s]+$", "", b)
                return a, b
    return None, None


def normalize_osaka_route(
    route_text: str,
    miles: int,
    travel_start: date | None,
    travel_end: date | None,
) -> dict | None:
    """大阪関連のroute_textを正規化。非大阪はNoneを返す。"""
    if "大阪" not in route_text:
        return None
    a, b = _extract_city_names(route_text)
    if not a or not b:
        # フォールバック: 大阪を含む短いテキストをそのまま扱う
        return {
            "origin_area": "大阪",
            "origin_airports": OSAKA_AIRPORTS,
            "destination_name": route_text.replace("大阪", "").replace("⇔", "").strip() or "不明",
            "destination_airports": [],
            "miles": miles,
            "route_text": route_text,
            "travel_period_start": travel_start.isoformat() if travel_start else None,
            "travel_period_end": travel_end.isoformat() if travel_end else None,
        }

    # 大阪がどちら側かを判定
    if "大阪" in a:
        dest_name = b
    elif "大阪" in b:
        dest_name = a
    else:
        return None

    # 空港コード解決
    dest_name_clean = dest_name.strip()
    # 括弧付きの正規化
    dest_airports = CITY_TO_AIRPORTS.get(dest_name_clean)
    if dest_airports is None:
        # 部分一致で探す（例: 「札幌（新千歳）」がキーにない場合）
        for key, codes in CITY_TO_AIRPORTS.items():
            if key in dest_name_clean or dest_name_clean in key:
                dest_airports = codes
                break
        # 括弧を除去して再試行
        if dest_airports is None:
            base = re.sub(r"[（(].*?[）)]", "", dest_name_clean).strip()
            dest_airports = CITY_TO_AIRPORTS.get(base, [])

    if dest_airports is None:
        dest_airports = []

    return {
        "origin_area": "大阪",
        "origin_airports": OSAKA_AIRPORTS,
        "destination_name": dest_name_clean,
        "destination_airports": dest_airports,
        "miles": miles,
        "route_text": f"大阪⇔{dest_name_clean}",
        "travel_period_start": travel_start.isoformat() if travel_start else None,
        "travel_period_end": travel_end.isoformat() if travel_end else None,
    }


def normalize_all_osaka_routes(
    routes_by_miles: dict[int, list[str]],
    travel_start: date | None,
    travel_end: date | None,
) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for miles, texts in routes_by_miles.items():
        for rt in texts:
            if "大阪" not in rt:
                continue
            normalized = normalize_osaka_route(rt, miles, travel_start, travel_end)
            if normalized:
                key = f"{normalized['route_text']}:{miles}"
                if key not in seen:
                    seen.add(key)
                    result.append(normalized)
    return result
