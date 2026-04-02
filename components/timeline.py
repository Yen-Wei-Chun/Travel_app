import streamlit as st
import streamlit.components.v1 as components
from datetime import date as dt_date
from urllib.parse import quote


def _group_by_date(rows: list[dict]) -> dict:
    groups: dict[str, list] = {}
    for i, row in enumerate(rows):
        key = str(row.get("date", "未指定"))
        groups.setdefault(key, []).append({**row, "_idx": i})
    return groups


def _fmt_date(s: str) -> str:
    try:
        d = dt_date.fromisoformat(s)
        days = ["一", "二", "三", "四", "五", "六", "日"]
        return f"{d.month}/{d.day}（{days[d.weekday()]}）"
    except ValueError:
        return s


def _maps_url(row: dict) -> str:
    try:
        lat, lng = float(row["lat"]), float(row["lng"])
        return f"https://maps.google.com/maps?q={lat},{lng}"
    except (TypeError, ValueError, KeyError):
        loc = row.get("location", "")
        return f"https://maps.google.com/maps?q={quote(str(loc))}" if loc else ""


def _build_html(groups: dict, selected_idx: int) -> str:
    day_html = []

    for date_str, rows in groups.items():
        items = []
        for row in rows:
            idx       = row["_idx"]
            sel       = "selected" if idx == selected_idx else ""
            loc       = row.get("location", "（未命名）")
            transport = row.get("transport", "")
            duration  = row.get("duration", "")
            highlights = row.get("highlights", "")
            maps_url  = _maps_url(row)

            t_badge    = f'<span class="badge t-badge">{transport}</span>' if transport else ""
            d_badge    = f'<span class="badge d-badge">⏱ {duration}</span>' if duration else ""
            hl_row     = f'<div class="hl">{highlights}</div>' if highlights else ""
            maps_btn   = (
                f'<a class="maps-link" href="{maps_url}" target="_blank" '
                f'onclick="event.stopPropagation()">在地圖開啟 ↗</a>'
                if maps_url else ""
            )

            items.append(f"""
<div class="stop {sel}" data-idx="{idx}" onclick="selectStop({idx})">
  <div class="axis"><div class="line"></div><div class="dot"></div></div>
  <div class="card">
    <div class="card-top">
      <span class="loc">{loc}</span>
      <div class="card-right">
        <span class="badges">{t_badge}{d_badge}</span>
        {maps_btn}
      </div>
    </div>
    {hl_row}
  </div>
</div>""")

        day_html.append(f"""
<div class="day-group">
  <div class="day-label">{_fmt_date(date_str)}</div>
  {"".join(items)}
</div>""")

    sections = "\n".join(day_html)

    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:13px;color:#1a1a1a;background:transparent;padding:4px 2px 16px}}
.day-label{{font-size:11px;font-weight:700;color:#999;letter-spacing:.07em;
  text-transform:uppercase;padding:14px 0 6px 32px}}
.stop{{display:flex;gap:0;padding:2px 4px;border-radius:10px;cursor:pointer;transition:background .12s}}
.stop:hover{{background:#f5f5f5}}
.stop.selected .card{{border-color:#378ADD;background:#EBF4FD;box-shadow:0 0 0 2px #B5D4F4}}
.stop.selected .dot{{background:#185FA5;transform:scale(1.4)}}
.axis{{display:flex;flex-direction:column;align-items:center;width:26px;flex-shrink:0;padding-top:14px}}
.line{{width:2px;flex:1;min-height:6px;background:#DDD}}
.dot{{width:9px;height:9px;border-radius:50%;background:#CCC;flex-shrink:0;transition:all .18s;z-index:1}}
.stop:first-child .line{{visibility:hidden}}
.card{{flex:1;margin:4px 0 4px 8px;border:1px solid #EBEBEB;border-radius:10px;
  padding:9px 12px;background:#fff;transition:all .18s}}
.card-top{{display:flex;align-items:flex-start;justify-content:space-between;gap:6px}}
.card-right{{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0}}
.loc{{font-size:14px;font-weight:600;line-height:1.35}}
.badges{{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}}
.badge{{font-size:11px;padding:2px 7px;border-radius:99px;white-space:nowrap}}
.t-badge{{background:#EBF4FD;color:#0C447C;border:.5px solid #B5D4F4}}
.d-badge{{background:#F5F5F5;color:#555;border:.5px solid #DDD}}
.maps-link{{font-size:11px;color:#185FA5;text-decoration:none;white-space:nowrap;
  padding:2px 8px;border-radius:99px;border:.5px solid #B5D4F4;background:#EBF4FD;
  transition:background .12s;display:inline-block}}
.maps-link:hover{{background:#d0e8f8}}
.hl{{font-size:12px;color:#666;margin-top:6px;padding-top:6px;
  border-top:.5px solid #F0F0F0;line-height:1.5}}
</style></head><body>
<div id="tl">{sections}</div>
<script>
function selectStop(idx) {{
  // 更新選中樣式
  document.querySelectorAll('.stop').forEach(e => e.classList.remove('selected'));
  const el = document.querySelector('.stop[data-idx="' + idx + '"]');
  if (el) el.classList.add('selected');

  // 透過修改 parent URL 的 query param 通知 Streamlit rerun
  try {{
    const url = new URL(window.parent.location.href);
    url.searchParams.set('stop_idx', idx);
    window.parent.history.replaceState(null, '', url.toString());
    // 觸發 Streamlit 偵測 query param 變化
    window.parent.dispatchEvent(new PopStateEvent('popstate'));
  }} catch(e) {{
    // cross-origin fallback：用 postMessage
    window.parent.postMessage({{type: 'stop_select', idx: idx}}, '*');
  }}
}}

// 初始化：捲動到選中項
(function() {{
  const el = document.querySelector('.stop[data-idx="{selected_idx}"]');
  if (el) el.scrollIntoView({{block: 'nearest', behavior: 'smooth'}});
}})();
</script>
</body></html>"""


def render_timeline(
    rows: list[dict],
    selected_idx: int = 0,
    height: int = 520,
) -> None:
    if not rows:
        st.info("尚無行程資料，請在下方表格新增停留點。")
        return
    groups   = _group_by_date(rows)
    html_str = _build_html(groups, selected_idx)
    components.html(html_str, height=height, scrolling=True)