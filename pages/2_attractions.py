import uuid, json, requests
from collections import OrderedDict
import streamlit as st
import streamlit.components.v1 as components

from modules.auth import require_auth, get_current_user
from modules.db   import read_sheet, append_row, update_row, delete_row

st.set_page_config(page_title="景點介紹", page_icon="📍", layout="wide")
require_auth()
user    = get_current_user()
trip_id = user["trip_id"]

CATEGORIES = ["餐飲", "戶外景點", "室內景點", "購物", "其他"]
CAT_COLORS = {
    "餐飲":    {"bg": "#FAEEDA", "text": "#633806"},
    "戶外景點": {"bg": "#E1F5EE", "text": "#085041"},
    "室內景點": {"bg": "#E6F1FB", "text": "#0C447C"},
    "購物":    {"bg": "#FBEAF0", "text": "#72243E"},
    "其他":    {"bg": "#F1EFE8", "text": "#444441"},
}
DAY_COLORS = [
    {"bg": "#E6F1FB", "text": "#0C447C", "tag_bg": "#0C447C", "tag_text": "#E6F1FB"},
    {"bg": "#E1F5EE", "text": "#085041", "tag_bg": "#085041", "tag_text": "#E1F5EE"},
    {"bg": "#FAEEDA", "text": "#633806", "tag_bg": "#633806", "tag_text": "#FAEEDA"},
    {"bg": "#FBEAF0", "text": "#72243E", "tag_bg": "#72243E", "tag_text": "#FBEAF0"},
    {"bg": "#EEEDFE", "text": "#3C3489", "tag_bg": "#3C3489", "tag_text": "#EEEDFE"},
]
WEEKDAYS  = ["一", "二", "三", "四", "五", "六", "日"]
DOT_COLORS = ["#BA7517", "#0F6E56", "#185FA5", "#993C1D", "#3C3489"]


# ── 資料載入 ─────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def load_attractions(trip_id: str) -> list[dict]:
    df = read_sheet("attractions", trip_id)
    if df.empty:
        return []
    for col in ["category","is_rainy_day","opening_hours","best_time",
                "suggested_duration","ticket_price","history","activities"]:
        if col not in df.columns:
            df[col] = ""
    return df.to_dict("records")

@st.cache_data(ttl=60, show_spinner=False)
def load_itinerary(trip_id: str) -> list[dict]:
    df = read_sheet("itinerary", trip_id)
    return df.to_dict("records") if not df.empty else []

attractions = load_attractions(trip_id)
itin_rows   = load_itinerary(trip_id)

loc_to_date: dict[str, str] = {}
for r in sorted(itin_rows, key=lambda x: str(x.get("date",""))):
    loc = str(r.get("location","")).strip()
    if loc and loc not in loc_to_date:
        loc_to_date[loc] = str(r.get("date",""))

st.session_state.setdefault("show_add_form",    False)
st.session_state.setdefault("edit_attr_id",     None)
st.session_state.setdefault("show_import_panel", False)


# ── 工具函式 ─────────────────────────────────────────────────────
def _is_rainy(attr: dict) -> bool:
    return str(attr.get("is_rainy_day","")).strip().upper() in ("TRUE","1","YES","✓")

def _fmt_date(s: str) -> str:
    try:
        from datetime import date as dt
        d = dt.fromisoformat(s)
        return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）"
    except Exception:
        return s

def _is_draft(attr: dict) -> bool:
    return not attr.get("description") and not attr.get("tips") and not attr.get("history")


# ════════════════════════════════════════════════════════════════
# AI 自動生成
# ════════════════════════════════════════════════════════════════
def _generate_attr_info(name: str, location: str, category: str) -> dict | None:
    try:
        api_key = st.secrets["anthropic_api_key"]
    except Exception:
        st.error("找不到 anthropic_api_key，請確認 secrets.toml 設定。")
        return None

    prompt = f"""你是一位專業的旅遊編輯，請為以下景點生成完整的繁體中文介紹資料。

景點名稱：{name}
所在地區：{location or "未指定"}
類別：{category or "未指定"}

請嚴格只回傳 JSON，不要有任何說明文字或 markdown，格式如下：
{{
  "description": "景點簡介，2-3句，生動描述特色與亮點",
  "tips": "實用行程建議，包含最佳造訪時間、注意事項等，1-2句",
  "opening_hours": "開放時間，例如 06:00 – 18:00，若不確定填「請洽官網」",
  "best_time": "最佳造訪時段，例如 清晨 / 傍晚",
  "suggested_duration": "建議停留時間，例如 1.5 – 2 小時",
  "ticket_price": "門票資訊，例如 ¥500 / 人，若免費填「免費入場」",
  "history": "歷史故事或背景介紹，3-5句，生動有趣",
  "activities": [
    {{"title": "必做活動1", "desc": "具體說明，1-2句"}},
    {{"title": "必做活動2", "desc": "具體說明，1-2句"}},
    {{"title": "必做活動3", "desc": "具體說明，1-2句"}}
  ]
}}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        raw  = resp.json()["content"][0]["text"].strip()
        raw  = raw.replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        if isinstance(data.get("activities"), list):
            data["activities"] = json.dumps(data["activities"], ensure_ascii=False)
        return data
    except Exception as e:
        st.error(f"AI 生成失敗：{e}")
        return None


# ════════════════════════════════════════════════════════════════
# 卡片 HTML
# ════════════════════════════════════════════════════════════════
def build_card_html(attr: dict) -> str:
    name      = attr.get("name","（未命名）")
    loc       = attr.get("location","")
    desc      = attr.get("description","") or "尚未填寫簡介"
    tips      = attr.get("tips","") or "尚未填寫貼士"
    image_url = (attr.get("image_url") or "").strip()
    category  = attr.get("category","")
    is_rainy  = _is_rainy(attr)
    is_draft  = _is_draft(attr)
    opening   = attr.get("opening_hours","") or "—"
    best_time = attr.get("best_time","") or "—"
    duration  = attr.get("suggested_duration","") or "—"
    ticket    = attr.get("ticket_price","") or "—"
    history   = attr.get("history","") or "尚未填寫歷史故事"
    acts_raw  = attr.get("activities","") or "[]"
    try:
        activities = json.loads(acts_raw) if isinstance(acts_raw, str) else acts_raw
        if not isinstance(activities, list):
            activities = []
    except Exception:
        activities = []

    photo_inner = (
        f'<img src="{image_url}" style="width:100%;height:100%;object-fit:cover;position:absolute;inset:0">'
        if image_url else
        '<div style="display:flex;flex-direction:column;align-items:center;gap:6px">'
        '<svg width="28" height="28" viewBox="0 0 32 32" fill="none">'
        '<rect x="2" y="6" width="28" height="20" rx="4" stroke="#ccc" stroke-width="1.2"/>'
        '<circle cx="11" cy="13" r="2.5" stroke="#ccc" stroke-width="1.2"/>'
        '<path d="M2 22l7-6 5 5 4-4 7 7" stroke="#ccc" stroke-width="1.2" stroke-linecap="round"/>'
        '</svg><span style="font-size:12px;color:#ccc">無圖片</span></div>'
    )

    tags_html = ""
    if category and category in CAT_COLORS:
        c = CAT_COLORS[category]
        tags_html += (f'<span style="font-size:10px;font-weight:500;padding:2px 8px;'
                      f'border-radius:99px;background:{c["bg"]};color:{c["text"]}">{category}</span> ')
    if is_rainy:
        tags_html += ('<span style="font-size:10px;font-weight:500;padding:2px 8px;'
                      'border-radius:99px;background:#E6F1FB;color:#0C447C">☔ 雨天備案</span> ')
    if is_draft:
        tags_html += ('<span style="font-size:10px;padding:2px 8px;border-radius:99px;'
                      'background:#F1EFE8;color:#888">草稿</span>')

    loc_html = (
        f'<div style="font-size:12px;color:#888;display:flex;align-items:center;gap:4px">'
        f'<svg width="12" height="12" viewBox="0 0 13 13" fill="none">'
        f'<path d="M6.5 1C4.3 1 2.5 2.8 2.5 5c0 3 4 7 4 7s4-4 4-7c0-2.2-1.8-4-4-4z" fill="#aaa"/>'
        f'<circle cx="6.5" cy="5" r="1.3" fill="#fff"/></svg>{loc}</div>'
        if loc else ""
    )

    acts_html = ""
    for i, act in enumerate(activities[:4]):
        dot = DOT_COLORS[i % len(DOT_COLORS)]
        acts_html += (
            f'<div style="display:flex;align-items:flex-start;gap:10px;'
            f'padding:8px 14px;border-bottom:.5px solid #f0f0f0">'
            f'<div style="width:6px;height:6px;border-radius:50%;background:{dot};'
            f'flex-shrink:0;margin-top:5px"></div>'
            f'<div><div style="font-size:13px;font-weight:500;color:#1a1a1a">{act.get("title","")}</div>'
            f'<div style="font-size:12px;color:#666;line-height:1.5;margin-top:2px">'
            f'{act.get("desc","")}</div></div></div>'
        )
    if not acts_html:
        acts_html = '<div style="padding:12px 14px;font-size:12px;color:#bbb">尚未填寫必做活動</div>'

    tips_preview = tips[:100] + ("…" if len(tips) > 100 else "")

    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:transparent;padding:4px;height:700px}}
.scene{{perspective:1200px;width:100%;height:692px}}
.flipper{{width:100%;height:100%;position:relative;transform-style:preserve-3d;
  transition:transform .55s cubic-bezier(.4,.2,.2,1)}}
.flipper.flipped{{transform:rotateY(180deg)}}
.face{{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;
  border-radius:14px;border:.5px solid #e0e0e0;background:#fff;overflow:hidden;
  box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.back{{transform:rotateY(180deg);display:flex;flex-direction:column}}
.photo{{height:175px;background:#f5f4f0;position:relative;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;
  border-bottom:.5px solid #e0e0e0;overflow:hidden}}
.body{{padding:13px 15px 15px;display:flex;flex-direction:column;gap:9px;overflow-y:auto}}
.title{{font-size:18px;font-weight:500;color:#1a1a1a;line-height:1.25}}
.tags{{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}}
.desc{{font-size:12px;color:#666;line-height:1.6}}
.divider{{height:.5px;background:#efefef;margin:0 -15px}}
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.info-label{{font-size:10px;color:#bbb;letter-spacing:.04em}}
.info-val{{font-size:12px;color:#1a1a1a;font-weight:500;margin-top:2px}}
.tip-box{{background:#f8f8f6;border-radius:8px;padding:9px 11px;
  display:flex;gap:8px;align-items:flex-start}}
.tip-label{{font-size:10px;font-weight:500;color:#aaa;letter-spacing:.04em;margin-bottom:3px}}
.tip-text{{font-size:11px;color:#666;line-height:1.55}}
.flip-btn{{width:100%;padding:8px;border-radius:9px;font-size:12px;font-weight:500;
  cursor:pointer;border:.5px solid #d0d0d0;background:#f5f5f3;color:#1a1a1a;
  display:flex;align-items:center;justify-content:center;gap:5px;transition:opacity .15s}}
.flip-btn:hover{{opacity:.75}}
.bh{{padding:12px 15px 10px;border-bottom:.5px solid #efefef;
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
.bt{{font-size:14px;font-weight:500;color:#1a1a1a}}
.bs{{font-size:11px;color:#888}}
.bc{{width:26px;height:26px;border-radius:99px;border:.5px solid #d0d0d0;
  background:#f5f5f3;cursor:pointer;display:flex;align-items:center;justify-content:center}}
.bc:hover{{opacity:.6}}
.bb{{padding:0;display:flex;flex-direction:column;gap:0;overflow-y:auto;flex:1}}
.sb{{background:#f8f8f6;margin:12px 15px 0;border-radius:10px;padding:12px;
  display:flex;flex-direction:column;gap:5px}}
.sl{{font-size:10px;font-weight:500;color:#aaa;letter-spacing:.06em}}
.st{{font-size:12px;color:#666;line-height:1.65}}
.todo-block{{border:.5px solid #e0e0e0;border-radius:10px;overflow:hidden;margin:12px 15px 15px}}
.todo-header{{padding:9px 14px;background:#f8f8f6;border-bottom:.5px solid #efefef;
  font-size:10px;font-weight:500;color:#aaa;letter-spacing:.06em}}
</style></head><body>
<div class="scene"><div class="flipper" id="f">
  <div class="face">
    <div class="photo">{photo_inner}</div>
    <div class="body">
      <div>
        <div class="title">{name}</div>
        <div class="tags">{tags_html}</div>
      </div>
      {loc_html}
      <p class="desc">{desc[:160]}{"…" if len(desc)>160 else ""}</p>
      <div class="divider"></div>
      <div class="info-grid">
        <div><div class="info-label">開放時間</div><div class="info-val">{opening}</div></div>
        <div><div class="info-label">最佳造訪</div><div class="info-val">{best_time}</div></div>
        <div><div class="info-label">建議停留</div><div class="info-val">{duration}</div></div>
        <div><div class="info-label">門票資訊</div><div class="info-val">{ticket}</div></div>
      </div>
      <div class="divider"></div>
      <div class="tip-box">
        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" style="flex-shrink:0;margin-top:1px">
          <circle cx="7" cy="7" r="6" stroke="#BA7517" stroke-width="1.1"/>
          <rect x="6.3" y="6" width="1.4" height="4.5" rx=".7" fill="#BA7517"/>
          <circle cx="7" cy="4.2" r=".85" fill="#BA7517"/>
        </svg>
        <div><div class="tip-label">行程建議</div><p class="tip-text">{tips_preview}</p></div>
      </div>
      <button class="flip-btn" onclick="document.getElementById('f').classList.add('flipped')">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/>
          <rect x="6.3" y="6" width="1.4" height="4.5" rx=".7" fill="currentColor"/>
          <circle cx="7" cy="4.2" r=".85" fill="currentColor"/>
        </svg>實用貼士
      </button>
    </div>
  </div>
  <div class="face back">
    <div class="bh">
      <div><div class="bt">{name}</div><div class="bs">深度介紹 &amp; 必做活動</div></div>
      <div class="bc" onclick="document.getElementById('f').classList.remove('flipped')">
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
          <path d="M2 2l8 8M10 2l-8 8" stroke="#888" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
    </div>
    <div class="bb">
      <div class="sb">
        <div class="sl">歷史故事</div>
        <p class="st">{history}</p>
      </div>
      <div class="todo-block">
        <div class="todo-header">必做活動</div>
        {acts_html}
      </div>
    </div>
  </div>
</div></div>
</body></html>"""


# ════════════════════════════════════════════════════════════════
# 頁首列
# ════════════════════════════════════════════════════════════════
col_h, col_import, col_add = st.columns([3, 1.4, 1])
with col_h:
    st.subheader("📍 景點介紹")
    st.caption(f"共 {len(attractions)} 個景點")
with col_import:
    if st.button("⬇️ 從行程匯入地點", use_container_width=True):
        st.session_state["show_import_panel"] = True
with col_add:
    if st.button("＋ 新增景點", type="primary", use_container_width=True):
        st.session_state["show_add_form"]     = True
        st.session_state["show_import_panel"] = False
        st.session_state["edit_attr_id"]      = None


# ════════════════════════════════════════════════════════════════
# 勾選式匯入面板
# ════════════════════════════════════════════════════════════════
if st.session_state["show_import_panel"]:
    itin_locs = sorted({str(r.get("location","")).strip()
                        for r in itin_rows if r.get("location")})
    existing  = {str(a.get("name","")).strip() for a in attractions}
    available = [l for l in itin_locs if l not in existing]

    with st.container(border=True):
        st.markdown("**從行程匯入地點**")
        st.caption("勾選想建立景點介紹的地點，不需要的（如機場、車站）可以不勾。")

        if not available:
            st.info("行程裡的所有地點都已在景點清單中，無需匯入。")
        else:
            # 全選 / 全不選
            sel_all = st.checkbox("全部勾選", value=False, key="import_select_all")

            selected_locs = []
            cols = st.columns(3)
            for i, loc in enumerate(available):
                checked = cols[i % 3].checkbox(loc, value=sel_all, key=f"import_cb_{loc}")
                if checked:
                    selected_locs.append(loc)

            st.caption(f"已選 {len(selected_locs)} / {len(available)} 個地點")

            c1, c2, _ = st.columns([1, 1, 4])
            with c1:
                if st.button("✅ 確認匯入", type="primary",
                             use_container_width=True, key="confirm_import",
                             disabled=len(selected_locs) == 0):
                    for loc in selected_locs:
                        append_row("attractions", {
                            "attr_id": "at_" + uuid.uuid4().hex[:8],
                            "trip_id": trip_id,
                            "name": loc, "location": loc,
                            "description": "", "tips": "", "image_url": "",
                            "category": "", "is_rainy_day": "FALSE",
                            "opening_hours": "", "best_time": "",
                            "suggested_duration": "", "ticket_price": "",
                            "history": "", "activities": "",
                        })
                    st.session_state["show_import_panel"] = False
                    load_attractions.clear()
                    st.success(f"✅ 已匯入 {len(selected_locs)} 個景點草稿！")
                    st.rerun()
            with c2:
                if st.button("取消", use_container_width=True, key="cancel_import"):
                    st.session_state["show_import_panel"] = False
                    st.rerun()

    st.divider()


# ── 新增景點表單 ─────────────────────────────────────────────────
if st.session_state["show_add_form"] and not st.session_state["edit_attr_id"]:
    with st.container(border=True):
        st.markdown("**新增景點**")
        with st.form("add_attraction"):
            c1, c2   = st.columns(2)
            name     = c1.text_input("景點名稱 *")
            loc      = c2.text_input("所在地區")
            category = st.selectbox("類別", [""] + CATEGORIES)
            is_rainy = st.checkbox("☔ 雨天備案")
            desc     = st.text_area("景點簡介", height=70)
            tips     = st.text_area("實用貼士", height=55)
            g1,g2,g3,g4 = st.columns(4)
            opening  = g1.text_input("開放時間")
            best_t   = g2.text_input("最佳造訪")
            dur      = g3.text_input("建議停留")
            ticket   = g4.text_input("門票資訊")
            history  = st.text_area("歷史故事", height=70)
            img_url  = st.text_input("圖片網址", placeholder="https://...")
            s_col, c_col, _ = st.columns([1,1,4])
            submitted = s_col.form_submit_button("儲存", type="primary")
            cancelled = c_col.form_submit_button("取消")
        if submitted:
            if not name.strip():
                st.error("景點名稱為必填。")
            else:
                append_row("attractions", {
                    "attr_id": "at_" + uuid.uuid4().hex[:8],
                    "trip_id": trip_id,
                    "name": name.strip(), "location": loc.strip(),
                    "description": desc.strip(), "tips": tips.strip(),
                    "image_url": img_url.strip(), "category": category,
                    "is_rainy_day": "TRUE" if is_rainy else "FALSE",
                    "opening_hours": opening.strip(), "best_time": best_t.strip(),
                    "suggested_duration": dur.strip(), "ticket_price": ticket.strip(),
                    "history": history.strip(), "activities": "",
                })
                st.session_state["show_add_form"] = False
                load_attractions.clear()
                st.rerun()
        if cancelled:
            st.session_state["show_add_form"] = False
            st.rerun()
    st.divider()


# ── 篩選列 ───────────────────────────────────────────────────────
f_col, r_col = st.columns([2, 1])
with f_col:
    filter_cat = st.selectbox("類別篩選", ["全部"] + CATEGORIES,
                              label_visibility="collapsed", key="filter_cat")
with r_col:
    only_rainy = st.checkbox("☔ 只看雨天備案", key="only_rainy")

display_list = [
    a for a in attractions
    if (filter_cat == "全部" or a.get("category","") == filter_cat)
    and (not only_rainy or _is_rainy(a))
]

st.divider()


# ════════════════════════════════════════════════════════════════
# 依日期分區 + 卡片渲染
# ════════════════════════════════════════════════════════════════
date_order: list[str] = []
seen: set = set()
for r in sorted(itin_rows, key=lambda x: str(x.get("date",""))):
    d = str(r.get("date","")).strip()
    if d and d not in seen:
        date_order.append(d)
        seen.add(d)

groups: OrderedDict = OrderedDict()
for d in date_order:
    groups[d] = []
groups["許願池"] = []

for attr in display_list:
    name = str(attr.get("name","")).strip()
    date = loc_to_date.get(name,"")
    if date and date in groups:
        groups[date].append(attr)
    else:
        groups["許願池"].append(attr)

groups = OrderedDict((k,v) for k,v in groups.items() if v)

if not display_list:
    if not attractions:
        st.info("還沒有景點資料。點「⬇️ 從行程匯入地點」勾選想建立的地點，或手動新增。")
    else:
        st.info("目前篩選條件下沒有景點。")
else:
    day_idx = 0
    for group_key, group_attrs in groups.items():
        if group_key == "許願池":
            st.markdown(
                '<div style="display:flex;align-items:center;gap:10px;padding:8px 0 4px">'
                '<span style="font-size:13px;font-weight:600;color:#888">🌙 許願池</span>'
                '<span style="font-size:12px;color:#bbb">未對應到行程日期的景點</span></div>',
                unsafe_allow_html=True,
            )
        else:
            c = DAY_COLORS[day_idx % len(DAY_COLORS)]
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;padding:10px 16px;'
                f'background:{c["bg"]};border-radius:10px;margin-bottom:4px">'
                f'<span style="font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;'
                f'background:{c["tag_bg"]};color:{c["tag_text"]}">{_fmt_date(group_key)}</span>'
                f'<span style="font-size:13px;font-weight:500;color:{c["text"]}">'
                f'{len(group_attrs)} 個景點</span></div>',
                unsafe_allow_html=True,
            )
            day_idx += 1

        card_cols = st.columns(3, gap="medium")
        for i, attr in enumerate(group_attrs):
            attr_id  = attr.get("attr_id","")
            name     = attr.get("name","（未命名）")
            is_draft = _is_draft(attr)

            with card_cols[i % 3]:
                card_h = 480 if is_draft else 708
                components.html(build_card_html(attr), height=card_h, scrolling=False)

                # AI 自動生成
                if st.button("✨ 自動生成介紹", key=f"gen_{attr_id}",
                             use_container_width=True):
                    with st.spinner(f"AI 正在生成「{name}」的介紹…"):
                        result = _generate_attr_info(
                            name, attr.get("location",""), attr.get("category","")
                        )
                    if result:
                        update_row("attractions", "attr_id", attr_id, {
                            **{k: attr.get(k,"") for k in
                               ["name","location","category","is_rainy_day","image_url"]},
                            "description":        result.get("description",""),
                            "tips":               result.get("tips",""),
                            "opening_hours":      result.get("opening_hours",""),
                            "best_time":          result.get("best_time",""),
                            "suggested_duration": result.get("suggested_duration",""),
                            "ticket_price":       result.get("ticket_price",""),
                            "history":            result.get("history",""),
                            "activities":         result.get("activities",""),
                        })
                        load_attractions.clear()
                        st.success(f"✅ 「{name}」介紹已生成！")
                        st.rerun()

                # 編輯表單
                with st.expander("✏️ 編輯"):
                    with st.form(f"edit_{attr_id}"):
                        ec1,ec2 = st.columns(2)
                        e_name   = ec1.text_input("景點名稱 *", value=attr.get("name",""))
                        e_loc    = ec2.text_input("所在地區",   value=attr.get("location",""))
                        cat_opts = [""] + CATEGORIES
                        e_cat_i  = cat_opts.index(attr.get("category","")) \
                                   if attr.get("category","") in cat_opts else 0
                        e_cat    = st.selectbox("類別", cat_opts, index=e_cat_i)
                        e_rainy  = st.checkbox("☔ 雨天備案", value=_is_rainy(attr))
                        e_desc   = st.text_area("景點簡介", value=attr.get("description",""), height=70)
                        e_tips   = st.text_area("實用貼士", value=attr.get("tips",""),        height=55)
                        eg1,eg2,eg3,eg4 = st.columns(4)
                        e_open   = eg1.text_input("開放時間", value=attr.get("opening_hours",""))
                        e_best   = eg2.text_input("最佳造訪", value=attr.get("best_time",""))
                        e_dur    = eg3.text_input("建議停留", value=attr.get("suggested_duration",""))
                        e_ticket = eg4.text_input("門票資訊", value=attr.get("ticket_price",""))
                        e_hist   = st.text_area("歷史故事",   value=attr.get("history",""),    height=70)
                        e_acts   = st.text_area("必做活動（JSON）", value=attr.get("activities",""), height=55)
                        e_img    = st.text_input("圖片網址",  value=attr.get("image_url",""))
                        es,ec,_ = st.columns([1,1,4])
                        e_sub = es.form_submit_button("儲存", type="primary")
                        e_can = ec.form_submit_button("取消")
                    if e_sub:
                        if not e_name.strip():
                            st.error("景點名稱為必填。")
                        else:
                            update_row("attractions", "attr_id", attr_id, {
                                "name": e_name.strip(), "location": e_loc.strip(),
                                "description": e_desc.strip(), "tips": e_tips.strip(),
                                "image_url": e_img.strip(), "category": e_cat,
                                "is_rainy_day": "TRUE" if e_rainy else "FALSE",
                                "opening_hours": e_open.strip(), "best_time": e_best.strip(),
                                "suggested_duration": e_dur.strip(), "ticket_price": e_ticket.strip(),
                                "history": e_hist.strip(), "activities": e_acts.strip(),
                            })
                            load_attractions.clear()
                            st.rerun()
                    if e_can:
                        st.rerun()

                # 刪除 + 二次確認
                if st.button("🗑️ 刪除景點", key=f"del_{attr_id}", use_container_width=True):
                    st.session_state[f"confirm_del_{attr_id}"] = True

                if st.session_state.get(f"confirm_del_{attr_id}"):
                    st.warning(f"確認刪除「{name}」？此操作無法復原。")
                    y_col, n_col = st.columns(2)
                    with y_col:
                        if st.button("確定刪除", key=f"yes_{attr_id}",
                                     type="primary", use_container_width=True):
                            delete_row("attractions", "attr_id", attr_id)
                            st.session_state.pop(f"confirm_del_{attr_id}", None)
                            load_attractions.clear()
                            st.rerun()
                    with n_col:
                        if st.button("取消", key=f"no_{attr_id}", use_container_width=True):
                            st.session_state.pop(f"confirm_del_{attr_id}", None)
                            st.rerun()

        st.divider()