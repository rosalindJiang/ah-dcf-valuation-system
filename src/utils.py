"""
src/utils.py

通用工具函数：日志初始化、日期处理、格式化输出等。
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


def setup_logging(level: str = None) -> None:
    """
    初始化全局日志配置。
    建议在每个脚本入口处调用一次。

    Args:
        level: 日志级别字符串（DEBUG / INFO / WARNING / ERROR），
               默认读取 settings.LOG_LEVEL。
    """
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format=settings.LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def validate_date_range(start_date: str, end_date: str) -> None:
    """
    校验日期范围合法性（YYYY-MM-DD 格式，start <= end）。

    Args:
        start_date: 起始日期字符串。
        end_date:   结束日期字符串。

    Raises:
        ValueError: 格式错误或 start > end。
    """
    from datetime import datetime
    fmt = "%Y-%m-%d"
    try:
        start = datetime.strptime(start_date, fmt)
        end   = datetime.strptime(end_date, fmt)
    except ValueError as e:
        raise ValueError(f"日期格式错误（应为 YYYY-MM-DD）：{e}") from e

    if start > end:
        raise ValueError(f"起始日期 {start_date} 不能晚于结束日期 {end_date}")


def format_pct(value: float, decimals: int = 2) -> str:
    """
    将小数格式化为百分比字符串，正数前加 + 号。

    Args:
        value:    小数值，如 0.12 表示 12%。
        decimals: 小数位数。

    Returns:
        格式化字符串，如 "+12.00%" 或 "-5.50%"。
    """
    return f"{value * 100:+.{decimals}f}%"
