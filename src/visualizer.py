"""
src/visualizer.py

可视化模块：从数据库读取 DCF 估值结果和历史价格，生成独立交互式 HTML 报告。
使用 Plotly CDN 输出单个 HTML 文件，双击在浏览器打开，无需启动服务器。

报告包含交互式筛选面板：
  - 股票代码多选（复选框，实时更新所有图表）
  - 历史价格日期区间（日期选择器，实时更新走势图）

图表列表：
  1. 顶部统计摘要卡片
  2. DCF 结果明细表格
  3. 高低估百分比水平条形图
  4. 市场价 vs 内在价值分组对比图
  5. A 股 / H 股历史收盘价走势折线图（独立双图）
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from src import database

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "dcf_report.html",
)


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
    output = output_path or _DEFAULT_OUTPUT

    results = database.query_all_dcf_results()
    if not results:
        logger.warning("数据库中无 DCF 估值结果，请先运行估值 Pipeline。")
        return None

    # 预加载所有股票的历史价格，嵌入 HTML 供 JS 筛选
    all_stocks = settings.A_SHARE_STOCKS + settings.H_SHARE_STOCKS
    price_history: Dict[str, List[Dict]] = {}
    for code in all_stocks:
        rows = database.query_price_history(code)
        price_history[code] = [{"date": r["trade_date"], "close": r["close"]} for r in rows]

    html = _build_html(results, price_history)

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("HTML 报告已生成：%s", output)
    return output


# ──────────────────────────────────────────────
# CSS（独立函数，避免 f-string 大括号转义问题）
# ──────────────────────────────────────────────

def _css() -> str:
    return """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      background: #f0f2f5;
      color: #2c3e50;
      min-height: 100vh;
    }
    /* 顶部标题栏 */
    .header {
      background: linear-gradient(135deg, #1a252f 0%, #2980b9 100%);
      color: white;
      padding: 28px 40px;
    }
    .header h1 { font-size: 26px; font-weight: 700; letter-spacing: .5px; margin-bottom: 6px; }
    .header p  { font-size: 13px; opacity: .80; }

    /* 统计卡片行 */
    .stats-row {
      display: flex;
      gap: 16px;
      padding: 20px 40px;
      background: white;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }
    .stat-card {
      flex: 1;
      background: #f8fafc;
      border-radius: 10px;
      padding: 16px 20px;
      border-left: 4px solid #3498db;
    }
    .stat-card.green  { border-color: #27ae60; }
    .stat-card.red    { border-color: #e74c3c; }
    .stat-card.orange { border-color: #e67e22; }
    .stat-value { font-size: 28px; font-weight: 700; }
    .stat-label { font-size: 12px; color: #7f8c8d; margin-top: 4px; }

    /* 筛选面板 */
    .filter-panel {
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,.07);
      padding: 18px 22px;
      margin-bottom: 20px;
    }
    .filter-panel h3 {
      font-size: 14px;
      font-weight: 600;
      color: #2c3e50;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .filter-row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .filter-row:last-child { margin-bottom: 0; }
    .filter-label {
      font-size: 13px;
      font-weight: 600;
      color: #555;
      min-width: 90px;
    }
    /* 股票复选框 */
    .stock-cb {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
      font-size: 13px;
      padding: 5px 10px;
      border: 1px solid #dce1e7;
      border-radius: 20px;
      background: #f8fafc;
      transition: all .15s;
      user-select: none;
    }
    .stock-cb:hover { border-color: #3498db; background: #eaf4fd; }
    .stock-cb input[type=checkbox] { accent-color: #3498db; width: 14px; height: 14px; }
    .badge {
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 3px;
      letter-spacing: .3px;
    }
    .badge-a { background: #e8f5e9; color: #2e7d32; }
    .badge-h { background: #fff3e0; color: #e65100; }
    /* 快捷按钮 */
    .btn-sm {
      font-size: 12px;
      padding: 5px 12px;
      border: 1px solid #bdc3c7;
      border-radius: 5px;
      background: white;
      cursor: pointer;
      color: #555;
      transition: all .15s;
    }
    .btn-sm:hover { background: #ecf0f1; border-color: #95a5a6; }
    /* 日期输入 */
    .date-input {
      font-size: 13px;
      padding: 5px 10px;
      border: 1px solid #dce1e7;
      border-radius: 6px;
      color: #2c3e50;
      outline: none;
    }
    .date-input:focus { border-color: #3498db; }
    .date-sep { color: #95a5a6; font-size: 13px; }

    /* 内容区 */
    .container { padding: 24px 40px; max-width: 1400px; margin: 0 auto; }
    .chart-card {
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,.07);
      padding: 20px 16px;
      margin-bottom: 22px;
    }
    .history-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 22px;
    }
    .history-row .chart-card { margin-bottom: 0; }

    /* 空状态提示 */
    .empty-state {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 120px;
      color: #95a5a6;
      font-size: 14px;
    }

    /* 免责声明 */
    .disclaimer {
      background: #fef9e7;
      border: 1px solid #f9ca24;
      border-radius: 8px;
      padding: 12px 18px;
      font-size: 13px;
      color: #7d6608;
      margin-bottom: 20px;
      line-height: 1.6;
    }
    /* 底部 */
    .footer {
      text-align: center;
      padding: 18px;
      font-size: 12px;
      color: #95a5a6;
    }
    @media (max-width: 900px) {
      .stats-row, .container, .header { padding-left: 16px; padding-right: 16px; }
      .history-row { grid-template-columns: 1fr; }
    }
    """


# ──────────────────────────────────────────────
# JavaScript（独立函数）
# ──────────────────────────────────────────────

def _js() -> str:
    return r"""
    const COLORS = ["#3498db","#e74c3c","#2ecc71","#9b59b6","#f39c12",
                    "#1abc9c","#e67e22","#34495e","#e91e63","#00bcd4"];

    /* ── 筛选状态读取 ── */
    function getSelectedStocks() {
        return Array.from(document.querySelectorAll('.stock-checkbox:checked'))
                    .map(cb => cb.value);
    }
    function getDateRange() {
        return {
            start: document.getElementById('startDate').value,
            end:   document.getElementById('endDate').value
        };
    }

    /* ── 统计卡片更新 ── */
    function renderStats(data) {
        const n = data.length;
        const under = data.filter(r => r.upside_downside_pct > 0).length;
        const over  = n - under;
        const avg   = n ? data.reduce((s,r) => s + r.upside_downside_pct, 0) / n : 0;
        document.getElementById('stat-total').textContent = n;
        document.getElementById('stat-under').textContent = under;
        document.getElementById('stat-over').textContent  = over;
        document.getElementById('stat-avg').textContent   = (avg >= 0 ? '+' : '') + avg.toFixed(1) + '%';
    }

    /* ── 评级标签 ── */
    function rating(v) {
        if (v >= 30)  return "⬆⬆ 明显低估";
        if (v >= 10)  return "⬆ 低估";
        if (v >= -10) return "→ 合理";
        if (v >= -30) return "⬇ 高估";
        return "⬇⬇ 明显高估";
    }

    /* ── 明细表格 ── */
    function renderTable(data) {
        const el = document.getElementById('chart-table');
        if (!data.length) { el.innerHTML = '<div class="empty-state">请至少选择一只股票</div>'; return; }
        const rowColors = data.map(r =>
            r.upside_downside_pct >= 10 ? "#d5f5e3" :
            r.upside_downside_pct <= -10 ? "#fadbd8" : "#fdfefe"
        );
        const trace = {
            type: "table",
            header: {
                values: ["股票代码","估值日期","市场价","内在价值","高低估(%)","WACC","终端增长率","综合评级"],
                fill: {color: "#2c3e50"},
                font: {color: "white", size: 13},
                align: "center",
                height: 38
            },
            cells: {
                values: [
                    data.map(r => r.stock_code),
                    data.map(r => r.valuation_date),
                    data.map(r => r.latest_market_price.toFixed(2)),
                    data.map(r => r.estimated_intrinsic_value.toFixed(2)),
                    data.map(r => (r.upside_downside_pct >= 0 ? "+" : "") + r.upside_downside_pct.toFixed(1) + "%"),
                    data.map(r => (r.wacc * 100).toFixed(1) + "%"),
                    data.map(r => (r.terminal_growth_rate * 100).toFixed(1) + "%"),
                    data.map(r => rating(r.upside_downside_pct))
                ],
                fill: {color: Array(8).fill(rowColors)},
                align: "center",
                font: {size: 12},
                height: 32
            }
        };
        Plotly.react(el, [trace], {
            title: {text: "DCF 估值结果明细", font: {size: 15}},
            height: Math.max(280, data.length * 36 + 110),
            margin: {l:20, r:20, t:55, b:20},
            paper_bgcolor: "white",
            font: {family: "Arial, sans-serif"}
        }, {displayModeBar: false});
    }

    /* ── 高低估条形图 ── */
    function renderUpsideBar(data) {
        const el = document.getElementById('chart-upside');
        if (!data.length) { el.innerHTML = '<div class="empty-state">请至少选择一只股票</div>'; return; }
        const sorted = [...data].sort((a,b) => a.upside_downside_pct - b.upside_downside_pct);
        const pcts = sorted.map(r => r.upside_downside_pct);
        Plotly.react(el, [{
            type: "bar", orientation: "h",
            x: pcts,
            y: sorted.map(r => r.stock_code),
            marker: {color: pcts.map(p => p > 0 ? "#27ae60" : "#e74c3c")},
            text: pcts.map(p => (p >= 0 ? "+" : "") + p.toFixed(1) + "%"),
            textposition: "outside",
            hovertemplate: "<b>%{y}</b><br>高低估：%{x:+.2f}%<extra></extra>"
        }], {
            title: {text: "各股票高低估百分比（正值 = 低估，负值 = 高估）", font: {size: 15}},
            xaxis: {title: "高低估 (%)", gridcolor: "#f0f0f0", zerolinecolor: "#95a5a6"},
            height: Math.max(360, sorted.length * 46),
            plot_bgcolor: "white", paper_bgcolor: "white",
            font: {family: "Arial, sans-serif"},
            margin: {l:20, r:70, t:55, b:40},
            shapes: [{type:"line", x0:0, x1:0, y0:-0.5, y1:sorted.length-0.5,
                      line:{color:"#95a5a6", width:1.5, dash:"dash"}}]
        }, {displayModeBar: false});
    }

    /* ── 市场价 vs 内在价值 ── */
    function renderPriceComparison(data) {
        const el = document.getElementById('chart-compare');
        if (!data.length) { el.innerHTML = '<div class="empty-state">请至少选择一只股票</div>'; return; }
        const codes = data.map(r => r.stock_code);
        Plotly.react(el, [
            {type:"bar", name:"市场价",    x:codes, y:data.map(r => r.latest_market_price),
             marker:{color:"#3498db"}, hovertemplate:"<b>%{x}</b><br>市场价：%{y:.2f}<extra></extra>"},
            {type:"bar", name:"DCF 内在价值", x:codes, y:data.map(r => r.estimated_intrinsic_value),
             marker:{color:"#e67e22"}, hovertemplate:"<b>%{x}</b><br>内在价值：%{y:.2f}<extra></extra>"}
        ], {
            title: {text: "市场价 vs DCF 内在价值对比", font: {size: 15}},
            barmode: "group",
            xaxis: {title: "股票代码"},
            yaxis: {title: "价格（元 / 港元）", gridcolor: "#f0f0f0"},
            height: 420,
            plot_bgcolor: "white", paper_bgcolor: "white",
            font: {family: "Arial, sans-serif"},
            legend: {x:0.01, y:0.99, bgcolor:"rgba(255,255,255,0.85)"},
            margin: {l:20, r:20, t:55, b:40}
        }, {displayModeBar: false});
    }

    /* ── 历史走势图（A 股 / H 股各一个 div） ── */
    function renderPriceHistory(selectedStocks, start, end) {
        function buildTraces(codes, prefix) {
            return codes.map((code, i) => {
                const hist = (ALL_HISTORY[code] || []).filter(h =>
                    (!start || h.date >= start) && (!end || h.date <= end)
                );
                return {
                    type: "scatter", mode: "lines",
                    name: prefix + ":" + code,
                    x: hist.map(h => h.date),
                    y: hist.map(h => h.close),
                    line: {color: COLORS[i % COLORS.length], width: 1.5},
                    hovertemplate: "<b>" + code + "</b><br>%{x}<br>收盘价：%{y:.2f}<extra></extra>"
                };
            });
        }
        function histLayout(title) {
            return {
                title: {text: title, font: {size: 14}},
                height: 350,
                plot_bgcolor: "white", paper_bgcolor: "white",
                font: {family: "Arial, sans-serif"},
                xaxis: {gridcolor: "#f0f0f0", tickangle: -30},
                yaxis: {gridcolor: "#f0f0f0"},
                legend: {bgcolor: "rgba(255,255,255,0.85)", font:{size:11}},
                margin: {l:50, r:20, t:45, b:50}
            };
        }

        const aSelected = selectedStocks.filter(c => A_STOCKS.includes(c));
        const hSelected = selectedStocks.filter(c => H_STOCKS.includes(c));

        const elA = document.getElementById('chart-history-a');
        const elH = document.getElementById('chart-history-h');

        if (!aSelected.length) {
            elA.innerHTML = '<div class="empty-state">未选择 A 股</div>';
        } else {
            Plotly.react(elA, buildTraces(aSelected, "A"), histLayout("A 股历史收盘价走势"),
                         {displayModeBar: false});
        }
        if (!hSelected.length) {
            elH.innerHTML = '<div class="empty-state">未选择 H 股</div>';
        } else {
            Plotly.react(elH, buildTraces(hSelected, "H"), histLayout("H 股历史收盘价走势"),
                         {displayModeBar: false});
        }
    }

    /* ── 主渲染函数（所有图表联动更新） ── */
    function renderAll() {
        const selected = getSelectedStocks();
        const {start, end} = getDateRange();
        const dcf = ALL_DCF.filter(r => selected.includes(r.stock_code));

        renderStats(dcf);
        renderTable(dcf);
        renderUpsideBar(dcf);
        renderPriceComparison(dcf);
        renderPriceHistory(selected, start, end);
    }

    /* ── 快捷按钮 ── */
    function selectAll()   { document.querySelectorAll('.stock-checkbox').forEach(cb => cb.checked = true);  renderAll(); }
    function selectNone()  { document.querySelectorAll('.stock-checkbox').forEach(cb => cb.checked = false); renderAll(); }
    function selectAOnly() { document.querySelectorAll('.stock-checkbox').forEach(cb => { cb.checked = A_STOCKS.includes(cb.value); }); renderAll(); }
    function selectHOnly() { document.querySelectorAll('.stock-checkbox').forEach(cb => { cb.checked = H_STOCKS.includes(cb.value); }); renderAll(); }

    /* ── 页面初始化 ── */
    document.addEventListener('DOMContentLoaded', renderAll);
    """


# ──────────────────────────────────────────────
# HTML 页面组装
# ──────────────────────────────────────────────

def _build_html(results: List[Dict], price_history: Dict[str, List[Dict]]) -> str:
    """
    将数据嵌入 HTML，所有图表由浏览器端 Plotly.js 渲染，支持实时筛选。

    Args:
        results:       DCF 估值结果列表（每股最新一条）。
        price_history: {stock_code: [{date, close}]} 历史价格字典。

    Returns:
        完整 HTML 字符串。
    """
    total       = len(results)
    undervalued = sum(1 for r in results if r["upside_downside_pct"] > 0)
    overvalued  = total - undervalued
    avg_upside  = sum(r["upside_downside_pct"] for r in results) / total if total else 0
    gen_time    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 日期范围默认值（从历史数据中取 min/max）
    all_dates = [h["date"] for hist in price_history.values() for h in hist]
    min_date  = min(all_dates) if all_dates else settings.START_DATE
    max_date  = max(all_dates) if all_dates else settings.END_DATE

    # 嵌入数据
    dcf_json     = json.dumps(results,       ensure_ascii=False)
    history_json = json.dumps(price_history, ensure_ascii=False)
    a_stocks_json = json.dumps(settings.A_SHARE_STOCKS)
    h_stocks_json = json.dumps(settings.H_SHARE_STOCKS)

    # 构建股票复选框
    cb_parts = []
    for code in settings.A_SHARE_STOCKS + settings.H_SHARE_STOCKS:
        market = "A" if code in settings.A_SHARE_STOCKS else "H"
        cb_parts.append(
            f'<label class="stock-cb">'
            f'<input type="checkbox" class="stock-checkbox" value="{code}" '
            f'onchange="renderAll()" checked>'
            f'<span class="badge badge-{market.lower()}">{market}</span>'
            f'{code}</label>'
        )
    checkboxes_html = "\n            ".join(cb_parts)

    css = _css()
    js  = _js()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AH 股 DCF 估值报告</title>
  <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
  <style>{css}</style>
</head>
<body>

<!-- 顶部标题 -->
<div class="header">
  <h1>AH 股 DCF 估值分析报告</h1>
  <p>数据来源：AkShare &nbsp;|&nbsp;
     数据区间：{settings.START_DATE} ~ {settings.END_DATE} &nbsp;|&nbsp;
     生成时间：{gen_time}</p>
</div>

<!-- 统计卡片 -->
<div class="stats-row">
  <div class="stat-card">
    <div class="stat-value" id="stat-total">{total}</div>
    <div class="stat-label">估值股票总数</div>
  </div>
  <div class="stat-card green">
    <div class="stat-value" id="stat-under">{undervalued}</div>
    <div class="stat-label">低估股票数量</div>
  </div>
  <div class="stat-card red">
    <div class="stat-value" id="stat-over">{overvalued}</div>
    <div class="stat-label">高估股票数量</div>
  </div>
  <div class="stat-card orange">
    <div class="stat-value" id="stat-avg">{avg_upside:+.1f}%</div>
    <div class="stat-label">平均高低估幅度</div>
  </div>
</div>

<!-- 主内容 -->
<div class="container">

  <!-- 筛选面板 -->
  <div class="filter-panel">
    <h3>🔍 筛选条件</h3>

    <div class="filter-row">
      <span class="filter-label">股票代码</span>
      {checkboxes_html}
      <button class="btn-sm" onclick="selectAll()">全选</button>
      <button class="btn-sm" onclick="selectNone()">全不选</button>
      <button class="btn-sm" onclick="selectAOnly()">仅 A 股</button>
      <button class="btn-sm" onclick="selectHOnly()">仅 H 股</button>
    </div>

    <div class="filter-row">
      <span class="filter-label">历史价格区间</span>
      <input type="date" id="startDate" class="date-input"
             value="{min_date}" min="{min_date}" max="{max_date}"
             onchange="renderAll()">
      <span class="date-sep">至</span>
      <input type="date" id="endDate" class="date-input"
             value="{max_date}" min="{min_date}" max="{max_date}"
             onchange="renderAll()">
      <button class="btn-sm" onclick="document.getElementById('startDate').value='{min_date}';
                                      document.getElementById('endDate').value='{max_date}';
                                      renderAll()">重置日期</button>
    </div>
  </div>

  <!-- 免责声明 -->
  <div class="disclaimer">
    ⚠️ <strong>免责声明：</strong>本报告为 Demo 简化 DCF 估值，基准营收和总股本来自年报近似值
    （config/settings.py STOCK_FINANCIALS），WACC 按行业手工设定，未接入实时财务报表，净负债未扣减。
    估值结果仅供学习和系统验证，<strong>不构成任何投资建议</strong>。
  </div>

  <!-- 图表区 -->
  <div class="chart-card"><div id="chart-table"></div></div>
  <div class="chart-card"><div id="chart-upside"></div></div>
  <div class="chart-card"><div id="chart-compare"></div></div>

  <!-- 历史走势（A/H 并排） -->
  <div class="history-row">
    <div class="chart-card"><div id="chart-history-a"></div></div>
    <div class="chart-card"><div id="chart-history-h"></div></div>
  </div>

</div>

<div class="footer">
  AH 股 DCF 估值计算系统 &nbsp;·&nbsp; 生成于 {gen_time}
</div>

<!-- 嵌入数据 -->
<script>
const ALL_DCF     = {dcf_json};
const ALL_HISTORY = {history_json};
const A_STOCKS    = {a_stocks_json};
const H_STOCKS    = {h_stocks_json};
</script>

<!-- 渲染与筛选逻辑 -->
<script>{js}</script>

</body>
</html>"""
