"""
app.py

AH 股 DCF 估值系统 Web 服务入口。

运行方式：
    python app.py

浏览器访问：http://localhost:5000

功能：
  - 股票下拉选择（支持多选，demo 为 10 只，生产可扩展至 7000+）
  - 日期范围选择（触发数据下载 + DCF 估值 + 可视化）
  - 估值结果按（股票代码，结束日期）追加存入数据库，不覆盖历史记录
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify

from src.utils import setup_logging
from src.database import init_tables, query_price_history
from src.data_downloader import download_a_share_data, download_hk_stock_data
from src.valuation_pipeline import run_pipeline
from config import settings

setup_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    """主页：渲染选股 + 日期范围 + 图表界面。"""
    stocks = []
    for code in settings.A_SHARE_STOCKS:
        stocks.append({
            "code": code,
            "name": settings.STOCK_NAMES.get(code, code),
            "market": "A",
        })
    for code in settings.H_SHARE_STOCKS:
        stocks.append({
            "code": code,
            "name": settings.STOCK_NAMES.get(code, code),
            "market": "H",
        })
    return render_template(
        "index.html",
        stocks=stocks,
        default_start=settings.START_DATE,
        default_end=settings.END_DATE,
    )


@app.route("/api/run", methods=["POST"])
def api_run():
    """
    执行完整估值流程并返回 JSON 结果。

    Request body (JSON):
        stocks     : list[str]  股票代码列表
        start_date : str        数据起始日期 YYYY-MM-DD
        end_date   : str        数据结束日期 YYYY-MM-DD（同时作为 valuation_date）

    Response (JSON):
        results   : list[dict]  DCF 估值结果
        history   : dict        {code: [{date, close}]} 价格历史
        a_stocks  : list[str]   本次 A 股代码
        h_stocks  : list[str]   本次 H 股代码
        errors    : list[str]   警告信息（下载失败等）
    """
    payload    = request.get_json(force=True)
    stocks     = payload.get("stocks", [])
    start_date = payload.get("start_date", settings.START_DATE)
    end_date   = payload.get("end_date",   settings.END_DATE)

    if not stocks:
        return jsonify({"error": "请至少选择一只股票"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "请填写完整的日期范围"}), 400
    if start_date > end_date:
        return jsonify({"error": "起始日期不能晚于结束日期"}), 400

    a_stocks = [s for s in stocks if s in settings.A_SHARE_STOCKS]
    h_stocks = [s for s in stocks if s in settings.H_SHARE_STOCKS]

    # Step 1: 确保数据库已初始化
    init_tables()

    errors = []

    # Step 2: 下载行情数据
    if a_stocks:
        try:
            download_a_share_data(stock_list=a_stocks, start_date=start_date, end_date=end_date)
        except Exception as e:
            msg = f"A 股数据下载失败：{e}"
            errors.append(msg)
            logger.error(msg)

    if h_stocks:
        try:
            download_hk_stock_data(stock_list=h_stocks, start_date=start_date, end_date=end_date)
        except Exception as e:
            msg = f"H 股数据下载失败：{e}"
            errors.append(msg)
            logger.error(msg)

    # Step 3: DCF 估值（end_date 作为 valuation_date，支持按日期范围追加）
    results = run_pipeline(
        stock_list=stocks,
        valuation_date=end_date,
        start_date=start_date,
    )

    # Step 4: 读取价格历史（按用户选定日期范围）
    history = {}
    for code in stocks:
        rows = query_price_history(code, start_date=start_date, end_date=end_date)
        history[code] = [{"date": r["trade_date"], "close": r["close"]} for r in rows]

    return jsonify({
        "results":  results,
        "history":  history,
        "a_stocks": a_stocks,
        "h_stocks": h_stocks,
        "errors":   errors,
    })


if __name__ == "__main__":
    init_tables()
    print("=" * 50)
    print("  AH 股 DCF 估值系统 Web 服务已启动")
    print("  请在浏览器访问：http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000)
