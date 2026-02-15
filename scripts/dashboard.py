"""Algora Dashboard — generates a self-contained HTML dashboard with charts.

Usage:
    python -X utf8 -m scripts.dashboard              # generate data/dashboard.html
    python -X utf8 -m scripts.dashboard --open        # generate and open in browser
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.config import DATA_DIR
from src.db import (
    init_db,
    get_channel_stats_history,
    get_published_posts_count,
    get_top_products,
    get_posts_by_type,
    get_posts_by_category,
    get_engagement_summary,
    get_engagement_by_post_type,
    get_engagement_by_category,
    get_top_posts_by_views,
)


TYPE_LABELS = {
    "product": "Находка дня",
    "niche_review": "Обзор ниши",
    "weekly_top": "Топ недели",
    "beginner_mistake": "Ошибка новичка",
    "product_of_week": "Товар недели",
}


def _build_dashboard_html() -> str:
    """Collect all data and render the dashboard HTML."""
    init_db()

    # --- Data collection ---
    posts_count = get_published_posts_count()

    # Subscriber history
    history = get_channel_stats_history(60)
    hist_dates = []
    hist_subs = []
    hist_posts = []
    if history:
        for row in reversed(history):
            hist_dates.append(row["date"])
            hist_subs.append(row["subscribers"])
            hist_posts.append(row["posts_total"])

    # Engagement summary
    eng = get_engagement_summary() or {}

    # Engagement by post type
    eng_by_type = get_engagement_by_post_type()
    etype_labels = []
    etype_avg = []
    etype_max = []
    etype_cnt = []
    for row in eng_by_type:
        label = TYPE_LABELS.get(row["post_type"], row["post_type"] or "Другое")
        etype_labels.append(label)
        etype_avg.append(row["avg_views"])
        etype_max.append(row["max_views"])
        etype_cnt.append(row["cnt"])

    # Engagement by category
    eng_by_cat = get_engagement_by_category()
    ecat_labels = []
    ecat_avg = []
    ecat_cnt = []
    for row in eng_by_cat[:12]:
        ecat_labels.append(row["category"])
        ecat_avg.append(row["avg_views"])
        ecat_cnt.append(row["cnt"])

    # Posts by type (pie chart)
    by_type = get_posts_by_type()
    ptype_labels = []
    ptype_values = []
    for row in by_type:
        label = TYPE_LABELS.get(row["post_type"], row["post_type"] or "Без типа")
        ptype_labels.append(label)
        ptype_values.append(row["cnt"])

    # Posts by category (bar)
    by_cat = get_posts_by_category()
    pcat_labels = []
    pcat_values = []
    for row in by_cat[:15]:
        pcat_labels.append(row["category"] or "—")
        pcat_values.append(row["cnt"])

    # Top products
    top = get_top_products(10)
    top_data = []
    for p in top:
        raw = json.loads(p["raw_json"])
        title = raw.get("title_ru", raw.get("title_cn", "???"))[:40]
        top_data.append({
            "title": title,
            "score": round(p["total_score"], 1),
            "margin": round(p["margin_pct"], 0),
            "competitors": p["wb_competitors"],
        })

    # Top posts by views
    top_viewed = get_top_posts_by_views(10)
    tv_data = []
    for p in top_viewed:
        ptype = TYPE_LABELS.get(p["post_type"], p["post_type"] or "?")
        tv_data.append({
            "views": p["views"],
            "type": ptype,
            "category": p["category"] or "—",
            "score": round(p["total_score"] or 0, 1),
        })

    # Growth metrics
    growth_total = 0
    growth_daily = 0.0
    latest_subs = 0
    if len(hist_subs) >= 2:
        latest_subs = hist_subs[-1]
        growth_total = hist_subs[-1] - hist_subs[0]
        growth_daily = growth_total / len(hist_subs)
    elif hist_subs:
        latest_subs = hist_subs[-1]

    # Generation timestamp
    from datetime import datetime, timezone
    generated_at = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    # --- Render HTML ---
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ALGORA Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    padding: 20px;
  }}
  h1 {{
    text-align: center;
    font-size: 28px;
    margin-bottom: 8px;
    background: linear-gradient(135deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .subtitle {{
    text-align: center;
    color: #888;
    font-size: 14px;
    margin-bottom: 24px;
  }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .kpi {{
    background: #1a1d27;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    border: 1px solid #2a2d3a;
  }}
  .kpi-value {{
    font-size: 32px;
    font-weight: 700;
    color: #667eea;
  }}
  .kpi-value.green {{ color: #4ade80; }}
  .kpi-value.orange {{ color: #fb923c; }}
  .kpi-value.purple {{ color: #a78bfa; }}
  .kpi-label {{
    font-size: 13px;
    color: #888;
    margin-top: 4px;
  }}
  .charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
  }}
  .chart-card {{
    background: #1a1d27;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #2a2d3a;
  }}
  .chart-card h3 {{
    font-size: 16px;
    margin-bottom: 12px;
    color: #ccc;
  }}
  .chart-box {{
    width: 100%;
    min-height: 320px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  th {{
    text-align: left;
    padding: 8px 12px;
    border-bottom: 2px solid #2a2d3a;
    color: #888;
    font-weight: 600;
  }}
  td {{
    padding: 8px 12px;
    border-bottom: 1px solid #1f2230;
  }}
  tr:hover td {{ background: #1f2230; }}
  .score-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
  }}
  .score-high {{ background: #064e3b; color: #4ade80; }}
  .score-mid {{ background: #422006; color: #fb923c; }}
  .score-low {{ background: #450a0a; color: #f87171; }}
  .footer {{
    text-align: center;
    color: #555;
    font-size: 12px;
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid #1f2230;
  }}
  @media (max-width: 600px) {{
    .charts-grid {{ grid-template-columns: 1fr; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
</style>
</head>
<body>

<h1>ALGORA Dashboard</h1>
<p class="subtitle">Аналитика канала @algora_trends &bull; Обновлено: {generated_at}</p>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-value">{latest_subs}</div>
    <div class="kpi-label">Подписчиков</div>
  </div>
  <div class="kpi">
    <div class="kpi-value purple">{posts_count}</div>
    <div class="kpi-label">Постов опубликовано</div>
  </div>
  <div class="kpi">
    <div class="kpi-value green">{'+' if growth_total >= 0 else ''}{growth_total}</div>
    <div class="kpi-label">Рост подписчиков</div>
  </div>
  <div class="kpi">
    <div class="kpi-value orange">{growth_daily:+.1f}/день</div>
    <div class="kpi-label">Средний рост</div>
  </div>
  <div class="kpi">
    <div class="kpi-value">{eng.get('total_views', 0):,}</div>
    <div class="kpi-label">Всего просмотров</div>
  </div>
  <div class="kpi">
    <div class="kpi-value green">{eng.get('avg_views', 0):.0f}</div>
    <div class="kpi-label">Ср. просмотры/пост</div>
  </div>
</div>

<!-- Charts Row 1: Subscribers + Engagement by Type -->
<div class="charts-grid">
  <div class="chart-card">
    <h3>Рост подписчиков</h3>
    <div class="chart-box" id="chart-subs"></div>
  </div>
  <div class="chart-card">
    <h3>Средние просмотры по типам постов</h3>
    <div class="chart-box" id="chart-eng-type"></div>
  </div>
</div>

<!-- Charts Row 2: Posts pie + Category engagement -->
<div class="charts-grid">
  <div class="chart-card">
    <h3>Распределение постов по типам</h3>
    <div class="chart-box" id="chart-posts-pie"></div>
  </div>
  <div class="chart-card">
    <h3>Просмотры по категориям</h3>
    <div class="chart-box" id="chart-eng-cat"></div>
  </div>
</div>

<!-- Charts Row 3: Posts by category + Top posts table -->
<div class="charts-grid">
  <div class="chart-card">
    <h3>Посты по категориям</h3>
    <div class="chart-box" id="chart-posts-cat"></div>
  </div>
  <div class="chart-card">
    <h3>Топ постов по просмотрам</h3>
    <table>
      <thead>
        <tr><th>#</th><th>Просмотры</th><th>Тип</th><th>Категория</th><th>Score</th></tr>
      </thead>
      <tbody>
        {''.join(
            f'<tr><td>{i+1}</td><td><b>{p["views"]}</b></td><td>{p["type"]}</td>'
            f'<td>{p["category"]}</td>'
            f'<td><span class="score-badge {"score-high" if p["score"] >= 7 else "score-mid" if p["score"] >= 5 else "score-low"}">'
            f'{p["score"]}</span></td></tr>'
            for i, p in enumerate(tv_data)
        ) if tv_data else '<tr><td colspan="5" style="text-align:center;color:#555">Нет данных</td></tr>'}
      </tbody>
    </table>
  </div>
</div>

<!-- Top Products Table -->
<div class="charts-grid">
  <div class="chart-card" style="grid-column: 1 / -1;">
    <h3>Топ-10 товаров по рейтингу</h3>
    <table>
      <thead>
        <tr><th>#</th><th>Товар</th><th>Score</th><th>Маржа %</th><th>Конкуренты WB</th></tr>
      </thead>
      <tbody>
        {''.join(
            f'<tr><td>{i+1}</td><td>{p["title"]}</td>'
            f'<td><span class="score-badge {"score-high" if p["score"] >= 7 else "score-mid" if p["score"] >= 5 else "score-low"}">'
            f'{p["score"]}</span></td>'
            f'<td>{p["margin"]:.0f}%</td><td>{p["competitors"]}</td></tr>'
            for i, p in enumerate(top_data)
        ) if top_data else '<tr><td colspan="5" style="text-align:center;color:#555">Нет данных</td></tr>'}
      </tbody>
    </table>
  </div>
</div>

<div class="footer">
  Сгенерировано автоматически &bull; ALGORA Analytics Dashboard
</div>

<script>
const plotLayout = {{
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: {{ color: '#aaa', size: 12 }},
  margin: {{ l: 50, r: 20, t: 10, b: 50 }},
  xaxis: {{ gridcolor: '#1f2230', tickfont: {{ size: 11 }} }},
  yaxis: {{ gridcolor: '#1f2230', tickfont: {{ size: 11 }} }},
}};
const plotConfig = {{ responsive: true, displayModeBar: false }};

// 1. Subscribers chart
Plotly.newPlot('chart-subs', [{{
  x: {json.dumps(hist_dates)},
  y: {json.dumps(hist_subs)},
  type: 'scatter',
  mode: 'lines+markers',
  line: {{ color: '#667eea', width: 2 }},
  marker: {{ size: 5 }},
  fill: 'tozeroy',
  fillcolor: 'rgba(102,126,234,0.1)',
}}], {{
  ...plotLayout,
  yaxis: {{ ...plotLayout.yaxis, title: 'Подписчики' }},
}}, plotConfig);

// 2. Engagement by post type (bar)
Plotly.newPlot('chart-eng-type', [
  {{
    x: {json.dumps(etype_labels)},
    y: {json.dumps(etype_avg)},
    type: 'bar',
    name: 'Ср. просмотры',
    marker: {{ color: '#667eea', borderRadius: 4 }},
  }},
  {{
    x: {json.dumps(etype_labels)},
    y: {json.dumps(etype_max)},
    type: 'bar',
    name: 'Макс просмотры',
    marker: {{ color: 'rgba(102,126,234,0.3)' }},
  }}
], {{
  ...plotLayout,
  barmode: 'group',
  legend: {{ font: {{ size: 11 }}, x: 0, y: 1.15, orientation: 'h' }},
}}, plotConfig);

// 3. Posts pie chart
Plotly.newPlot('chart-posts-pie', [{{
  labels: {json.dumps(ptype_labels)},
  values: {json.dumps(ptype_values)},
  type: 'pie',
  hole: 0.45,
  marker: {{
    colors: ['#667eea', '#764ba2', '#4ade80', '#fb923c', '#f87171', '#38bdf8'],
  }},
  textinfo: 'label+percent',
  textfont: {{ size: 12 }},
}}], {{
  ...plotLayout,
  showlegend: false,
  margin: {{ l: 20, r: 20, t: 10, b: 20 }},
}}, plotConfig);

// 4. Engagement by category (horizontal bar)
Plotly.newPlot('chart-eng-cat', [{{
  y: {json.dumps(ecat_labels)},
  x: {json.dumps(ecat_avg)},
  type: 'bar',
  orientation: 'h',
  marker: {{ color: '#a78bfa' }},
  text: {json.dumps(ecat_cnt)}.map(n => n + ' постов'),
  textposition: 'auto',
  textfont: {{ size: 11 }},
}}], {{
  ...plotLayout,
  margin: {{ l: 140, r: 20, t: 10, b: 40 }},
  xaxis: {{ ...plotLayout.xaxis, title: 'Ср. просмотры' }},
  yaxis: {{ ...plotLayout.yaxis, autorange: 'reversed' }},
}}, plotConfig);

// 5. Posts by category (bar)
Plotly.newPlot('chart-posts-cat', [{{
  x: {json.dumps(pcat_labels)},
  y: {json.dumps(pcat_values)},
  type: 'bar',
  marker: {{ color: '#4ade80' }},
}}], {{
  ...plotLayout,
  xaxis: {{ ...plotLayout.xaxis, tickangle: -45 }},
  yaxis: {{ ...plotLayout.yaxis, title: 'Количество постов' }},
  margin: {{ l: 50, r: 20, t: 10, b: 100 }},
}}, plotConfig);
</script>

</body>
</html>"""
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Algora Dashboard Generator")
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open dashboard in browser after generation",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output file path (default: data/dashboard.html)",
    )
    args = parser.parse_args()

    out_path = Path(args.output) if args.output else DATA_DIR / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Generating dashboard...")
    html = _build_dashboard_html()
    out_path.write_text(html, encoding="utf-8")
    logger.info("Dashboard saved to {}", out_path)

    if args.open:
        webbrowser.open(str(out_path.resolve()))
        logger.info("Opened in browser")


if __name__ == "__main__":
    main()
