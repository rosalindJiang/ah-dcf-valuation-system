"""
src/valuation_pipeline.py

估值流程调度模块（Pipeline）。
协调各模块完成：读取股票池 → 查询最新价格 → 调用 DCF 模型 → 写入结果 → 打印汇总。
"""

import logging
from typing import List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from src import database
from src.dcf_model import DCFModel, DCFAssumptions

logger = logging.getLogger(__name__)


def run_pipeline(
    stock_list: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    执行全量估值 Pipeline。

    步骤：
        1. 合并 A 股和 H 股股票池（支持自定义覆盖）
        2. 从数据库读取每只股票最新收盘价
        3. 实例化 DCFModel 并运行估值
        4. 将估值结果写入 dcf_valuation_results 表
        5. 打印结果汇总表格

    Args:
        stock_list: 自定义股票列表，None 时使用 settings 中的全量列表。
        db_path:    数据库路径，None 时使用 settings.DB_PATH。
    """
    all_stocks = stock_list or (settings.A_SHARE_STOCKS + settings.H_SHARE_STOCKS)
    logger.info("Pipeline 启动，待估值股票 %d 只", len(all_stocks))

    results     = []
    skipped     = []

    for code in all_stocks:
        try:
            result = _valuate_single(code, db_path)
            if result:
                results.append(result)
            else:
                skipped.append(code)
        except Exception as e:
            logger.error("估值 %s 时发生未预期错误：%s", code, e)
            skipped.append(code)

    _print_summary(results, skipped)


def _valuate_single(stock_code: str, db_path: Optional[str]) -> Optional[dict]:
    """
    对单只股票执行估值并持久化结果。

    Args:
        stock_code: 股票代码。
        db_path:    数据库路径。

    Returns:
        估值结果字典，若无价格数据则返回 None。
    """
    # 查询最新收盘价
    price_row = database.query_latest_close(stock_code, db_path)
    if not price_row:
        logger.warning("%s：数据库中无价格数据，跳过估值", stock_code)
        return None

    market_price = price_row["close"]
    if not market_price or market_price <= 0:
        logger.warning("%s：收盘价无效（%.4f），跳过估值", stock_code, market_price or 0)
        return None

    # 读取个股财务基础数据，覆盖全局默认参数
    fin = settings.STOCK_FINANCIALS.get(stock_code, {})
    assumptions = DCFAssumptions(
        wacc=fin.get("wacc", settings.DEFAULT_WACC),
        revenue_growth_rate=fin.get("revenue_growth_rate", settings.REVENUE_GROWTH_RATE),
    )
    base_revenue = fin.get("revenue")       # None 时 DCFModel 回退到虚拟代理值
    total_shares = fin.get("shares")        # None 时 DCFModel 回退到虚拟代理值

    # 运行 DCF 估值
    model  = DCFModel(stock_code, market_price, assumptions, base_revenue, total_shares)
    result = model.run_valuation()

    # 写入数据库
    database.upsert_dcf_result(result, db_path)

    return result


def _print_summary(results: list, skipped: list) -> None:
    """
    打印估值结果汇总表格到控制台。

    Args:
        results: 成功完成估值的结果列表。
        skipped: 因数据缺失而跳过的股票代码列表。
    """
    print("\n" + "=" * 80)
    print(f"{'DCF 估值结果汇总':^76}")
    print("=" * 80)

    if results:
        header = f"{'股票代码':<14} {'市场价':>10} {'内在价值':>10} {'高低估(%)':>12} {'估值日期':>12}"
        print(header)
        print("-" * 80)

        # 按高低估比例降序排列
        for r in sorted(results, key=lambda x: x["upside_downside_pct"], reverse=True):
            flag = "▲低估" if r["upside_downside_pct"] > 0 else "▼高估"
            print(
                f"{r['stock_code']:<14} "
                f"{r['latest_market_price']:>10.2f} "
                f"{r['estimated_intrinsic_value']:>10.2f} "
                f"{r['upside_downside_pct']:>+10.1f}%  "
                f"{r['valuation_date']:>12}  {flag}"
            )
    else:
        print("  （无估值结果，请先运行数据下载）")

    if skipped:
        print(f"\n  跳过（无数据）：{', '.join(skipped)}")

    print("=" * 80)
    print(f"  完成 {len(results)} 只，跳过 {len(skipped)} 只")
    print("  注意：当前为 demo 简化 DCF，估值仅供参考，不构成投资建议。")
    print("=" * 80 + "\n")
