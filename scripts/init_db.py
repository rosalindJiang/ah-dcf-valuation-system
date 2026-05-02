"""
scripts/init_db.py

初始化 SQLite 数据库，创建所有业务表。
幂等操作：重复执行不会破坏已有数据。

运行方式：
    python scripts/init_db.py
"""

import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import setup_logging
from src.database import init_tables
from config import settings

import logging

setup_logging()
logger = logging.getLogger(__name__)


def main():
    logger.info("初始化数据库：%s", settings.DB_PATH)
    init_tables()
    logger.info("数据库初始化完成，可运行 scripts/run_download.py 下载数据。")


if __name__ == "__main__":
    main()
