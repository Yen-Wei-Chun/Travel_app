# 渲染 Embed iframe；無 API Key 時顯示連結 fallback

import streamlit as st
import streamlit.components.v1 as components
from modules.maps import build_embed_url, build_route_url, build_single_url


# ── Fallback（無 API Key 時） ────────────────────────────────────
def _render_fallback(rows: list[dict], selected_idx: int) -> None:
    st.warning("尚未設定 Maps API Key，改以連結方式顯示。", icon="🗺️")
    route_url = build_route_url(rows)
    if route_url:
        st.link_button("🗺️ 開啟整趟路線", route_url, use_container_width=True)
    row = rows[min(selected_idx, len(rows) - 1)]
    single_url = build_single_url(row.get("location",""), row.get("lat"), row.get("lng"))
    if single_url:
        st.link_button(f"📍 {row.get('location','查看地點')} ↗", single_url)


# ── Embed iframe HTML ────────────────────────────────────────────
def _embed_html(src: str, height: int) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:transparent}}
#wrap{{width:100%;height:{height}px;border-radius:12px;overflow:hidden;border:1px solid #E0E0E0}}
iframe{{width:100%;height:100%;border:none;display:block}}
</style></head><body>
<div id="wrap">
  <iframe src="{src}" allowfullscreen referrerpolicy="no-referrer-when-downgrade" loading="lazy"></iframe>
</div>
</body></html>"""


# ── 公開：地圖主體 ───────────────────────────────────────────────
def render_map(
    rows: list[dict],
    mode: str = "directions",
    selected_idx: int = 0,
    height: int = 460,
) -> None:
    """
    渲染 Google Maps Embed iframe。
    mode: "directions"（整趟路線）| "place"（選中地點）
    """
    if not rows:
        st.info("尚無行程資料，無法顯示地圖。")
        return
    src = build_embed_url(rows, mode=mode, selected_idx=selected_idx)
    if not src:
        _render_fallback(rows, selected_idx)
        return
    components.html(_embed_html(src, height), height=height + 8, scrolling=False)


# ── 公開：地圖下方快捷按鈕 ──────────────────────────────────────
def render_map_controls(rows: list[dict], selected_idx: int = 0) -> None:
    """整趟路線（回第一站）+ 選中地點，兩個按鈕並排。"""
    if not rows:
        return
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗺️ 整趟路線", use_container_width=True, key="map_ctrl_route"):
            st.session_state["selected_stop_idx"] = 0
            st.query_params["stop_idx"] = "0"
            st.rerun()
    row = rows[min(selected_idx, len(rows) - 1)]
    single_url = build_single_url(row.get("location",""), row.get("lat"), row.get("lng"))
    with c2:
        if single_url:
            st.link_button(f"📍 {row.get('location','查看地點')} ↗", single_url, use_container_width=True)