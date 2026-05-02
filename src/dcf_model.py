"""
src/dcf_model.py

DCF（Discounted Cash Flow）估值模型。

当前版本为 demo 简化 DCF：
  - 使用数据库中最新收盘价作为市场价格
  - 基于 settings.py 中的假设参数生成未来自由现金流
  - 使用 WACC 对现金流折现
  - 用 Gordon Growth Model 计算终值（Terminal Value）
  - 输出内在价值估计和相对市场价格的高低估比例

生产环境升级方向：
  - 接入完整财务报表（收入、EBIT、D&A、CapEx、营运资本变动）
  - 按行业/公司单独设置 Beta、资本结构、行业基准增长率
  - 支持蒙特卡洛模拟进行敏感性分析
  - 多情景（悲观/基准/乐观）估值
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 假设参数数据类
# ──────────────────────────────────────────────

@dataclass
class DCFAssumptions:
    """
    封装单次 DCF 估值所需的全部假设参数。
    默认值来自 settings.py，可针对单只股票覆盖。
    """
    wacc:                  float = field(default_factory=lambda: settings.DEFAULT_WACC)
    terminal_growth_rate:  float = field(default_factory=lambda: settings.TERMINAL_GROWTH_RATE)
    forecast_years:        int   = field(default_factory=lambda: settings.FORECAST_YEARS)
    revenue_growth_rate:   float = field(default_factory=lambda: settings.REVENUE_GROWTH_RATE)
    operating_margin:      float = field(default_factory=lambda: settings.OPERATING_MARGIN)
    tax_rate:              float = field(default_factory=lambda: settings.TAX_RATE)
    depreciation_ratio:    float = field(default_factory=lambda: settings.DEPRECIATION_RATIO)
    capex_ratio:           float = field(default_factory=lambda: settings.CAPEX_RATIO)
    working_capital_ratio: float = field(default_factory=lambda: settings.WORKING_CAPITAL_RATIO)

    def to_json(self) -> str:
        """序列化为 JSON 字符串，用于存入数据库。"""
        return json.dumps(asdict(self), ensure_ascii=False)


# ──────────────────────────────────────────────
# DCF 模型类
# ──────────────────────────────────────────────

class DCFModel:
    """
    简化 DCF 估值模型。

    使用流程：
        1. 实例化 DCFModel(stock_code, market_price, assumptions)
        2. 调用 run_valuation() 获取完整估值结果字典

    内部计算步骤：
        Step 1 - forecast_free_cash_flow(): 预测各年 FCFF
        Step 2 - calculate_terminal_value(): 计算 Gordon Growth 终值
        Step 3 - discount_cash_flows():      折现现金流与终值
        Step 4 - calculate_intrinsic_value(): 汇总内在价值
    """

    def __init__(
        self,
        stock_code: str,
        market_price: float,
        assumptions: DCFAssumptions = None,
        base_revenue: float = None,
    ):
        """
        Args:
            stock_code:    股票代码，仅用于日志和结果标记。
            market_price:  最新市场收盘价（元 / 港元）。
            assumptions:   DCFAssumptions 实例，默认使用全局参数。
            base_revenue:  基准年营收（元）。
                           demo 中以 market_price * 1e8 作为代理（虚拟规模）；
                           生产环境应传入真实营收数据。
        """
        self.stock_code   = stock_code
        self.market_price = market_price
        self.assum        = assumptions or DCFAssumptions()

        # demo 代理基准营收：用市场价格 × 1亿 作为虚构规模基础
        # 实际使用时应替换为真实财报营收数据
        self.base_revenue = base_revenue or (market_price * 1e8)

        if self.assum.wacc <= self.assum.terminal_growth_rate:
            raise ValueError(
                f"WACC ({self.assum.wacc}) 必须大于终端增长率 ({self.assum.terminal_growth_rate})，"
                "否则 Gordon Growth 终值公式无意义。"
            )

    # ── Step 1 ────────────────────────────────

    def forecast_free_cash_flow(self) -> List[float]:
        """
        预测未来 N 年的自由现金流（FCFF，企业自由现金流）。

        FCFF = EBIT × (1 - 税率) + D&A - CapEx - 营运资本增量
             = NOPAT + D&A - CapEx - △WC

        其中各项均以当年营收为基数按比例估算。

        Returns:
            按年份顺序排列的 FCFF 列表（单位：元）。
        """
        fcff_list = []
        revenue = self.base_revenue

        for year in range(1, self.assum.forecast_years + 1):
            revenue *= (1 + self.assum.revenue_growth_rate)

            ebit    = revenue * self.assum.operating_margin
            nopat   = ebit * (1 - self.assum.tax_rate)         # 税后净营业利润
            da      = revenue * self.assum.depreciation_ratio  # 折旧与摊销（非现金，加回）
            capex   = revenue * self.assum.capex_ratio          # 资本开支（现金流出）
            delta_wc = revenue * self.assum.working_capital_ratio  # 营运资本增量（占用）

            fcff = nopat + da - capex - delta_wc
            fcff_list.append(fcff)
            logger.debug("  Year %d: Revenue=%.2fM, FCFF=%.2fM", year, revenue / 1e6, fcff / 1e6)

        return fcff_list

    # ── Step 2 ────────────────────────────────

    def calculate_terminal_value(self, final_year_fcff: float) -> float:
        """
        使用 Gordon Growth Model 计算终值。

        Terminal Value = FCFF_N × (1 + g) / (WACC - g)

        其中 g 为永续增长率（terminal_growth_rate）。

        Args:
            final_year_fcff: 预测最后一年的自由现金流。

        Returns:
            终值（未折现，单位：元）。
        """
        g    = self.assum.terminal_growth_rate
        wacc = self.assum.wacc
        tv   = final_year_fcff * (1 + g) / (wacc - g)
        logger.debug("Terminal Value（未折现）= %.2fM", tv / 1e6)
        return tv

    # ── Step 3 ────────────────────────────────

    def discount_cash_flows(
        self,
        fcff_list: List[float],
        terminal_value: float,
    ) -> float:
        """
        将所有现金流和终值折现至今天。

        PV = Σ [FCFF_t / (1+WACC)^t]  +  TV / (1+WACC)^N

        Args:
            fcff_list:      各年 FCFF 列表。
            terminal_value: 未折现终值。

        Returns:
            企业总价值（Enterprise Value，元）。
        """
        wacc = self.assum.wacc
        n    = self.assum.forecast_years

        pv_fcff = sum(
            cf / (1 + wacc) ** t
            for t, cf in enumerate(fcff_list, start=1)
        )
        pv_tv   = terminal_value / (1 + wacc) ** n
        ev      = pv_fcff + pv_tv

        logger.debug(
            "PV(FCFF)=%.2fM, PV(TV)=%.2fM, EV=%.2fM",
            pv_fcff / 1e6, pv_tv / 1e6, ev / 1e6,
        )
        return ev

    # ── Step 4 ────────────────────────────────

    def calculate_intrinsic_value(self, enterprise_value: float) -> float:
        """
        将企业价值（EV）转换为每股内在价值。

        demo 简化：假设虚拟股本为 1 亿股，EV 直接除以股本得到每股价值。
        生产环境：应接入真实股本数（total_shares）、净负债（net_debt）：
            equity_value    = EV - net_debt
            intrinsic_value = equity_value / total_shares

        Args:
            enterprise_value: 企业总价值（元）。

        Returns:
            每股内在价值（元 / 港元）。
        """
        # demo：虚拟股本 = base_revenue / 100（使结果与市场价在同一数量级）
        virtual_shares = self.base_revenue / 100
        intrinsic_value = enterprise_value / virtual_shares
        return round(intrinsic_value, 4)

    # ── 主入口 ────────────────────────────────

    def run_valuation(self) -> Dict[str, Any]:
        """
        执行完整 DCF 估值流程，返回结构化结果字典。

        Returns:
            包含以下字段的字典（与 dcf_valuation_results 表结构对应）：
                stock_code, valuation_date, forecast_years, wacc,
                terminal_growth_rate, estimated_intrinsic_value,
                latest_market_price, upside_downside_pct, assumptions_json
        """
        from datetime import date

        logger.info("开始估值：%s（市场价=%.2f）", self.stock_code, self.market_price)

        # Step 1: 预测现金流
        fcff_list = self.forecast_free_cash_flow()

        # Step 2: 终值
        tv = self.calculate_terminal_value(fcff_list[-1])

        # Step 3: 折现
        ev = self.discount_cash_flows(fcff_list, tv)

        # Step 4: 每股内在价值
        intrinsic = self.calculate_intrinsic_value(ev)

        # 高低估比例（正数=低估，负数=高估）
        upside_pct = round((intrinsic - self.market_price) / self.market_price * 100, 2)

        result = {
            "stock_code":               self.stock_code,
            "valuation_date":           date.today().isoformat(),
            "forecast_years":           self.assum.forecast_years,
            "wacc":                     self.assum.wacc,
            "terminal_growth_rate":     self.assum.terminal_growth_rate,
            "estimated_intrinsic_value": intrinsic,
            "latest_market_price":      self.market_price,
            "upside_downside_pct":      upside_pct,
            "assumptions_json":         self.assum.to_json(),
        }

        logger.info(
            "估值完成：%s | 内在价值=%.2f | 市场价=%.2f | 高低估=%.1f%%",
            self.stock_code, intrinsic, self.market_price, upside_pct,
        )
        return result
