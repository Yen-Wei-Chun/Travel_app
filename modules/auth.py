import streamlit as st
import uuid
import random
import string
from datetime import datetime
from modules.db import read_sheet, append_row

def _generate_trip_id() -> str:
    return str(uuid.uuid4())[:8]

def _generate_join_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

def create_trip(trip_name: str, destination: str, start_date: str, end_date: str, base_currency: str) -> dict | None:
    join_code = _generate_join_code()
    trip_id = _generate_trip_id()

    existing = read_sheet("trips")
    if not existing.empty and join_code in existing["join_code"].values:
        join_code = _generate_join_code()

    data = {
        "trip_id": trip_id,
        "join_code": join_code,
        "trip_name": trip_name,
        "destination": destination,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "base_currency": base_currency,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    ok = append_row("trips", data)
    if ok:
        return data
    return None

def join_trip(join_code: str, member_name: str) -> dict | None:
    trips_df = read_sheet("trips")
    if trips_df.empty:
        return None

    matched = trips_df[trips_df["join_code"] == join_code.upper().strip()]
    if matched.empty:
        return None

    trip = matched.iloc[0].to_dict()
    trip_id = trip["trip_id"]

    members_df = read_sheet("members", trip_id=trip_id)
    if not members_df.empty and member_name.strip() in members_df["name"].values:
        return trip

    member_data = {
        "member_id": "m_" + str(uuid.uuid4())[:8],
        "trip_id": trip_id,
        "name": member_name.strip(),
        "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    append_row("members", member_data)
    return trip

def set_session(trip: dict, member_name: str):
    st.session_state["trip_id"] = trip["trip_id"]
    st.session_state["trip_name"] = trip["trip_name"]
    st.session_state["member_name"] = member_name.strip()
    st.session_state["base_currency"] = trip["base_currency"]
    st.session_state["authenticated"] = True

def get_current_user() -> dict | None:
    if not st.session_state.get("authenticated"):
        return None
    return {
        "trip_id": st.session_state.get("trip_id"),
        "trip_name": st.session_state.get("trip_name"),
        "member_name": st.session_state.get("member_name"),
        "base_currency": st.session_state.get("base_currency")
    }

def require_auth() -> dict:
    user = get_current_user()
    if not user:
        st.warning("請先從首頁輸入旅程代碼加入旅程")
        st.stop()
    return user

def logout():
    for key in ["trip_id", "trip_name", "member_name", "base_currency", "authenticated"]:
        st.session_state.pop(key, None)