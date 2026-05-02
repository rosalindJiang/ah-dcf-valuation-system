"""
scripts/run_valuation.py

运行 DCF 估值 Pipeline，输出估值结果并存入数据库。

运行方式：
    python scripts/run_valuation.py

前置条件：
  - 已执行 python scripts/init_db.py
  - 已执行 python scripts/run_download.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import setup_logging
from src.valuation_pipeline import run_pipeline

setup_logging()
logger = logging.getLogger(__name__)


def main():
    logger.info("启动 DCF 估值 Pipeline...")
    run_pipeline()
    logger.info("估值 Pipeline 执行完毕，结果已写入数据库。")


if __name__ == "__main__":
    main()
