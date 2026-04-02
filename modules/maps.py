import re
import requests
import streamlit as st
from urllib.parse import quote, urlencode


# ── 讀取 API Key ────────────────────────────────────────────────
def _maps_key() -> str:
    try:
        return st.secrets["maps_api_key"]
    except Exception:
        return ""


# ── 0. 從 Google Maps URL 解析座標 ─────────────────────────────
def extract_latng_from_url(maps_url: str) -> tuple[float, float] | tuple[None, None]:
    """
    從 Google Maps 分享連結解析 (lat, lng)。
    支援格式：
      - maps.app.goo.gl 短網址（自動 follow redirect）
      - /maps/place/.../@lat,lng,zoom
      - /maps?q=lat,lng
      - /maps/search/.../@lat,lng,zoom
    解析失敗回傳 (None, None)，不 raise exception。
    """
    url = maps_url.strip()
    if not url:
        return None, None

    # 短網址：follow redirect 取完整 URL
    if "maps.app.goo.gl" in url:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=5)
            url = resp.url
        except Exception:
            return None, None

    # @lat,lng 格式（/maps/place 和 /maps/search 通用）
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))

    # ?q=lat,lng 格式
    m = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))

    return None, None


# ── 1. Geocoding：地名 → (lat, lng) ────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def geocode(location: str, hint: str = "") -> tuple[float, float] | None:
    """
    地名 → (lat, lng)。失敗或無 Key 時回傳 None。
    快取 24 小時，相同地名不重複呼叫 API。
    hint 可傳入旅遊目的地，提升搜尋準確度（例如 "日本關西"）。
    """
    api_key = _maps_key()
    if not api_key or not location.strip():
        return None
    query = f"{location} {hint}".strip()
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": api_key, "language": "zh-TW"},
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return round(loc["lat"], 6), round(loc["lng"], 6)
    except Exception:
        pass
    return None


def geocode_rows(rows: list[dict]) -> list[dict]:
    """
    批次補齊 itinerary rows 的 lat/lng。
    已有座標的列直接跳過，只對空值呼叫 API。
    """
    result = []
    for row in rows:
        r = dict(row)
        try:
            float(r["lat"]); float(r["lng"])
            result.append(r)
            continue
        except (TypeError, ValueError, KeyError):
            pass
        coords = geocode(r.get("location", ""))
        r["lat"], r["lng"] = coords if coords else (None, None)
        result.append(r)
    return result


# ── 2. 單點 Google Maps 連結 ────────────────────────────────────
def build_single_url(location: str, lat=None, lng=None) -> str:
    """優先用座標（精準），沒有座標才用地名搜尋。"""
    if lat and lng:
        try:
            return f"https://maps.google.com/maps?q={float(lat)},{float(lng)}"
        except (TypeError, ValueError):
            pass
    return f"https://maps.google.com/maps?q={quote(str(location))}"


# ── 3. 整趟路線連結（waypoints） ────────────────────────────────
def build_route_url(stops: list[dict]) -> str:
    """
    組合 Google Maps 路線連結（query parameter 格式，對中日文地名更穩定）。
    去重保留順序，不指定 travelmode 讓使用者自行選擇。
    """
    valid = [s for s in stops if s.get("location")]
    if len(valid) < 2:
        return ""

    seen = set()
    unique_stops = []
    for s in valid:
        if s["location"] not in seen:
            seen.add(s["location"])
            unique_stops.append(s)

    if len(unique_stops) < 2:
        return ""

    origin = quote(unique_stops[0]["location"], safe="")
    destination = quote(unique_stops[-1]["location"], safe="")
    url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"

    if len(unique_stops) > 2:
        waypoints = quote("|".join(s["location"] for s in unique_stops[1:-1]), safe="|")
        url += f"&waypoints={waypoints}"

    return url


# ── 4. Maps Embed API iframe src ────────────────────────────────
def build_embed_url(
    stops: list[dict],
    mode: str = "place",
    zoom: int = 13,
    selected_idx: int = 0,
) -> str:
    """
    產生 Maps Embed API 的 iframe src。
    mode: "place"（單一地點）| "directions"（整趟路線）
    """
    api_key = _maps_key()
    if not api_key or not stops:
        return ""

    base = "https://www.google.com/maps/embed/v1/"

    def _q(row):
        try:
            return f"{float(row['lat'])},{float(row['lng'])}"
        except (TypeError, ValueError, KeyError):
            return str(row.get("location", ""))

    if mode == "directions" and len(stops) >= 2:
        params = {
            "key": api_key,
            "origin": _q(stops[0]),
            "destination": _q(stops[-1]),
        }
        mid = stops[1:-1][:8]
        if mid:
            params["waypoints"] = "|".join(_q(s) for s in mid)
        return base + "directions?" + urlencode(params)

    # place（預設）
    row = stops[min(selected_idx, len(stops) - 1)]
    return base + "place?" + urlencode({"key": api_key, "q": _q(row), "zoom": zoom})