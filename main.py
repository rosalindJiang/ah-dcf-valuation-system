"""
main.py

一键运行入口：依次执行数据库初始化、数据下载、DCF 估值、可视化报告四个步骤。

运行方式：
    python main.py

输出：
  - data/ah_dcf.db       估值数据库
  - data/dcf_report.html 可视化报告（用浏览器打开）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils import setup_logging, validate_date_range
from src.database import init_tables
from src.data_downloader import download_a_share_data, download_hk_stock_data
from src.valuation_pipeline import run_pipeline
from src.visualizer import generate_report
from config import settings

import logging

setup_logging()
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 50)
    logger.info("AH 股 DCF 估值系统启动")
    logger.info("=" * 50)

    # Step 1: 初始化数据库
    logger.info("步骤 1/4：初始化数据库")
    init_tables()

    # Step 2: 下载行情数据
    validate_date_range(settings.START_DATE, settings.END_DATE)

    logger.info("步骤 2/4：下载 A 股数据（AkShare）")
    try:
        download_a_share_data()
    except Exception as e:
        logger.error("A 股下载失败：%s", e)

    logger.info("步骤 2/4：下载 H 股数据（AkShare）（续）")
    try:
        download_hk_stock_data()
    except Exception as e:
        logger.error("H 股下载失败：%s", e)

    # Step 3: DCF 估值
    logger.info("步骤 3/4：运行 DCF 估值 Pipeline")
    run_pipeline()

    # Step 4: 生成可视化报告
    logger.info("步骤 4/4：生成可视化 HTML 报告")
    try:
        report_path = generate_report()
        if report_path:
            logger.info("报告已生成，请用浏览器打开：%s", report_path)
    except Exception as e:
        logger.error("报告生成失败：%s", e)

    logger.info("=" * 50)
    logger.info("全部完成。")
    logger.info("  数据库：%s", settings.DB_PATH)
    logger.info("  报告：  %s", os.path.join(os.path.dirname(settings.DB_PATH), "dcf_report.html"))
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
