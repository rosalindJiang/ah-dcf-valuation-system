"""
src/data_downloader.py

数据采集模块。
- A 股和 H 股均通过 AkShare 下载真实行情数据，统一接口、无需注册账号。
- A 股接口：ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)
- H 股接口：ak.stock_hk_hist(symbol, period, start_date, end_date, adjust)
"""

import logging
from typing import List, Optional

import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from src import database

logger = logging.getLogger(__name__)

# AkShare 返回的列名 → 统一内部字段名（A 股和 H 股列名相同，共用同一映射）
_AKSHARE_COL_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}


# ──────────────────────────────────────────────
# 日期格式转换（settings 用 YYYY-MM-DD，AkShare 用 YYYYMMDD）
# ──────────────────────────────────────────────

def _to_akshare_date(date_str: str) -> str:
    """将 '2023-01-01' 转为 AkShare 所需的 '20230101'。"""
    return date_str.replace("-", "")


# ──────────────────────────────────────────────
# A 股下载（AkShare）
# ──────────────────────────────────────────────

def download_a_share_data(
    stock_list: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None,
) -> None:
    """
    通过 AkShare 下载 A 股日线行情并写入数据库。

    Args:
        stock_list: 6位纯数字 A 股代码列表，默认使用 settings.A_SHARE_STOCKS。
        start_date: 起始日期（YYYY-MM-DD），默认使用 settings.START_DATE。
        end_date:   结束日期（YYYY-MM-DD），默认使用 settings.END_DATE。
        db_path:    SQLite 数据库路径，默认使用 settings.DB_PATH。
    """
    try:
        import akshare as ak
    except ImportError:
        logger.error("未安装 akshare，请执行：pip install akshare")
        raise

    stocks = stock_list or settings.A_SHARE_STOCKS
    start  = _to_akshare_date(start_date or settings.START_DATE)
    end    = _to_akshare_date(end_date   or settings.END_DATE)

    logger.info("开始下载 A 股数据（AkShare），共 %d 只，日期范围：%s ~ %s",
                len(stocks), start, end)

    for code in stocks:
        _download_single_a_share(ak, code, start, end, db_path)

    logger.info("A 股数据下载完成。")


def _download_single_a_share(
    ak,
    stock_code: str,
    start_date: str,
    end_date: str,
    db_path: Optional[str],
) -> None:
    """
    下载单只 A 股日线数据并写入数据库。

    Args:
        ak:         已导入的 akshare 模块。
        stock_code: 6位纯数字代码（如 '600519'）。
        start_date: AkShare 格式起始日期（'20230101'）。
        end_date:   AkShare 格式结束日期（'20241231'）。
        db_path:    数据库路径。
    """
    logger.info("下载 A 股 %s ...", stock_code)
    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="",       # 不复权；可改为 "qfq"（前复权）或 "hfq"（后复权）
        )

        if df is None or df.empty:
            logger.warning("  %s：未获取到数据（可能代码错误或停牌）", stock_code)
            return

        records = _parse_akshare_df(df, stock_code, _AKSHARE_COL_MAP, source="akshare_a")
        if records:
            database.upsert_stock_prices(records, db_path)
            logger.info("  %s：写入 %d 条记录", stock_code, len(records))

    except Exception as e:
        logger.error("下载 A 股 %s 时发生异常：%s", stock_code, e)


# ──────────────────────────────────────────────
# H 股下载（AkShare）
# ──────────────────────────────────────────────

def download_hk_stock_data(
    stock_list: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None,
) -> None:
    """
    通过 AkShare 下载 H 股日线行情并写入数据库。

    Args:
        stock_list: 5位纯数字港股代码列表，默认使用 settings.H_SHARE_STOCKS。
        start_date: 起始日期（YYYY-MM-DD），默认使用 settings.START_DATE。
        end_date:   结束日期（YYYY-MM-DD），默认使用 settings.END_DATE。
        db_path:    SQLite 数据库路径，默认使用 settings.DB_PATH。
    """
    try:
        import akshare as ak
    except ImportError:
        logger.error("未安装 akshare，请执行：pip install akshare")
        raise

    stocks = stock_list or settings.H_SHARE_STOCKS
    start  = _to_akshare_date(start_date or settings.START_DATE)
    end    = _to_akshare_date(end_date   or settings.END_DATE)

    logger.info("开始下载 H 股数据（AkShare），共 %d 只，日期范围：%s ~ %s",
                len(stocks), start, end)

    for code in stocks:
        _download_single_hk_share(ak, code, start, end, db_path)

    logger.info("H 股数据下载完成。")


def _download_single_hk_share(
    ak,
    stock_code: str,
    start_date: str,
    end_date: str,
    db_path: Optional[str],
) -> None:
    """
    下载单只 H 股日线数据并写入数据库。

    Args:
        ak:         已导入的 akshare 模块。
        stock_code: 5位纯数字港股代码（如 '00700'）。
        start_date: AkShare 格式起始日期。
        end_date:   AkShare 格式结束日期。
        db_path:    数据库路径。
    """
    logger.info("下载 H 股 %s ...", stock_code)
    try:
        df = ak.stock_hk_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="",
        )

        if df is None or df.empty:
            logger.warning("  %s：未获取到数据（可能代码错误或停牌）", stock_code)
            return

        records = _parse_akshare_df(df, stock_code, _AKSHARE_COL_MAP, source="akshare_hk")
        if records:
            database.upsert_stock_prices(records, db_path)
            logger.info("  %s：写入 %d 条记录", stock_code, len(records))

    except Exception as e:
        logger.error("下载 H 股 %s 时发生异常：%s", stock_code, e)


# ──────────────────────────────────────────────
# 公共解析函数
# ──────────────────────────────────────────────

def _parse_akshare_df(
    df: "pd.DataFrame",
    stock_code: str,
    col_map: dict,
    source: str,
) -> list:
    """
    将 AkShare 返回的 DataFrame 转换为数据库写入格式的字典列表。

    Args:
        df:         AkShare 返回的 DataFrame。
        stock_code: 股票代码（写入 stock_code 字段）。
        col_map:    AkShare 列名到内部字段名的映射。
        source:     数据来源标记（写入 source 字段）。

    Returns:
        可直接传入 database.upsert_stock_prices() 的字典列表。
    """
    df = df.rename(columns=col_map)

    required = ["trade_date", "open", "high", "low", "close", "volume", "amount"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        logger.warning("  %s：DataFrame 缺少字段 %s，跳过", stock_code, missing)
        return []

    df = df[required].copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df["stock_code"] = stock_code
    df["source"]     = source

    # 过滤收盘价为空或零的行
    df = df[df["close"].notna() & (df["close"] != 0)]

    return df.to_dict(orient="records")
