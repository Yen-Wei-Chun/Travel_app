import streamlit as st
from modules.receipt_scanner import scan_receipt


def render_scan_section(member_names: list, base_currency: str,
                        currencies: list, categories: list) -> dict | None:
    """
    渲染掃帳單 UI。
    回傳用戶確認後的花費 dict，供 3_expenses.py 使用。
    若尚未確認則回傳 None。
    """

    st.markdown("#### 掃描帳單")

    # 上傳方式：手機拍照 or 桌機上傳
    col1, col2 = st.columns(2)
    with col1:
        camera_img = st.camera_input("拍照")
    with col2:
        upload_img = st.file_uploader("或上傳圖片",
                                      type=["jpg", "jpeg", "png"])

    image_bytes = None
    if camera_img:
        image_bytes = camera_img.getvalue()
    elif upload_img:
        image_bytes = upload_img.getvalue()

    # 有圖片就掃描
    if image_bytes:
        # 避免同一張圖重複呼叫 API
        img_hash = hash(image_bytes)
        if st.session_state.get("last_scan_hash") != img_hash:
            with st.spinner("AI 辨識中..."):
                result = scan_receipt(image_bytes)
            if result:
                st.session_state["scan_result"] = result
                st.session_state["last_scan_hash"] = img_hash

    # 顯示辨識結果 + 可編輯預覽表單
    if "scan_result" in st.session_state:
        result = st.session_state["scan_result"]

        # confidence 警示
        if result.get("confidence") == "low":
            st.warning("⚠️ 辨識信心度偏低，請仔細確認以下欄位")
        elif result.get("confidence") == "medium":
            st.info("ℹ️ 部分欄位可能需要確認")

        # 翻譯提示
        if result.get("was_translated"):
            st.caption(f"原文：{result.get('item_original')} → 已翻譯為中文")

        st.markdown("**確認辨識結果**")

        with st.form("scan_confirm"):
            col1, col2 = st.columns(2)
            with col1:
                item_zh = st.text_input(
                    "項目名稱",
                    value=result.get("item_zh", ""))
                category = st.selectbox(
                    "類別",
                    categories,
                    index=categories.index(result.get("category", "其他"))
                    if result.get("category") in categories else 0)
            with col2:
                amount = st.number_input(
                    "金額",
                    value=float(result.get("amount", 0)),
                    min_value=0.0, step=1.0)
                currency = st.selectbox(
                    "幣別",
                    currencies,
                    index=currencies.index(result.get("currency", base_currency))
                    if result.get("currency") in currencies else 0)

            confirmed = st.form_submit_button("使用此結果填入表單", type="primary")

        if confirmed:
            # 清除 session state，準備下一次掃描
            del st.session_state["scan_result"]
            del st.session_state["last_scan_hash"]
            return {
                "description":          item_zh,
                "description_original": result.get("item_original", ""),
                "category":             category,
                "amount_orig":          amount,
                "orig_currency":        currency,
            }

    return None