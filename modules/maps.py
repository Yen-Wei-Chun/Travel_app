import requests
import streamlit as st
from urllib.parse import quote, urlencode


# ── 讀取 API Key ────────────────────────────────────────────────
def _maps_key() -> str:
    try:
        return st.secrets["maps_api_key"]
    except Exception:
        return ""


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
    組合 Google Maps 路線連結。
    座標優先；最多 8 個 waypoints（Google 限制）。
    """
    if not stops:
        return ""
    if len(stops) == 1:
        return build_single_url(
            stops[0].get("location", ""), stops[0].get("lat"), stops[0].get("lng")
        )

    def _q(row):
        try:
            return f"{float(row['lat'])},{float(row['lng'])}"
        except (TypeError, ValueError, KeyError):
            return quote(str(row.get("location", "")))

    params = {
        "api": "1",
        "origin": _q(stops[0]),
        "destination": _q(stops[-1]),
    }
    mid = stops[1:-1][:8]
    if mid:
        params["waypoints"] = "|".join(_q(s) for s in mid)

    return "https://maps.google.com/maps/dir/?" + urlencode(params)


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