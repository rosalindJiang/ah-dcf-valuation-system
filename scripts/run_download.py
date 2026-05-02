"""
scripts/run_download.py

通过 AkShare 下载 A 股和 H 股真实行情数据并存入 SQLite。

运行方式：
    python scripts/run_download.py

注意：
  - A 股和 H 股均通过 AkShare 下载，无需注册账号。
  - 如需修改股票池或日期，请编辑 config/settings.py。
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import setup_logging, validate_date_range
from src.data_downloader import download_a_share_data, download_hk_stock_data
from config import settings

setup_logging()
logger = logging.getLogger(__name__)


def main():
    validate_date_range(settings.START_DATE, settings.END_DATE)

    logger.info("─" * 50)
    logger.info("步骤 1/2：下载 A 股数据（AkShare）")
    logger.info("─" * 50)
    try:
        download_a_share_data()
    except Exception as e:
        logger.error("A 股下载失败：%s", e)
        logger.error("排查建议：1) 检查网络连通性  2) 确认 akshare 已安装  3) 检查股票代码格式")

    logger.info("─" * 50)
    logger.info("步骤 2/2：下载 H 股数据（AkShare）")
    logger.info("─" * 50)
    try:
        download_hk_stock_data()
    except Exception as e:
        logger.error("H 股下载失败：%s", e)
        logger.error("排查建议：1) 检查网络连通性  2) 确认 akshare 已安装  3) 检查港股代码格式（5位数字）")

    logger.info("数据下载流程结束，可运行 scripts/run_valuation.py 执行估值。")


if __name__ == "__main__":
    main()
