#!/usr/bin/env python3
"""决策复盘引擎 — 对已落库的 BUY/SELL 决策验证"判断方向是否兑现"，并回填 review_outcome。

核心逻辑已抽到 services/experience_loop_service.py（供运行时自动化复用），
本脚本仅保留 CLI 入口与统计输出，独立运行与运行时调用共用同一实现。

对 decision_cards 表中 review_outcome 为空、action 为 BUY/SELL 且已记录
current_price 的决策卡，取决策日之后的 10 根日线 K 线，计算区间涨跌幅与
最高/最低幅度，判定 verdict（HIT/MISS）并回填 review_outcome JSON。

Usage::

    # 复盘全部待处理决策
    python scripts/review_decisions.py

    # 仅处理前 20 条待复盘决策
    python scripts/review_decisions.py --limit 20
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 保证包根目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.experience_loop_service import review_pending_decisions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_review(limit: int = 0) -> int:
    """执行复盘：委托 experience_loop_service，返回本次成功回填 review_outcome 的条数。

    服务内部已处理：取决策日后 10 根已收盘日线，不足 10 根的跳过且不标记；
    已复盘（review_outcome 非空）的决策卡天然幂等跳过。
    """
    return review_pending_decisions(limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="决策复盘引擎：验证 BUY/SELL 判断方向是否兑现")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="最多处理的待复盘决策条数（0 = 不限制）",
    )
    args = parser.parse_args()

    logger.info("开始复盘：limit=%s", args.limit or "unlimited")
    reviewed = run_review(limit=args.limit)
    logger.info("复盘完成：共回填 %d 条（数据不足 10 根的自动跳过、不标记）", reviewed)


if __name__ == "__main__":
    main()
