import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def _get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def _get_sheet(sheet_name: str):
    if "spreadsheet_id" not in st.secrets:
        st.error("⚠️ secrets.toml 缺少 spreadsheet_id，請確認設定")
        st.stop()
    gc = _get_client()
    sh = gc.open_by_key(st.secrets["spreadsheet_id"])
    return sh.worksheet(sheet_name)

@st.cache_data(ttl=60)
def read_sheet(sheet_name: str, trip_id: str = None) -> pd.DataFrame:
    ws = _get_sheet(sheet_name)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    if sheet_name == "itinerary":
        df = df.drop(columns=["route"], errors="ignore")
    if trip_id and "trip_id" in df.columns:
        df = df[df["trip_id"] == trip_id]
    return df.reset_index(drop=True)

def append_row(sheet_name: str, data: dict) -> bool:
    try:
        ws = _get_sheet(sheet_name)
        headers = ws.row_values(1)
        filtered = {k: v for k, v in data.items() if k != "route"}
        row = [filtered.get(h, "") for h in headers]
        ws.append_row(row, value_input_option="USER_ENTERED")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"寫入失敗：{e}")
        return False

def update_row(sheet_name: str, id_col: str, id_val: str, data: dict) -> bool:
    try:
        ws = _get_sheet(sheet_name)
        headers = ws.row_values(1)
        if id_col not in headers:
            st.error(f"欄位 '{id_col}' 不存在於 {sheet_name}")
            return False
        col_idx = headers.index(id_col) + 1
        cell = ws.find(id_val, in_column=col_idx)
        if not cell:
            st.error(f"找不到 {id_col} = {id_val}")
            return False

        # 一次 batch update
        updates = []
        for key, val in {k: v for k, v in data.items() if k != "route"}.items():
            if key in headers:
                col = headers.index(key) + 1
                updates.append({
                    "range": gspread.utils.rowcol_to_a1(cell.row, col),
                    "values": [[val]]
                })
        if updates:
            ws.batch_update(updates)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"更新失敗：{e}")
        return False



def delete_row(sheet_name: str, id_col: str, id_val: str) -> bool:
    try:
        ws = _get_sheet(sheet_name)
        headers = ws.row_values(1)
        if id_col not in headers:
            st.error(f"欄位 '{id_col}' 不存在於 {sheet_name}")
            return False
        col_idx = headers.index(id_col) + 1
        cell = ws.find(id_val, in_column=col_idx)
        if not cell:
            st.error(f"找不到 {id_col} = {id_val}")
            return False
        ws.delete_rows(cell.row)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"刪除失敗：{e}")
        return False