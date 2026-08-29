#!/usr/bin/env python3
"""热门行业数据批量初始化脚本。

按总市值取前 N 个东财行业板块，拉取成分股写入 stock_industry 表
（industry_l1=板块名, industry_l2=粗分类），限流自动控制，支持断点续传。

用法:
    cd python-service
    .venv/bin/python scripts/init_hot_industry.py            # 默认 TOP 30
    .venv/bin/python scripts/init_hot_industry.py --top-n 50
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from services.industry_service import sync_hot_industries


def main() -> None:
    parser = argparse.ArgumentParser(description="热门行业数据批量初始化")
    parser.add_argument("--top-n", type=int, default=30, help="东财模式热门板块数量（按总市值），默认 30")
    parser.add_argument(
        "--source", choices=["auto", "em", "sina"], default="auto",
        help="数据源：auto 东财优先回退新浪（默认）/ em 仅东财 / sina 仅新浪",
    )
    args = parser.parse_args()

    logger.info("开始初始化热门行业数据：TOP %d，数据源 %s", args.top_n, args.source)
    result = sync_hot_industries(top_n=args.top_n, source=args.source)

    if "error" in result:
        logger.error("初始化失败: %s", result["error"])
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("初始化结果（%s）：", result.get("source", "?"))
    logger.info("  板块总数: %d", result["total_boards"])
    logger.info("  已初始化: %d", result["initialized_boards"])
    logger.info("  股票总数: %d", result["total_symbols"])
    if result["errors"]:
        logger.warning("  错误 %d 个:", len(result["errors"]))
        for e in result["errors"][:10]:
            logger.warning("    %s", e)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
