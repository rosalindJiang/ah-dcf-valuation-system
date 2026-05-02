"""
src/visualizer.py

可视化模块：从数据库读取 DCF 估值结果和历史价格，生成独立交互式 HTML 报告。
使用 Plotly 输出单个 HTML 文件，双击即可在浏览器中打开，无需启动服务器。

报告包含：
  1. 顶部统计摘要卡片
  2. DCF 结果明细表格
  3. 高低估百分比水平条形图
  4. 市场价 vs 内在价值分组对比图
  5. A 股 / H 股历史收盘价走势折线图
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from src import database

logger = logging.getLogger(__name__)

# 默认输出路径
_DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "dcf_report.html",
)

# 图表配色
_COLORS = ["#3498db", "#e74c3c", "#2ecc71", "#9b59b6", "#f39c12",
           "#1abc9c", "#e67e22", "#34495e", "#e91e63", "#00bcd4"]


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

def generate_report(output_path: str = None) -> Optional[str]:
    """
    生成 DCF 估值 HTML 报告，保存到本地文件。

    Args:
        output_path: HTML 输出路径，默认为 data/dcf_report.html。

    Returns:
        生成的 HTML 文件绝对路径，若无数据则返回 None。
    """
    try:
        import plotly.io as pio  # noqa: F401  验证 plotly 已安装
    except ImportError:
        logger.error("未安装 plotly，请执行：pip install plotly")
        raise

    output = output_path or _DEFAULT_OUTPUT

    results = database.query_all_dcf_results()
    if not results:
        logger.warning("数据库中无 DCF 估值结果，请先运行估值 Pipeline。")
        return None

    html = _build_html(results)

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("HTML 报告已生成：%s", output)
    return output


# ──────────────────────────────────────────────
# 图表生成函数
# ──────────────────────────────────────────────

def _chart_upside_bar(results: List[Dict]) -> str:
    """
    生成高低估百分比水平条形图（正值=低估=绿，负值=高估=红）。
    按百分比升序排列，视觉上最低估在最上方。
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    sorted_r = sorted(results, key=lambda x: x["upside_downside_pct"])
    codes  = [r["stock_code"] for r in sorted_r]
    pcts   = [r["upside_downside_pct"] for r in sorted_r]
    colors = ["#27ae60" if p > 0 else "#e74c3c" for p in pcts]
    texts  = [f"{p:+.1f}%" for p in pcts]

    fig = go.Figure(go.Bar(
        x=pcts,
        y=codes,
        orientation="h",
        marker_color=colors,
        text=texts,
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>高低估：%{x:+.2f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1.5, line_color="#95a5a6", line_dash="dash")
    fig.update_layout(
        title=dict(text="各股票高低估百分比（正值 = 低估，负值 = 高估）", font_size=15),
        xaxis_title="高低估 (%)",
        height=max(360, len(codes) * 46),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif"),
        margin=dict(l=20, r=70, t=55, b=40),
        xaxis=dict(gridcolor="#f0f0f0", zerolinecolor="#95a5a6"),
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


def _chart_price_comparison(results: List[Dict]) -> str:
    """
    生成市场价 vs DCF 内在价值分组条形图。
    蓝色为市场价，橙色为内在价值，便于直观对比高低估方向。
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    codes  = [r["stock_code"] for r in results]
    mkt    = [r["latest_market_price"] for r in results]
    iv     = [r["estimated_intrinsic_value"] for r in results]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="市场价",
        x=codes, y=mkt,
        marker_color="#3498db",
        hovertemplate="<b>%{x}</b><br>市场价：%{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="DCF 内在价值",
        x=codes, y=iv,
        marker_color="#e67e22",
        hovertemplate="<b>%{x}</b><br>内在价值：%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="市场价 vs DCF 内在价值对比", font_size=15),
        barmode="group",
        xaxis_title="股票代码",
        yaxis_title="价格（元 / 港元）",
        height=420,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif"),
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
        margin=dict(l=20, r=20, t=55, b=40),
        yaxis=dict(gridcolor="#f0f0f0"),
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


def _chart_table(results: List[Dict]) -> str:
    """
    生成 DCF 估值结果数据表格（Plotly Table）。
    低估行底色绿，高估行底色红，合理区间白色。
    """
    import plotly.graph_objects as go
    import plotly.io as pio

    def rating(v: float) -> str:
        if v >= 30:    return "⬆⬆ 明显低估"
        elif v >= 10:  return "⬆ 低估"
        elif v >= -10: return "→ 合理"
        elif v >= -30: return "⬇ 高估"
        else:          return "⬇⬇ 明显高估"

    row_colors = []
    for r in results:
        v = r["upside_downside_pct"]
        if v >= 10:    row_colors.append("#d5f5e3")
        elif v <= -10: row_colors.append("#fadbd8")
        else:          row_colors.append("#fdfefe")

    fig = go.Figure(go.Table(
        header=dict(
            values=["股票代码", "估值日期", "市场价", "内在价值",
                    "高低估(%)", "WACC", "终端增长率", "综合评级"],
            fill_color="#2c3e50",
            font=dict(color="white", size=13),
            align="center",
            height=38,
        ),
        cells=dict(
            values=[
                [r["stock_code"] for r in results],
                [r["valuation_date"] for r in results],
                [f"{r['latest_market_price']:.2f}" for r in results],
                [f"{r['estimated_intrinsic_value']:.2f}" for r in results],
                [f"{r['upside_downside_pct']:+.1f}%" for r in results],
                [f"{r['wacc']:.1%}" for r in results],
                [f"{r['terminal_growth_rate']:.1%}" for r in results],
                [rating(r["upside_downside_pct"]) for r in results],
            ],
            fill_color=[row_colors] * 8,
            align="center",
            font=dict(size=12),
            height=32,
        ),
    ))
    fig.update_layout(
        title=dict(text="DCF 估值结果明细", font_size=15),
        height=max(280, len(results) * 36 + 110),
        margin=dict(l=20, r=20, t=55, b=20),
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif"),
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


def _chart_price_history() -> str:
    """
    生成 A 股 / H 股历史收盘价走势折线图（左右双图）。
    数据直接从 stock_prices 表读取，若无数据则跳过对应股票。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("A 股历史收盘价走势", "H 股历史收盘价走势"),
        horizontal_spacing=0.08,
    )

    for i, code in enumerate(settings.A_SHARE_STOCKS):
        hist = database.query_price_history(code)
        if not hist:
            continue
        fig.add_trace(go.Scatter(
            x=[r["trade_date"] for r in hist],
            y=[r["close"] for r in hist],
            name=f"A:{code}",
            mode="lines",
            line=dict(color=_COLORS[i % len(_COLORS)], width=1.5),
            hovertemplate=f"<b>{code}</b><br>%{{x}}<br>收盘价：%{{y:.2f}}<extra></extra>",
        ), row=1, col=1)

    for i, code in enumerate(settings.H_SHARE_STOCKS):
        hist = database.query_price_history(code)
        if not hist:
            continue
        fig.add_trace(go.Scatter(
            x=[r["trade_date"] for r in hist],
            y=[r["close"] for r in hist],
            name=f"H:{code}",
            mode="lines",
            line=dict(color=_COLORS[i % len(_COLORS)], width=1.5),
            hovertemplate=f"<b>{code}</b><br>%{{x}}<br>收盘价：%{{y:.2f}}<extra></extra>",
        ), row=1, col=2)

    fig.update_layout(
        title=dict(text="历史收盘价走势（{} ~ {}）".format(settings.START_DATE, settings.END_DATE), font_size=15),
        height=440,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial, sans-serif"),
        legend=dict(x=1.02, y=1, bgcolor="rgba(255,255,255,0.85)", font_size=11),
        margin=dict(l=20, r=130, t=60, b=40),
    )
    fig.update_xaxes(gridcolor="#f0f0f0", tickangle=-30)
    fig.update_yaxes(gridcolor="#f0f0f0")
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


# ──────────────────────────────────────────────
# HTML 页面组装
# ──────────────────────────────────────────────

def _build_html(results: List[Dict]) -> str:
    """
    将各图表 div 组装为完整的 HTML 页面，内嵌 Plotly CDN 和自定义 CSS。

    Args:
        results: DCF 估值结果列表。

    Returns:
        完整 HTML 字符串。
    """
    total       = len(results)
    undervalued = sum(1 for r in results if r["upside_downside_pct"] > 0)
    overvalued  = total - undervalued
    avg_upside  = sum(r["upside_downside_pct"] for r in results) / total if total else 0
    gen_time    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c_table   = _chart_table(results)
    c_upside  = _chart_upside_bar(results)
    c_compare = _chart_price_comparison(results)
    c_history = _chart_price_history()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AH 股 DCF 估值报告</title>
  <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      background: #f0f2f5;
      color: #2c3e50;
      min-height: 100vh;
    }}
    /* ── 顶部标题栏 ── */
    .header {{
      background: linear-gradient(135deg, #1a252f 0%, #2980b9 100%);
      color: white;
      padding: 28px 40px;
    }}
    .header h1 {{ font-size: 26px; font-weight: 700; letter-spacing: .5px; margin-bottom: 6px; }}
    .header p  {{ font-size: 13px; opacity: .80; }}
    /* ── 统计卡片行 ── */
    .stats-row {{
      display: flex;
      gap: 16px;
      padding: 20px 40px;
      background: white;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }}
    .stat-card {{
      flex: 1;
      background: #f8fafc;
      border-radius: 10px;
      padding: 16px 20px;
      border-left: 4px solid #3498db;
    }}
    .stat-card.green  {{ border-color: #27ae60; }}
    .stat-card.red    {{ border-color: #e74c3c; }}
    .stat-card.orange {{ border-color: #e67e22; }}
    .stat-value {{ font-size: 28px; font-weight: 700; }}
    .stat-label {{ font-size: 12px; color: #7f8c8d; margin-top: 4px; }}
    /* ── 内容区 ── */
    .container {{ padding: 24px 40px; max-width: 1400px; margin: 0 auto; }}
    .chart-card {{
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,.07);
      padding: 20px 16px;
      margin-bottom: 22px;
    }}
    /* ── 免责声明 ── */
    .disclaimer {{
      background: #fef9e7;
      border: 1px solid #f9ca24;
      border-radius: 8px;
      padding: 12px 18px;
      font-size: 13px;
      color: #7d6608;
      margin-bottom: 20px;
      line-height: 1.6;
    }}
    /* ── 底部 ── */
    .footer {{
      text-align: center;
      padding: 18px;
      font-size: 12px;
      color: #95a5a6;
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>AH 股 DCF 估值分析报告</h1>
  <p>
    数据来源：AkShare &nbsp;|&nbsp;
    数据区间：{settings.START_DATE} ~ {settings.END_DATE} &nbsp;|&nbsp;
    生成时间：{gen_time}
  </p>
</div>

<div class="stats-row">
  <div class="stat-card">
    <div class="stat-value">{total}</div>
    <div class="stat-label">估值股票总数</div>
  </div>
  <div class="stat-card green">
    <div class="stat-value">{undervalued}</div>
    <div class="stat-label">低估股票数量</div>
  </div>
  <div class="stat-card red">
    <div class="stat-value">{overvalued}</div>
    <div class="stat-label">高估股票数量</div>
  </div>
  <div class="stat-card orange">
    <div class="stat-value">{avg_upside:+.1f}%</div>
    <div class="stat-label">平均高低估幅度</div>
  </div>
</div>

<div class="container">

  <div class="disclaimer">
    ⚠️ <strong>免责声明：</strong>本报告为 Demo 简化 DCF 估值，基准营收和总股本来自年报近似值（config/settings.py STOCK_FINANCIALS），
    WACC 按行业手工设定，未接入实时财务报表，净负债未扣减。估值结果仅供学习和系统验证，<strong>不构成任何投资建议</strong>。
  </div>

  <div class="chart-card">{c_table}</div>
  <div class="chart-card">{c_upside}</div>
  <div class="chart-card">{c_compare}</div>
  <div class="chart-card">{c_history}</div>

</div>

<div class="footer">
  AH 股 DCF 估值计算系统 &nbsp;·&nbsp; 生成于 {gen_time}
</div>

</body>
</html>"""
