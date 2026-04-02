import streamlit as st
import pandas as pd
import uuid
import datetime
from modules.auth import require_auth
from modules.db import read_sheet, append_row
from modules.fx import get_rate, convert
from modules.split import calculate_splits, save_splits
from components.scan_ui import render_scan_section
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib
matplotlib.rcParams['font.family'] = 'Arial Unicode MS'  # 支援中文
from modules.split import settle
from modules.db import update_row

# ── 身份驗證 ──────────────────────────────────────────
require_auth()
trip_id  = st.session_state["trip_id"]
username = st.session_state["member_name"]

st.title("花費記帳")

# ── 讀取成員清單 ───────────────────────────────────────
members_df = read_sheet("members", trip_id)
if members_df.empty:
    member_names = [username]
else:
    member_names = members_df["name"].tolist()

# ── 讀取旅程 base currency ────────────────────────────
trips_df = read_sheet("trips", trip_id=None)
trip_row = trips_df[trips_df["trip_id"] == trip_id]
base_currency = trip_row.iloc[0]["base_currency"] if not trip_row.empty else "TWD"

# ── 常數 ──────────────────────────────────────────────
CATEGORIES = ["餐飲", "交通", "住宿", "購物", "票券", "其他"]
CURRENCIES = ["TWD", "JPY", "USD", "EUR", "KRW", "HKD", "SGD", "GBP", "THB"]

# 初始化預填資料
if "prefill" not in st.session_state:
    st.session_state["prefill"] = {}

with st.expander("📷 掃描帳單", expanded=False):
    scan_data = render_scan_section(
        member_names=member_names,
        base_currency=base_currency,
        currencies=CURRENCIES,
        categories=CATEGORIES,
    )
    if scan_data:
        st.session_state["prefill"] = scan_data
        st.success("已填入表單，請在下方確認後送出")
        st.rerun()

# ══════════════════════════════════════════════════════
# 輸入區：手動表單
# ══════════════════════════════════════════════════════
prefill = st.session_state.get("prefill", {})

with st.expander("＋ 新增花費", expanded=True):
    with st.form("add_expense"):
        col1, col2 = st.columns(2)
        with col1:
            paid_by  = st.selectbox("付款人 *", member_names,
                                    index=member_names.index(username)
                                    if username in member_names else 0)
            date     = st.date_input("日期 *", value=datetime.date.today())
            category = st.selectbox(
                "類別 *", CATEGORIES,
                index=CATEGORIES.index(prefill.get("category", CATEGORIES[0]))
                if prefill.get("category") in CATEGORIES else 0)
        with col2:
            description   = st.text_input("項目名稱",
                                          value=prefill.get("description", ""))
            amount_orig   = st.number_input("金額 *",
                                            value=float(prefill.get("amount_orig", 0.0)),
                                            min_value=0.0, step=1.0)
            orig_currency = st.selectbox(
                "幣別", CURRENCIES,
                index=CURRENCIES.index(prefill.get("orig_currency", base_currency))
                if prefill.get("orig_currency") in CURRENCIES else 0)

        # ── 分帳設定 ──────────────────────────────────
        st.markdown("**分帳設定**")
        involved = st.multiselect("涉及成員 *", member_names,
                                  default=member_names)
        split_type = st.radio("分帳方式", ["AA", "比例", "指定"],
                              horizontal=True)

        # 比例／指定模式的額外輸入
        weights = {}
        if split_type == "比例" and involved:
            st.caption("輸入每人的比例權重（例：2 和 1 代表 2:1）")
            wcols = st.columns(len(involved))
            for i, m in enumerate(involved):
                with wcols[i]:
                    weights[m] = st.number_input(m, min_value=0.0,
                                                 value=1.0, step=0.5,
                                                 key=f"w_{m}")

        elif split_type == "指定" and involved:
            st.caption(f"輸入每人應付金額（{orig_currency}）")
            wcols = st.columns(len(involved))
            for i, m in enumerate(involved):
                with wcols[i]:
                    weights[m] = st.number_input(m, min_value=0.0,
                                                 value=0.0, step=1.0,
                                                 key=f"w_{m}")

        submitted = st.form_submit_button("新增花費", type="primary")

# ── 儲存邏輯（在 form 外面）──────────────────────────
if submitted:
    error = None

    if amount_orig <= 0:
        error = "金額必須大於 0"
    elif not involved:
        error = "請選擇至少一位涉及成員"
    elif split_type == "指定":
        total_assigned = sum(weights.values())
        diff = round(amount_orig - total_assigned, 2)
        if diff > 0:
            error = f"⚠️ 還差 {diff} {orig_currency} 未分配，請調整各人金額"
        elif diff < 0:
            error = f"⚠️ 超出 {abs(diff)} {orig_currency}，各人金額加總不能超過總金額"

    if error:
        st.error(error)
    else:
        with st.spinner("計算匯率並儲存中..."):
            # 1. 匯率換算
            fx_rate     = get_rate(orig_currency, base_currency)
            amount_base = convert(amount_orig, orig_currency, base_currency)

            # 2. 寫入 expenses
            expense_id = "ex_" + uuid.uuid4().hex[:8]
            append_row("expenses", {
                "expense_id":           expense_id,
                "trip_id":              trip_id,
                "paid_by":              paid_by,
                "date":                 str(date),
                "category":             category,
                "description":          description,
                "description_original": "",
                "amount_orig":          amount_orig,
                "orig_currency":        orig_currency,
                "fx_rate":              fx_rate,
                "amount_base":          amount_base,
                "split_type":           split_type,
                "created_at":           datetime.datetime.now().isoformat(timespec="seconds"),
            })

            # 3. 計算分帳
            # 「指定」模式若幣別不是 base currency，先換算每人份額
            if split_type == "指定" and orig_currency != base_currency:
                weights_base = {m: round(v * (fx_rate or 1), 2)
                                for m, v in weights.items()}
            else:
                weights_base = weights

            splits = calculate_splits(
                amount_base=amount_base,
                members=involved,
                split_type=split_type,
                weights=weights_base if split_type != "AA" else None,
            )

            # 4. 寫入 expense_splits
            save_splits(trip_id, expense_id, splits)

        st.success(f"已新增「{description or category}」{amount_orig} {orig_currency}"
                   f"（≈ {amount_base} {base_currency}）")
        st.session_state["prefill"] = {}  # 清除預填
        st.rerun()

# ══════════════════════════════════════════════════════
# 圖表區
# ══════════════════════════════════════════════════════
st.divider()
st.subheader("花費總覽")

expenses_df  = read_sheet("expenses", trip_id)
splits_df    = read_sheet("expense_splits", trip_id)

if expenses_df.empty:
    st.info("還沒有花費記錄，新增後這裡會顯示圖表")
else:
    expenses_df["amount_base"]  = pd.to_numeric(expenses_df["amount_base"],  errors="coerce")
    expenses_df["amount_orig"]  = pd.to_numeric(expenses_df["amount_orig"],  errors="coerce")

    # ── 成員下拉選單 ──────────────────────────────────
    view_options = ["全部"] + member_names
    selected_view = st.selectbox("查看視角", view_options,
                                 label_visibility="collapsed")

    # ── 準備圖表資料 ──────────────────────────────────
    CATEGORY_COLORS = {
        "餐飲": "#FF6B6B",
        "交通": "#4ECDC4",
        "住宿": "#45B7D1",
        "購物": "#FFA07A",
        "票券": "#98D8C8",
        "其他": "#C3A6FF",
    }

    if selected_view == "全部":
        # 圓餅圖：依類別加總
        pie_data = (expenses_df.groupby("category")["amount_base"]
                                .sum().reset_index())
        pie_data.columns = ["category", "amount"]

        # 長條圖：依日期加總
        bar_data = (expenses_df.groupby("date")["amount_base"]
                                .sum().reset_index())
        bar_data.columns = ["date", "amount"]
        chart_title = f"全部花費（{base_currency}）"

    else:
        # 個別成員：從 expense_splits 撈該成員份額
        if splits_df.empty:
            st.info("尚無分帳資料")
            splits_df = pd.DataFrame()
        else:
            splits_df["share_amount"] = pd.to_numeric(
                splits_df["share_amount"], errors="coerce")
            member_splits = splits_df[splits_df["member_name"] == selected_view]

            # join expenses 取得 category 和 date
            merged = member_splits.merge(
                expenses_df[["expense_id", "category", "date"]],
                on="expense_id", how="left")

            pie_data = (merged.groupby("category")["share_amount"]
                               .sum().reset_index())
            pie_data.columns = ["category", "amount"]

            bar_data = (merged.groupby("date")["share_amount"]
                               .sum().reset_index())
            bar_data.columns = ["date", "amount"]
        chart_title = f"{selected_view} 的花費（{base_currency}）"

    # ── 繪圖 ──────────────────────────────────────────
    if not pie_data.empty:
        col1, col2 = st.columns(2)

        # 圓餅圖
        with col1:
            st.markdown("**類別佔比**")
            fig1, ax1 = plt.subplots(figsize=(4, 4))
            colors = [CATEGORY_COLORS.get(c, "#DDDDDD")
                    for c in pie_data["category"]]
            wedges, texts, autotexts = ax1.pie(
                pie_data["amount"],
                colors=colors,
                autopct="%1.1f%%",
                startangle=90,
                textprops={"fontsize": 11},
            )
            # legend 放在圖表下方，不顯示在圓餅旁邊
            ax1.legend(
                wedges,
                pie_data["category"],
                loc="upper center",
                bbox_to_anchor=(0.5, -0.05),
                ncol=3,
                fontsize=10,
                frameon=False,
            )
            ax1.set_title(chart_title, fontsize=12, pad=12)
            fig1.patch.set_alpha(0)
            st.pyplot(fig1)
            plt.close(fig1)


        # 橫向長條圖
        # 橫向長條圖
        with col2:
            st.markdown("**每日花費**")
            # 依筆數動態調整圖表高度，最小 3，每筆加 0.5
            fig_height = max(3, len(bar_data) * 0.6)
            fig2, ax2 = plt.subplots(figsize=(4, fig_height))
            sns.barplot(
                data=bar_data,
                y="date",
                x="amount",
                orient="h",
                color="#4ECDC4",
                ax=ax2,
            )
            ax2.set_xlabel(base_currency, fontsize=10)
            ax2.set_ylabel("")
            ax2.set_title(chart_title, fontsize=12, pad=12)
            ax2.tick_params(axis="y", labelsize=9)

            # 數字放在長條內側右端
            for p in ax2.patches:
                width = p.get_width()
                # 避免數字超出長條（長條太短時改放外側）
                x_max = ax2.get_xlim()[1]
                if width > x_max * 0.2:  # 長條夠長，放內側
                    ax2.annotate(
                        f"{width:,.0f}",
                        (width - x_max * 0.02, p.get_y() + p.get_height() / 2),
                        ha="right", va="center", fontsize=9,
                        color="white", fontweight="bold",
                    )
                else:  # 長條太短，放外側避免看不到
                    ax2.annotate(
                        f"{width:,.0f}",
                        (width + x_max * 0.01, p.get_y() + p.get_height() / 2),
                        ha="left", va="center", fontsize=9, color="#555",
                    )

            fig2.patch.set_alpha(0)
            fig2.tight_layout()
            st.pyplot(fig2)
            plt.close(fig2)
        # 總計
        total = pie_data["amount"].sum()
        st.caption(f"總計：{total:,.0f} {base_currency}")

# ══════════════════════════════════════════════════════
# 結算區
# ══════════════════════════════════════════════════════
st.divider()
st.subheader("結算總覽")

transactions = settle(trip_id)

if not transactions:
    st.success("🎉 目前所有花費已結清！")
else:
    # ── 每人淨餘額 ────────────────────────────────────
    # 重新計算 balance 顯示用
    expenses_df_s  = read_sheet("expenses", trip_id)
    splits_df_s    = read_sheet("expense_splits", trip_id)

    paid_map = {}
    owed_map = {}

    if not expenses_df_s.empty:
        expenses_df_s["amount_base"] = pd.to_numeric(
            expenses_df_s["amount_base"], errors="coerce")
        for _, row in expenses_df_s.iterrows():
            name = row["paid_by"]
            paid_map[name] = paid_map.get(name, 0) + float(row.get("amount_base", 0))

    if not splits_df_s.empty:
        splits_df_s["share_amount"] = pd.to_numeric(
            splits_df_s["share_amount"], errors="coerce")
        pending = splits_df_s[
            splits_df_s["is_settled"].astype(str).str.upper() != "TRUE"]
        for _, row in pending.iterrows():
            name = row["member_name"]
            owed_map[name] = owed_map.get(name, 0) + float(row.get("share_amount", 0))

    all_members = set(paid_map.keys()) | set(owed_map.keys())
    balance = {m: round(paid_map.get(m, 0) - owed_map.get(m, 0), 2)
               for m in all_members}

    # 顯示每人淨餘額
    st.markdown("**每人餘額**")
    bcols = st.columns(len(balance)) if balance else []
    for i, (name, amt) in enumerate(balance.items()):
        with bcols[i]:
            if amt > 0:
                st.metric(name, f"+{amt:,.0f}", delta=f"應收 {base_currency}",
                          delta_color="normal")
            elif amt < 0:
                st.metric(name, f"{amt:,.0f}", delta=f"應付 {base_currency}",
                          delta_color="inverse")
            else:
                st.metric(name, "0", delta="已平衡")

    st.divider()

    # ── 轉帳清單 ──────────────────────────────────────
    st.markdown("**轉帳清單**")
    for i, t in enumerate(transactions):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                f"**{t['from']}** → **{t['to']}**　"
                f"`{t['amount']:,.0f} {base_currency}`"
            )
        with col2:
            if st.button("標記已結清", key=f"settle_{i}"):
                # 把該成員所有未結清的 splits 標記為 TRUE
                if not splits_df_s.empty:
                    member_rows = splits_df_s[
                        (splits_df_s["member_name"] == t["from"]) &
                        (splits_df_s["is_settled"].astype(str).str.upper() != "TRUE")
                    ]
                    for _, srow in member_rows.iterrows():
                        update_row("expense_splits", "split_id",
                                   srow["split_id"], {"is_settled": "TRUE"})
                st.rerun()

# ══════════════════════════════════════════════════════
# 花費列表
# ══════════════════════════════════════════════════════
st.divider()
st.subheader("花費紀錄")

expenses_list_df = read_sheet("expenses", trip_id)

if expenses_list_df.empty:
    st.info("還沒有花費記錄")
else:
    expenses_list_df["amount_base"] = pd.to_numeric(
        expenses_list_df["amount_base"], errors="coerce")
    expenses_list_df["amount_orig"] = pd.to_numeric(
        expenses_list_df["amount_orig"], errors="coerce")

    show_cols = ["date", "paid_by", "category", "description",
                 "amount_orig", "orig_currency", "amount_base", "split_type"]
    show_cols = [c for c in show_cols if c in expenses_list_df.columns]
    expenses_list_df["amount_base"] = expenses_list_df["amount_base"].round(0).astype(int)

    st.dataframe(
        expenses_list_df[show_cols].sort_values("date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )