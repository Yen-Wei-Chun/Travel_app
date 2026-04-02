import base64
import json
import re
import anthropic
import streamlit as st


def scan_receipt(image_bytes: bytes) -> dict | None:
    """
    接收圖片 bytes，呼叫 Claude Vision API，
    回傳結構化 dict 或 None（失敗時）
    """
    # 圖片轉 base64
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    # 判斷圖片格式（簡單判斷 magic bytes）
    if image_bytes[:4] == b'\x89PNG':
        media_type = "image/png"
    else:
        media_type = "image/jpeg"

    prompt = """你是一個收據辨識助手。請分析這張收據圖片，回傳以下 JSON 格式，不要有任何其他文字：

{
  "category": "餐飲／交通／住宿／購物／票券／其他 其中一個",
  "item_zh": "項目名稱（中文）",
  "item_original": "項目原始文字（若已是中英文則和 item_zh 相同）",
  "was_translated": true 或 false,
  "amount": 數字（不含符號和逗號）,
  "currency": "三位幣別代碼，例如 JPY、TWD、USD",
  "confidence": "high、medium、low 其中一個"
}

規則：
- amount 只取總金額，不含小費建議
- 若看不清楚金額，confidence 填 low
- 若收據是日文／韓文／其他語言，item_zh 翻譯成中文，item_original 保留原文，was_translated 填 true
- 只回傳 JSON，不要有任何說明文字"""

    try:
        client = anthropic.Anthropic(
            api_key= st.secrets["anthropic_api_key"]
        )
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()

        # 清除可能的 markdown code fence
        raw = re.sub(r"```json|```", "", raw).strip()

        return json.loads(raw)

    except json.JSONDecodeError:
        st.error("AI 回傳格式錯誤，請重新掃描")
        return None
    except Exception as e:
        st.error(f"掃描失敗：{e}")
        return None