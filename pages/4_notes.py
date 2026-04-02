import streamlit as st
import pandas as pd
import uuid
import datetime
from modules.auth import require_auth
from modules.db import read_sheet, append_row, update_row

# ── 身份驗證 ──────────────────────────────────────────
require_auth()
trip_id = st.session_state["trip_id"]

st.title("注意事項")

# ── 常數 ──────────────────────────────────────────────
NOTE_TYPES = ["門票", "住宿", "交通", "其他"]
today = datetime.date.today()

# ── 新增注意事項 ───────────────────────────────────────
with st.expander("＋ 新增注意事項", expanded=False):
    with st.form("add_note"):
        title    = st.text_input("標題 *")
        note_type = st.selectbox("類型", NOTE_TYPES)
        content  = st.text_area("詳細說明（選填）", height=80)
        deadline = st.date_input("截止日期（選填）",
                                  value=None,
                                  min_value=datetime.date(2020, 1, 1))
        submitted = st.form_submit_button("新增", type="primary")

    if submitted:
        if not title:
            st.error("標題必填")
        else:
            append_row("notes", {
                "note_id":  "nt_" + uuid.uuid4().hex[:8],
                "trip_id":  trip_id,
                "type":     note_type,
                "title":    title,
                "content":  content,
                "deadline": str(deadline) if deadline else "",
                "done":     "FALSE",
            })
            st.success(f"已新增「{title}」")
            st.rerun()

st.divider()

# ── 讀取資料 ──────────────────────────────────────────
df = read_sheet("notes", trip_id)

if df.empty:
    df = pd.DataFrame(columns=[
        "note_id", "trip_id", "type", "title",
        "content", "deadline", "done"
    ])

# ── 篩選列 ────────────────────────────────────────────
col1, col2 = st.columns([2, 1])
with col1:
    type_filter = st.selectbox("篩選類型",
                                ["全部"] + NOTE_TYPES,
                                label_visibility="collapsed")
with col2:
    show_done = st.checkbox("顯示已完成", value=False)

# 套用篩選
filtered = df.copy()
if type_filter != "全部":
    filtered = filtered[filtered["type"] == type_filter]
if not show_done:
    filtered = filtered[
        filtered["done"].astype(str).str.upper() != "TRUE"
    ]

# ── 待辦清單 ──────────────────────────────────────────
if filtered.empty:
    st.info("沒有符合條件的項目" if not df.empty else "還沒有注意事項，在上方新增吧！")
else:
    for _, row in filtered.iterrows():
        note_id  = row["note_id"]
        is_done  = str(row.get("done", "FALSE")).upper() == "TRUE"
        deadline_str = str(row.get("deadline", "")).strip()

        # 逾期判斷
        is_overdue = False
        if deadline_str and not is_done:
            try:
                deadline_date = datetime.date.fromisoformat(deadline_str)
                is_overdue = deadline_date < today
            except ValueError:
                pass

        # 每個項目一個 container
        with st.container():
            col1, col2 = st.columns([5, 1])

            with col1:
                # 勾選框（即時同步）
                def make_callback(nid, current_done):
                    def callback():
                        new_val = "TRUE" if not current_done else "FALSE"
                        update_row("notes", "note_id", nid, {"done": new_val})
                    return callback

                checked = st.checkbox(
                    label=" ",
                    value=is_done,
                    key=f"chk_{note_id}",
                    on_change=make_callback(note_id, is_done),
                )

                # 標題列
                title_display = f"~~{row['title']}~~" if is_done else row['title']
                if is_overdue:
                    st.markdown(f"🔴 **{row['title']}**　"
                                f"<span style='color:#FF4B4B;font-size:12px'>"
                                f"逾期！截止：{deadline_str}</span>",
                                unsafe_allow_html=True)
                else:
                    deadline_tag = f"　截止：{deadline_str}" if deadline_str else ""
                    st.markdown(f"{'~~' if is_done else ''}**{row['title']}**"
                                f"{'~~' if is_done else ''}"
                                f"<span style='color:#888;font-size:12px'>"
                                f"{deadline_tag}</span>",
                                unsafe_allow_html=True)

                # 詳細說明（有的話才顯示）
                if row.get("content"):
                    st.caption(row["content"])

            with col2:
                # 類型標籤
                st.caption(row.get("type", ""))

            st.divider()