"""
scripts/run_report.py

生成 DCF 估值可视化 HTML 报告。

运行方式：
    python scripts/run_report.py

前置条件：
  - 已执行 python scripts/run_valuation.py（数据库中有估值结果）

输出：
  - data/dcf_report.html（双击用浏览器打开）
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import setup_logging
from src.visualizer import generate_report

setup_logging()
logger = logging.getLogger(__name__)


def main():
    logger.info("开始生成 DCF 估值可视化报告...")
    path = generate_report()
    if path:
        logger.info("报告已生成：%s", path)
        logger.info("请用浏览器打开该文件查看完整报告。")
    else:
        logger.error("报告生成失败，请确认数据库中有估值结果。")


if __name__ == "__main__":
    main()
