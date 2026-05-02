"""
src/data_downloader.py

数据采集模块。
- A 股和 H 股均通过 AkShare 下载真实行情数据，统一接口、无需注册账号。
- A 股接口：ak.stock_zh_a_daily(symbol, start_date, end_date, adjust)
- H 股接口：ak.stock_hk_daily(symbol, start_date, end_date, adjust)
"""

import logging
import os
import sys
from typing import List, Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from src import database

logger = logging.getLogger(__name__)


def _a_share_to_daily_symbol(stock_code: str) -> str:
    """
    将 A 股代码转换为 stock_zh_a_daily 需要的格式。

    600519 -> sh600519
    000001 -> sz000001
    300750 -> sz300750
    """
    code = str(stock_code).zfill(6)

    if code.startswith(("6", "9")):
        return "sh" + code
    elif code.startswith(("0", "2", "3")):
        return "sz" + code
    else:
        raise ValueError(f"无法识别 A 股代码：{stock_code}")


def _hk_to_daily_symbol(stock_code: str) -> str:
    """
    将 H 股代码转换为 stock_hk_daily 需要的格式。

    700 -> 00700
    00700 -> 00700
    2318 -> 02318
    """
    return str(stock_code).zfill(5)


def _normalize_date(date_str: str) -> str:
    """
    转成 YYYY-MM-DD，用于筛选 DataFrame。
    """
    return pd.to_datetime(date_str).strftime("%Y-%m-%d")


def _parse_daily_df(
    df: pd.DataFrame,
    stock_code: str,
    source: str,
    start_date: str,
    end_date: str,
) -> list:
    """
    将 stock_zh_a_daily / stock_hk_daily 返回的数据转换为数据库写入格式。

    daily 接口字段通常是：
    date, open, high, low, close, volume, amount
    """
    if df is None or df.empty:
        return []

    df = df.copy()

    required_cols = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.warning("%s：AkShare daily 数据缺少字段 %s", stock_code, missing)
        logger.warning("%s：实际字段为 %s", stock_code, list(df.columns))
        return []

    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    start = _normalize_date(start_date)
    end = _normalize_date(end_date)

    df = df[(df["date"] >= start) & (df["date"] <= end)].copy()

    if df.empty:
        logger.warning("%s：日期范围 %s ~ %s 内无行情数据", stock_code, start, end)
        return []

    out = pd.DataFrame()
    out["trade_date"] = df["date"]
    out["open"] = pd.to_numeric(df["open"], errors="coerce")
    out["high"] = pd.to_numeric(df["high"], errors="coerce")
    out["low"] = pd.to_numeric(df["low"], errors="coerce")
    out["close"] = pd.to_numeric(df["close"], errors="coerce")
    out["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    out["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    out["stock_code"] = str(stock_code).zfill(5) if source == "akshare_hk_daily" else str(stock_code).zfill(6)
    out["source"] = source

    out = out.dropna(subset=["trade_date", "close"])
    out = out[out["close"] > 0]

    return out.to_dict(orient="records")


def _write_records(records: list, stock_code: str, db_path: Optional[str]) -> None:
    """
    写入数据库。
    """
    if not records:
        logger.warning("%s：没有可写入的价格数据", stock_code)
        return

    database.upsert_stock_prices(records, db_path)
    logger.info("%s：成功写入 %d 条价格记录", stock_code, len(records))


# =========================================================
# A 股下载
# =========================================================

def download_a_share_data(
    stock_list: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None,
) -> None:
    """
    使用 AkShare stock_zh_a_daily 下载 A 股日线数据。
    """
    import akshare as ak

    stocks = stock_list or settings.A_SHARE_STOCKS
    start = start_date or settings.START_DATE
    end = end_date or settings.END_DATE

    logger.info(
        "开始下载 A 股数据（AkShare stock_zh_a_daily），共 %d 只，日期范围：%s ~ %s",
        len(stocks),
        start,
        end,
    )

    for stock_code in stocks:
        try:
            _download_single_a_share(
                ak=ak,
                stock_code=stock_code,
                start_date=start,
                end_date=end,
                db_path=db_path,
            )
        except Exception as exc:
            logger.error("下载 A 股 %s 时发生异常：%s", stock_code, exc)

    logger.info("A 股数据下载完成。")


def _download_single_a_share(
    ak,
    stock_code: str,
    start_date: str,
    end_date: str,
    db_path: Optional[str],
) -> None:
    """
    下载单只 A 股。
    """
    symbol = _a_share_to_daily_symbol(stock_code)

    logger.info("下载 A 股 %s，AkShare symbol=%s ...", stock_code, symbol)

    df = ak.stock_zh_a_daily(
        symbol=symbol,
        start_date=pd.to_datetime(start_date).strftime("%Y%m%d"),
        end_date=pd.to_datetime(end_date).strftime("%Y%m%d"),
        adjust="",
    )

    records = _parse_daily_df(
        df=df,
        stock_code=stock_code,
        source="akshare_a_daily",
        start_date=start_date,
        end_date=end_date,
    )

    _write_records(records, stock_code, db_path)


# =========================================================
# H 股下载
# =========================================================

def download_hk_stock_data(
    stock_list: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    db_path: str = None,
) -> None:
    """
    使用 AkShare stock_hk_daily 下载 H 股日线数据。
    """
    import akshare as ak

    stocks = stock_list or settings.H_SHARE_STOCKS
    start = start_date or settings.START_DATE
    end = end_date or settings.END_DATE

    logger.info(
        "开始下载 H 股数据（AkShare stock_hk_daily），共 %d 只，日期范围：%s ~ %s",
        len(stocks),
        start,
        end,
    )

    for stock_code in stocks:
        try:
            _download_single_hk_share(
                ak=ak,
                stock_code=stock_code,
                start_date=start,
                end_date=end,
                db_path=db_path,
            )
        except Exception as exc:
            logger.error("下载 H 股 %s 时发生异常：%s", stock_code, exc)

    logger.info("H 股数据下载完成。")


def _download_single_hk_share(
    ak,
    stock_code: str,
    start_date: str,
    end_date: str,
    db_path: Optional[str],
) -> None:
    """
    下载单只 H 股。
    """
    symbol = _hk_to_daily_symbol(stock_code)

    logger.info("下载 H 股 %s，AkShare symbol=%s ...", stock_code, symbol)

    df = ak.stock_hk_daily(
        symbol=symbol,
        adjust="",
    )

    records = _parse_daily_df(
        df=df,
        stock_code=stock_code,
        source="akshare_hk_daily",
        start_date=start_date,
        end_date=end_date,
    )

    _write_records(records, stock_code, db_path)
