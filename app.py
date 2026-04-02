import streamlit as st
from modules.auth import create_trip, join_trip, set_session, get_current_user, logout


def inject_css():
    with open("assets/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

inject_css()

st.set_page_config(
    page_title="旅遊規劃 App",
    page_icon="✈️",
    layout="wide"
)

user = get_current_user()

if not user:
    st.title("旅遊規劃 App")
    st.caption("家人共同記錄旅程的小工具")
    st.divider()

    tab_join, tab_create = st.tabs(["加入旅程", "建立新旅程"])

    with tab_join:
        st.subheader("輸入旅程代碼加入")
        join_code = st.text_input("旅程代碼（6位）", max_chars=6, placeholder="例如 JP2025")
        member_name = st.text_input("你的名字", key='join_member_name')
        if st.button("加入", use_container_width=True):
            if not join_code or not member_name:
                st.error("請填寫代碼和名字")
            else:
                trip = join_trip(join_code.strip().upper(), member_name.strip())
                if trip:
                    set_session(trip, member_name.strip())
                    st.success(f"歡迎，{member_name.strip()}！正在進入旅程...")
                    st.rerun()
                else:
                    st.error("找不到這個代碼，請確認是否輸入正確")

    with tab_create:
        st.subheader("建立一趟新旅程")
        trip_name = st.text_input("旅程名稱", placeholder="例如 日本關西五日遊")
        destination = st.text_input("目的地", placeholder="例如 日本關西")  # ← 新增這行
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("出發日期")
        with col2:
            end_date = st.date_input("回程日期")
        base_currency = st.selectbox(
            "結算幣別",
            ["TWD", "USD", "JPY", "EUR", "HKD", "GBP"],
            index=0
        )
        your_name = st.text_input("你的名字", key='create_your_name')
        if st.button("建立旅程", use_container_width=True):
            if not trip_name or not your_name:
                st.error("請填寫旅程名稱和你的名字")
            elif end_date < start_date:
                st.error("回程日期不能早於出發日期")
            else:
                trip = create_trip(trip_name, destination, start_date, end_date, base_currency)
                if trip:
                    join_trip(trip["join_code"], your_name)
                    set_session(trip, your_name)
                    st.success(f"旅程建立成功！")
                    st.info(f"旅程代碼：**{trip['join_code']}**　請把這個代碼傳給同行家人")
                    st.rerun()
                else:
                    st.error("建立失敗，請再試一次")

else:
    st.title(f"✈️ {user['trip_name']}")
    st.caption(f"成員：{user['member_name']}　結算幣別：{user['base_currency']}")
    st.divider()

    trips_df = __import__('modules.db', fromlist=['read_sheet']).read_sheet("trips")
    members_df = __import__('modules.db', fromlist=['read_sheet']).read_sheet(
        "members", trip_id=user["trip_id"]
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric("旅程代碼", user.get("trip_id", "")[:8] if False else
                  trips_df[trips_df["trip_id"] == user["trip_id"]]["join_code"].values[0]
                  if not trips_df.empty else "—")
    with col2:
        member_count = len(members_df) if not members_df.empty else 0
        st.metric("成員人數", f"{member_count} 人")

    if not members_df.empty:
        st.write("**同行成員：**　" + "　".join(members_df["name"].tolist()))

    st.divider()
    st.caption("請從左側選單選擇功能")

    if st.button("登出", type="secondary"):
        logout()
        st.rerun()