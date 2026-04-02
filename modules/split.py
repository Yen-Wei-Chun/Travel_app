from __future__ import annotations
import uuid
import datetime
from typing import Literal
import streamlit as st
from modules.db import read_sheet, append_row


# ── 分帳：計算每人應付金額 ────────────────────────────

def calculate_splits(
    amount_base: float,
    members: list[str],
    split_type: Literal["AA", "比例", "指定"],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    回傳 {member_name: share_amount}（base currency）

    - AA：weights 不需要傳
    - 比例：weights = {"小明": 2, "小華": 1}（會自動正規化）
    - 指定：weights = {"小明": 300, "小華": 150}（直接當作金額）
    """
    if not members:
        return {}

    if split_type == "AA":
        share = round(amount_base / len(members), 2)
        result = {m: share for m in members}
        # 處理浮點誤差：把差額補到第一個人
        diff = round(amount_base - sum(result.values()), 2)
        result[members[0]] = round(result[members[0]] + diff, 2)
        return result

    if split_type == "比例":
        total_weight = sum(weights.values())
        result = {}
        for m in members:
            result[m] = round(amount_base * weights.get(m, 0) / total_weight, 2)
        diff = round(amount_base - sum(result.values()), 2)
        result[members[0]] = round(result[members[0]] + diff, 2)
        return result

    if split_type == "指定":
        # 直接用傳入金額，但做一次四捨五入
        return {m: round(weights.get(m, 0), 2) for m in members}

    raise ValueError(f"不支援的 split_type：{split_type}")


# ── 分帳：寫入 expense_splits 表 ─────────────────────

def save_splits(
    trip_id: str,
    expense_id: str,
    splits: dict[str, float],
) -> bool:
    """把 calculate_splits 的結果寫入 expense_splits 表"""
    try:
        for member_name, share_amount in splits.items():
            append_row("expense_splits", {
                "split_id":    "sp_" + uuid.uuid4().hex[:8],
                "expense_id":  expense_id,
                "trip_id":     trip_id,
                "member_name": member_name,
                "share_amount": share_amount,
                "is_settled":  "FALSE",
            })
        return True
    except Exception as e:
        st.error(f"分帳寫入失敗：{e}")
        return False


# ── 結算：計算誰欠誰多少 ──────────────────────────────

def settle(trip_id: str) -> list[dict]:
    """
    回傳最小化轉帳清單：
    [{"from": "小華", "to": "小明", "amount": 300.0}, ...]
    """
    # 每人付出總額
    expenses_df = read_sheet("expenses", trip_id)
    paid = {}
    if not expenses_df.empty:
        for _, row in expenses_df.iterrows():
            name = row["paid_by"]
            paid[name] = paid.get(name, 0) + float(row.get("amount_base", 0))

    # 每人應付總份額
    splits_df = read_sheet("expense_splits", trip_id)
    owed = {}
    if not splits_df.empty:
        # 只計算未結清的
        pending = splits_df[splits_df["is_settled"].astype(str).str.upper() != "TRUE"]
        for _, row in pending.iterrows():
            name = row["member_name"]
            owed[name] = owed.get(name, 0) + float(row.get("share_amount", 0))

    # 所有涉及的成員
    all_members = set(paid.keys()) | set(owed.keys())

    # 淨餘額：正 = 別人欠你，負 = 你欠別人
    balance = {m: round(paid.get(m, 0) - owed.get(m, 0), 2) for m in all_members}

    # 貪心演算法：最小化轉帳次數
    creditors = sorted([(v, k) for k, v in balance.items() if v > 0], reverse=True)
    debtors   = sorted([(abs(v), k) for k, v in balance.items() if v < 0], reverse=True)
    transactions = []

    creditors = [[amt, name] for amt, name in creditors]
    debtors   = [[amt, name] for amt, name in debtors]

    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        credit_amt, creditor = creditors[i]
        debt_amt,   debtor   = debtors[j]
        transfer = round(min(credit_amt, debt_amt), 2)

        transactions.append({
            "from":   debtor,
            "to":     creditor,
            "amount": transfer,
        })

        creditors[i][0] = round(credit_amt - transfer, 2)
        debtors[j][0]   = round(debt_amt   - transfer, 2)

        if creditors[i][0] == 0:
            i += 1
        if debtors[j][0] == 0:
            j += 1

    return transactions