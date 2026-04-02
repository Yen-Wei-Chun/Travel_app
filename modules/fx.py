import requests
import datetime
import streamlit as st
from modules.db import read_sheet, append_row, update_row


def get_rate(from_currency: str, to_currency: str) -> float:
    """回傳 from_currency → to_currency 的匯率（7日平均）"""

    # 同幣別直接回傳
    if from_currency == to_currency:
        return 1.0

    cache_key = f"{from_currency}_{to_currency}"

    # ── 第一層：查 Sheets fx_cache ──────────────────────
    cached = _get_from_sheets(cache_key)
    if cached is not None:
        return cached

    # ── 第二層：打 frankfurter.app API ──────────────────
    rate = _fetch_from_api(from_currency, to_currency)
    if rate is not None:
        _save_to_sheets(cache_key, rate)
    return rate


def convert(amount: float, from_currency: str, to_currency: str) -> float:
    """將金額從 from_currency 換算成 to_currency"""
    rate = get_rate(from_currency, to_currency)
    if rate is None:
        return None
    return round(amount * rate, 2)


# ── 內部函式 ─────────────────────────────────────────

def _get_from_sheets(cache_key: str):
    """從 fx_cache 表查快取，超過 24 小時視為過期"""
    try:
        df = read_sheet("fx_cache", trip_id=None)  # fx_cache 不分 trip
        if df.empty:
            return None
        row = df[df["cache_key"] == cache_key]
        if row.empty:
            return None

        updated_at = datetime.datetime.fromisoformat(row.iloc[0]["updated_at"])
        age = datetime.datetime.now() - updated_at
        if age.total_seconds() > 86400:  # 超過 24 小時
            return None

        return float(row.iloc[0]["rate"])
    except Exception:
        return None


def _fetch_from_api(from_currency: str, to_currency: str) -> float:
    """呼叫 exchangerate-api.com 取即時匯率"""
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        rate = data["rates"].get(to_currency)
        if rate is None:
            st.warning(f"不支援的幣別：{to_currency}")
            return None
        return round(float(rate), 6)
    except Exception as e:
        st.warning(f"匯率取得失敗（{from_currency}→{to_currency}）：{e}")
        return None


def _save_to_sheets(cache_key: str, rate: float):
    """寫入或更新 fx_cache 表"""
    now = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        df = read_sheet("fx_cache", trip_id=None)
        if not df.empty and cache_key in df["cache_key"].values:
            # 已存在 → 更新
            update_row("fx_cache", "cache_key", cache_key, {
                "rate": rate,
                "updated_at": now,
            })
        else:
            # 不存在 → 新增
            append_row("fx_cache", {
                "cache_key":  cache_key,
                "rate":       rate,
                "updated_at": now,
            })
    except Exception:
        pass  # 快取寫入失敗不影響主流程