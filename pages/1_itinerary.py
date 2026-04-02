import uuid
import time
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

from modules.auth import require_auth, get_current_user
from modules.db   import read_sheet, append_row, update_row, delete_row
from modules.maps import geocode, geocode_rows, build_route_url, extract_latng_from_url

from components.timeline  import render_timeline
from components.map_embed import render_map, render_map_controls

st.set_page_config(page_title="行程總表", page_icon="🗺️", layout="wide")
require_auth()

user    = get_current_user()
trip_id = user["trip_id"]

st.session_state.setdefault("selected_stop_idx", 0)


# ── 資料載入 ─────────────────────────────────────────────────────
# ── 資料載入 ─────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def load_rows(trip_id: str) -> list[dict]:
    df = read_sheet("itinerary", trip_id)
    return geocode_rows(df.to_dict("records"))

@st.cache_data(ttl=300, show_spinner=False)
def load_destination(trip_id: str) -> str:
    df = read_sheet("trips")
    if df.empty:
        return ""
    matched = df[df["trip_id"] == trip_id]
    if matched.empty:
        return ""
    return str(matched.iloc[0].get("destination", "") or "")

rows = load_rows(trip_id)
destination = load_destination(trip_id)


# query_params 橋接
def _get_selected_idx(max_idx: int) -> int:
    try:
        val = int(st.query_params.get("stop_idx", 0))
        return max(0, min(val, max_idx))
    except (TypeError, ValueError):
        return 0

if rows:
    idx_from_params = _get_selected_idx(len(rows) - 1)
    if idx_from_params != st.session_state.selected_stop_idx:
        st.session_state.selected_stop_idx = idx_from_params


# ════════════════════════════════════════════════════════════════
# 頁首
# ════════════════════════════════════════════════════════════════
col_h, col_btn = st.columns([3, 1])
with col_h:
    st.subheader("🗺️ 行程總表")
    if rows:
        dates = sorted({str(r.get("date","")) for r in rows if r.get("date")})
        if dates:
            st.caption(f"{dates[0]} ～ {dates[-1]}　共 {len(rows)} 個停留點")
with col_btn:
    route_url = build_route_url(rows)
    if route_url:
        st.link_button("🗺️ 在 Google Maps 開啟整趟路線", route_url,
                       use_container_width=True, type="primary")

    else:
        st.caption("新增至少兩個停留點後即可開啟路線導航")

st.divider()


# ════════════════════════════════════════════════════════════════
# 雙欄：時間軸 ＋ 地圖
# ════════════════════════════════════════════════════════════════
selected_idx = st.session_state.selected_stop_idx
left, right  = st.columns([1, 1], gap="medium")

with left:
    st.markdown("**📅 停留點**")
    render_timeline(rows, selected_idx=selected_idx, height=520)

with right:
    st.markdown("**🗺️ 地圖**")
    map_mode = "place" if rows and selected_idx > 0 else "directions"
    render_map(rows, mode=map_mode, selected_idx=selected_idx, height=460)
    render_map_controls(rows, selected_idx=selected_idx)

st.divider()


# ════════════════════════════════════════════════════════════════
# 行程總覽表（依日期分組）
# 地點名稱：若有 attractions 對應 → 顯示「查看景點介紹」連結；否則純文字
# ════════════════════════════════════════════════════════════════
DAY_COLORS = [
    {"bg": "#E6F1FB", "text": "#0C447C", "tag_bg": "#0C447C", "tag_text": "#E6F1FB"},
    {"bg": "#E1F5EE", "text": "#085041", "tag_bg": "#085041", "tag_text": "#E1F5EE"},
    {"bg": "#FAEEDA", "text": "#633806", "tag_bg": "#633806", "tag_text": "#FAEEDA"},
    {"bg": "#FBEAF0", "text": "#72243E", "tag_bg": "#72243E", "tag_text": "#FBEAF0"},
    {"bg": "#EEEDFE", "text": "#3C3489", "tag_bg": "#3C3489", "tag_text": "#EEEDFE"},
]
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


def _fmt_date_full(s: str) -> str:
    try:
        from datetime import date as dt_date
        d = dt_date.fromisoformat(s)
        return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）"
    except Exception:
        return s


def build_overview_html(rows: list[dict]) -> str:
    from collections import OrderedDict
    groups: OrderedDict = OrderedDict()
    for r in sorted(rows, key=lambda x: str(x.get("date", ""))):
        groups.setdefault(str(r.get("date", "未指定")), []).append(r)

    day_blocks = []
    for day_num, (date_str, day_rows) in enumerate(groups.items()):
        c = DAY_COLORS[day_num % len(DAY_COLORS)]
        rows_html = []
        for r in day_rows:
            loc        = r.get("location", "")
            transport  = r.get("transport", "")
            duration   = r.get("duration", "")
            highlights = r.get("highlights", "")
            loc_html = f'<div class="place">{loc}</div>'
            t_badge = (f'<span class="badge">{transport}</span>'
                       if transport else "")

            rows_html.append(f"""<tr>
  <td style="width:35%">{loc_html}</td>
  <td style="width:20%;vertical-align:top">{t_badge}</td>
  <td style="width:15%;white-space:nowrap;color:#888;font-size:12px;vertical-align:top">{duration}</td>
  <td style="width:30%;font-size:12px;color:#555;line-height:1.6;vertical-align:top">{highlights}</td>
</tr>""")

        day_blocks.append(f"""
<div class="day-block">
  <div class="day-header" style="background:{c['bg']};color:{c['text']}">
    <span class="day-tag" style="background:{c['tag_bg']};color:{c['tag_text']}">
      DAY {day_num + 1}
    </span>
    {_fmt_date_full(date_str)}
  </div>
  <table>
    <colgroup>
      <col style="width:35%">
      <col style="width:20%">
      <col style="width:15%">
      <col style="width:30%">
    </colgroup>
    <thead><tr>
      <th>地點名稱</th>
      <th>交通</th>
      <th>停留時間</th>
      <th>行程亮點</th>
    </tr></thead>
    <tbody>{"".join(rows_html)}</tbody>
  </table>
</div>""")

    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:13px;color:#1a1a1a;background:transparent;padding:4px 0 16px}}
.day-block{{margin-bottom:16px;background:#fff;border-radius:12px;
  overflow:hidden;border:.5px solid #e0deda}}
.day-header{{display:flex;align-items:center;gap:10px;padding:10px 16px;
  font-weight:500;font-size:13px}}
.day-tag{{font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;
  white-space:nowrap;letter-spacing:.04em}}
table{{width:100%;border-collapse:collapse;table-layout:fixed}}
thead tr{{background:#fafaf8}}
th{{text-align:left;padding:8px 12px;font-weight:500;font-size:11px;
  letter-spacing:.04em;color:#999;border-bottom:.5px solid #e8e6e0;
  white-space:nowrap;overflow:hidden}}
td{{padding:10px 12px;border-bottom:.5px solid #f0ede8;
  overflow:hidden;word-break:break-word}}
tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:#fafaf8}}
.place{{font-weight:500;font-size:13px}}
.badge{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;
  white-space:nowrap;border:.5px solid #e0deda;color:#888;background:#fafaf8}}
</style></head><body>
{"".join(day_blocks)}
</body></html>"""


st.markdown("#### 📋 行程總覽")
if rows:
    dates_count  = len({str(r.get("date","")) for r in rows})
    table_height = min(dates_count * 44 + len(rows) * 52 + 60, 900)
    components.html(
        build_overview_html(rows),
        height=table_height, scrolling=True,
    )
else:
    st.info("尚無行程資料。")

st.divider()


# ════════════════════════════════════════════════════════════════
# 編輯行程（折疊）
# ════════════════════════════════════════════════════════════════
with st.expander("✏️ 編輯行程", expanded=False):
    all_dates    = sorted({str(r.get("date","")) for r in rows if r.get("date")})
    filter_dates = st.multiselect("篩選日期", all_dates,
                                  placeholder="不選 = 顯示全部", key="filter_dates")
    show_rows    = [r for r in rows if not filter_dates
                    or str(r.get("date","")) in filter_dates]

    EDIT_COLS   = ["date","location","transport","duration","highlights"]
    HIDDEN_COLS = ["row_id","trip_id","lat","lng"]

    df = pd.DataFrame(show_rows, columns=EDIT_COLS + HIDDEN_COLS) if show_rows \
         else pd.DataFrame(columns=EDIT_COLS + HIDDEN_COLS)

    if "date" in df.columns and not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # 加入勾選欄位（放最前面）
    df.insert(0, "_sel", False)

    col_cfg = {
        "_sel":       st.column_config.CheckboxColumn("選擇", default=False),
        "date":       st.column_config.DateColumn("日期", required=True, format="YYYY-MM-DD"),
        "location":   st.column_config.TextColumn("地點名稱", required=True, width="medium"),
        "transport":  st.column_config.SelectboxColumn(
                          "交通方式",
                          options=["飛機","火車","地鐵","公車","計程車","步行","租車","輪船","其他"]
                      ),
        "duration":   st.column_config.TextColumn("停留時間", width="small"),
        "highlights": st.column_config.TextColumn("行程亮點", width="large"),
        "row_id":     None,
        "trip_id":    None,
        "lat":        None,
        "lng":        None,
        "route":      None,
    }

    edited = st.data_editor(
        df, column_config=col_cfg, num_rows="dynamic",
        use_container_width=True, hide_index=True, key="itin_editor",
    )

    # ── 手動修正座標 ──────────────────────────────────────────────
    with st.expander("📍 手動修正某個地點的座標"):
        loc_options = [r.get("location","") for r in show_rows if r.get("location")]
        if not loc_options:
            st.info("目前沒有停留點可修正。")
        else:
            fix_loc = st.selectbox("選擇要修正的地點", loc_options, key="fix_loc_select")
            fix_url = st.text_input("貼上 Google Maps 分享連結", key="fix_maps_url")

            if st.button("🔍 解析座標", key="fix_parse_btn"):
                st.session_state.pop("_fix_lat", None)
                st.session_state.pop("_fix_lng", None)
                st.session_state["_fix_manual"] = False
                st.session_state["_fix_msg"] = None

                if not fix_url.strip():
                    st.session_state["_fix_msg"] = ("warning", "請先貼上 Google Maps 連結。")
                elif "maps.app.goo.gl" in fix_url:
                    try:
                        lat, lng = extract_latng_from_url(fix_url)
                    except Exception:
                        lat, lng = None, None
                    if lat is None:
                        st.session_state["_fix_msg"] = (
                            "warning", "短網址無法解析，請改用完整 Google Maps 連結。"
                        )
                    else:
                        st.session_state["_fix_lat"] = lat
                        st.session_state["_fix_lng"] = lng
                        st.session_state["_fix_msg"] = (
                            "success", f"解析成功：緯度 {lat}、經度 {lng}"
                        )
                else:
                    lat, lng = extract_latng_from_url(fix_url)
                    if lat is not None:
                        st.session_state["_fix_lat"] = lat
                        st.session_state["_fix_lng"] = lng
                        st.session_state["_fix_msg"] = (
                            "success", f"解析成功：緯度 {lat}、經度 {lng}"
                        )
                    else:
                        st.session_state["_fix_manual"] = True
                        st.session_state["_fix_msg"] = (
                            "warning", "無法自動解析，請手動輸入座標"
                        )

            # 顯示訊息
            msg = st.session_state.get("_fix_msg")
            if msg:
                getattr(st, msg[0])(msg[1])

            # 解析成功 → 顯示套用按鈕
            if st.session_state.get("_fix_lat") is not None:
                fix_lat = st.session_state["_fix_lat"]
                fix_lng = st.session_state["_fix_lng"]
                if st.button("✅ 套用座標", key="fix_apply_btn"):
                    target = next((r for r in show_rows if r.get("location") == fix_loc), None)
                    if target and target.get("row_id"):
                        update_row("itinerary", "row_id", target["row_id"],
                                   {"lat": fix_lat, "lng": fix_lng})
                        st.session_state.pop("_fix_lat", None)
                        st.session_state.pop("_fix_lng", None)
                        st.session_state["_fix_msg"] = None
                        load_rows.clear()
                        st.success("座標已更新！")
                        st.rerun()
                    else:
                        st.error("找不到對應的 row_id，請重新整理後再試。")

            # 解析失敗 → 顯示手動輸入
            elif st.session_state.get("_fix_manual"):
                fix_lat = st.number_input("緯度", value=0.0, format="%.6f", key="fix_manual_lat")
                fix_lng = st.number_input("經度", value=0.0, format="%.6f", key="fix_manual_lng")
                if st.button("✅ 套用座標", key="fix_manual_apply_btn"):
                    target = next((r for r in show_rows if r.get("location") == fix_loc), None)
                    if target and target.get("row_id"):
                        update_row("itinerary", "row_id", target["row_id"],
                                   {"lat": fix_lat, "lng": fix_lng})
                        st.session_state["_fix_manual"] = False
                        st.session_state["_fix_msg"] = None
                        load_rows.clear()
                        st.success("座標已更新！")
                        st.rerun()
                    else:
                        st.error("找不到對應的 row_id，請重新整理後再試。")

    # 讀取勾選的列（用 row_id 而非 location，避免同名地點誤刪）
    selected_mask   = edited["_sel"].fillna(False).astype(bool)
    selected_row_ids = [
        rid for rid in edited.loc[selected_mask, "row_id"].tolist()
        if rid
    ]

    save_col, del_col, hint_col = st.columns([1, 1, 2])
    with save_col:
        save = st.button("💾 儲存變更", type="primary", use_container_width=True)
    with del_col:
        delete_clicked = st.button(
            "🗑️ 刪除選中列",
            disabled=not selected_row_ids,
            use_container_width=True,
        )
    with hint_col:
        st.caption("儲存時自動補齊 Geocoding 座標。")

    if delete_clicked and selected_row_ids:
        id_to_label = {
            r["row_id"]: f"{r.get('date', '')}　{r.get('location', '')}"
            for r in show_rows if r.get("row_id")
        }
        delete_labels = [id_to_label.get(rid, rid) for rid in selected_row_ids]
        st.session_state["pending_delete_ids"]    = selected_row_ids
        st.session_state["pending_delete_labels"] = delete_labels
        st.rerun()

    pending        = st.session_state.get("pending_delete_ids", [])
    pending_labels = st.session_state.get("pending_delete_labels", [])
    if pending:
        label_list = "　".join(f"「{l}」" for l in pending_labels)
        st.warning(f"確認刪除以下 {len(pending)} 筆？此操作無法復原。\n{label_list}")
        confirm_col, cancel_col = st.columns([1, 1])
        with confirm_col:
            if st.button("✅ 確認刪除", type="primary", use_container_width=True):
                with st.spinner("刪除中…"):
                    for rid in pending:
                        delete_row("itinerary", "row_id", rid)
                st.session_state.pop("pending_delete_ids", None)
                st.session_state.pop("pending_delete_labels", None)
                load_rows.clear()
                st.rerun()
        with cancel_col:
            if st.button("❌ 取消", use_container_width=True):
                st.session_state.pop("pending_delete_ids", None)
                st.session_state.pop("pending_delete_labels", None)
                st.rerun()

    if save:
        new_rows = edited.drop(columns=["_sel"], errors="ignore").to_dict("records")
        saved, skipped = 0, 0

        # 建立原始資料的對照表，用來比對哪些列有變動
        original_map = {r.get("row_id",""): r for r in show_rows if r.get("row_id")}

        with st.spinner("儲存並補齊座標中…"):
            for r in new_rows:
                if not r.get("location") or not r.get("date"):
                    skipped += 1
                    continue

                r["trip_id"] = trip_id
                row_id = r.get("row_id","")

                # 新列（沒有 row_id）→ 直接新增
                if not row_id:
                    # 強制重新 geocode，不使用表格裡的舊座標
                    coords = geocode(r["location"], hint=destination)
                    if coords:
                        r["lat"], r["lng"] = coords
                    else:
                        r["lat"], r["lng"] = "", ""
                    r["row_id"] = "it_" + uuid.uuid4().hex[:8]
                    r["date"] = str(r.get("date", ""))
                    append_row("itinerary", r)
                    saved += 1
                    time.sleep(1)
                    continue

                # 舊列 → 比對是否有變動，沒變動就跳過
                orig = original_map.get(row_id, {})
                changed = any(
                    str(r.get(col,"")) != str(orig.get(col,""))
                    for col in ["date","location","transport","duration","highlights"]
                )
                if not changed:
                    continue

                if not r.get("lat") or not r.get("lng"):
                    coords = geocode(r["location"], hint=destination)
                    if coords:
                        r["lat"], r["lng"] = coords

                update_row("itinerary", "row_id", row_id, {
                    "date":       str(r.get("date","")),
                    "location":   r.get("location",""),
                    "transport":  r.get("transport",""),
                    "duration":   r.get("duration",""),
                    "highlights": r.get("highlights",""),
                    "lat":        "" if pd.isna(r.get("lat","")) else r.get("lat",""),
                    "lng":        "" if pd.isna(r.get("lng","")) else r.get("lng",""),
                    "trip_id":    trip_id,
                })
                saved += 1
                time.sleep(1)

        load_rows.clear()
        if saved:
            st.success(f"已儲存 {saved} 筆。")
        if skipped:
            st.warning(f"略過 {skipped} 筆（缺少日期或地點名稱）。")
        if saved or skipped:
            st.rerun()