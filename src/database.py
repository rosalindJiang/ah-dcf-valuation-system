"""
src/database.py

SQLite 数据库管理模块。
负责：建库建表、数据写入、数据查询。
所有 SQL 操作集中在此模块，业务层通过调用此模块与数据库交互。
"""

import sqlite3
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 连接管理
# ──────────────────────────────────────────────

def get_connection(db_path: str = None) -> sqlite3.Connection:
    """
    创建并返回 SQLite 数据库连接。

    Args:
        db_path: 数据库文件路径，默认读取 settings.DB_PATH。

    Returns:
        sqlite3.Connection 对象，开启 WAL 模式以支持并发读写。
    """
    path = db_path or settings.DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row          # 查询结果支持列名访问
    conn.execute("PRAGMA journal_mode=WAL")  # 写前日志，提升并发性能
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ──────────────────────────────────────────────
# 建表 DDL
# ──────────────────────────────────────────────

_DDL_STOCK_PRICES = """
CREATE TABLE IF NOT EXISTS stock_prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code  TEXT    NOT NULL,
    trade_date  TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    amount      REAL,
    source      TEXT,
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    UNIQUE (stock_code, trade_date)
)
"""

_DDL_FINANCIAL_ASSUMPTIONS = """
CREATE TABLE IF NOT EXISTS financial_assumptions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code           TEXT    NOT NULL,
    assumption_date      TEXT    NOT NULL,
    wacc                 REAL,
    terminal_growth_rate REAL,
    revenue_growth_rate  REAL,
    operating_margin     REAL,
    tax_rate             REAL,
    depreciation_ratio   REAL,
    capex_ratio          REAL,
    working_capital_ratio REAL,
    source               TEXT    DEFAULT 'manual',
    created_at           TEXT    DEFAULT (datetime('now', 'localtime')),
    UNIQUE (stock_code, assumption_date)
)
"""

_DDL_DCF_VALUATION_RESULTS = """
CREATE TABLE IF NOT EXISTS dcf_valuation_results (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code              TEXT    NOT NULL,
    valuation_date          TEXT    NOT NULL,
    start_date              TEXT,
    forecast_years          INTEGER,
    wacc                    REAL,
    terminal_growth_rate    REAL,
    estimated_intrinsic_value REAL,
    latest_market_price     REAL,
    upside_downside_pct     REAL,
    assumptions_json        TEXT,
    created_at              TEXT    DEFAULT (datetime('now', 'localtime')),
    UNIQUE (stock_code, valuation_date)
)
"""


def init_tables(db_path: str = None) -> None:
    """
    初始化数据库，创建所有业务表。
    若表已存在则跳过，安全幂等。

    Args:
        db_path: 数据库路径，默认使用 settings.DB_PATH。
    """
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(_DDL_STOCK_PRICES)
            conn.execute(_DDL_FINANCIAL_ASSUMPTIONS)
            conn.execute(_DDL_DCF_VALUATION_RESULTS)
        logger.info("数据库表初始化完成：stock_prices, financial_assumptions, dcf_valuation_results")
        # 迁移：为已存在的旧表添加 start_date 列（幂等，列已存在时静默忽略）
        try:
            conn.execute("ALTER TABLE dcf_valuation_results ADD COLUMN start_date TEXT")
        except Exception:
            pass
    finally:
        conn.close()


# ──────────────────────────────────────────────
# 写入操作
# ──────────────────────────────────────────────

def upsert_stock_prices(records: List[Dict[str, Any]], db_path: str = None) -> int:
    """
    批量写入（或更新）股票日线价格数据。
    使用 INSERT OR REPLACE 实现幂等写入，重复运行不产生重复记录。

    Args:
        records: 字典列表，每条包含 stock_code, trade_date, open, high, low,
                 close, volume, amount, source 字段。
        db_path: 数据库路径。

    Returns:
        成功写入的记录数。
    """
    if not records:
        return 0

    sql = """
        INSERT OR REPLACE INTO stock_prices
            (stock_code, trade_date, open, high, low, close, volume, amount, source)
        VALUES
            (:stock_code, :trade_date, :open, :high, :low, :close, :volume, :amount, :source)
    """
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executemany(sql, records)
        logger.info("写入 stock_prices：%d 条", len(records))
        return len(records)
    except sqlite3.Error as e:
        logger.error("写入 stock_prices 失败：%s", e)
        raise
    finally:
        conn.close()


def upsert_dcf_result(result: Dict[str, Any], db_path: str = None) -> None:
    """
    写入（或更新）单只股票的 DCF 估值结果。

    Args:
        result: 包含 DCF 估值字段的字典：
                stock_code, valuation_date, forecast_years, wacc,
                terminal_growth_rate, estimated_intrinsic_value,
                latest_market_price, upside_downside_pct, assumptions_json。
        db_path: 数据库路径。
    """
    sql = """
        INSERT OR REPLACE INTO dcf_valuation_results
            (stock_code, valuation_date, start_date, forecast_years, wacc,
             terminal_growth_rate, estimated_intrinsic_value,
             latest_market_price, upside_downside_pct, assumptions_json)
        VALUES
            (:stock_code, :valuation_date, :start_date, :forecast_years, :wacc,
             :terminal_growth_rate, :estimated_intrinsic_value,
             :latest_market_price, :upside_downside_pct, :assumptions_json)
    """
    conn = get_connection(db_path)
    try:
        # Ensure start_date key exists (result dict may not have it)
        row = dict(result)
        row.setdefault("start_date", "")
        with conn:
            conn.execute(sql, row)
        logger.info("写入 DCF 估值结果：%s @ %s", result["stock_code"], result["valuation_date"])
    except sqlite3.Error as e:
        logger.error("写入 DCF 结果失败（%s）：%s", result.get("stock_code"), e)
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# 查询操作
# ──────────────────────────────────────────────

def query_latest_close(stock_code: str, db_path: str = None) -> Optional[Dict[str, Any]]:
    """
    查询指定股票最新一条收盘价记录。

    Args:
        stock_code: 股票代码（baostock 格式或 HK 格式）。
        db_path: 数据库路径。

    Returns:
        包含 trade_date 和 close 的字典，若无数据则返回 None。
    """
    sql = """
        SELECT stock_code, trade_date, close
        FROM stock_prices
        WHERE stock_code = ?
        ORDER BY trade_date DESC
        LIMIT 1
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(sql, (stock_code,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def query_price_history(
    stock_code: str,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None,
) -> List[Dict[str, Any]]:
    """
    查询指定股票的历史价格序列。

    Args:
        stock_code: 股票代码。
        start_date: 起始日期字符串（YYYY-MM-DD），可选。
        end_date:   结束日期字符串（YYYY-MM-DD），可选。
        db_path:    数据库路径。

    Returns:
        按日期升序排列的价格记录列表。
    """
    conditions = ["stock_code = ?"]
    params: List[Any] = [stock_code]

    if start_date:
        conditions.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("trade_date <= ?")
        params.append(end_date)

    sql = f"""
        SELECT stock_code, trade_date, open, high, low, close, volume, amount, source
        FROM stock_prices
        WHERE {' AND '.join(conditions)}
        ORDER BY trade_date ASC
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_all_dcf_results(db_path: str = None) -> List[Dict[str, Any]]:
    """
    查询每只股票最新一次的 DCF 估值结果，按 upside_downside_pct 降序排列。

    每只股票只保留 valuation_date 最大的那条记录，避免历史运行数据混入图表。

    Args:
        db_path: 数据库路径。

    Returns:
        每只股票最新 DCF 估值结果列表。
    """
    sql = """
        SELECT r.stock_code, r.valuation_date, r.forecast_years, r.wacc,
               r.terminal_growth_rate, r.estimated_intrinsic_value,
               r.latest_market_price, r.upside_downside_pct
        FROM dcf_valuation_results r
        INNER JOIN (
            SELECT stock_code, MAX(valuation_date) AS max_date
            FROM dcf_valuation_results
            GROUP BY stock_code
        ) latest ON r.stock_code = latest.stock_code
                AND r.valuation_date = latest.max_date
        ORDER BY r.upside_downside_pct DESC
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
