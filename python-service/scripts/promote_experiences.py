#!/usr/bin/env python3
"""决策卡提升脚本 — 将已完成复盘（review_outcome 非空）的决策卡提升进 Chroma 经验库。

核心逻辑已抽到 services/experience_loop_service.py（供运行时自动化复用），
本脚本仅保留 CLI 入口与统计输出，独立运行与运行时调用共用同一实现。

复盘写侧闭环的最后一步：把 HIT（精选先例）与 MISS（反例）一并写入经验库。
检索侧通过 ``outcome.verdict`` 计算 ``validation_weight``，对 MISS 反例自动降权。
条目 id 为 ``dc_{decision_card_id}``，重复执行时 Chroma upsert 覆盖，天然幂等。

Usage::

    # 提升全部已复盘决策卡
    python scripts/promote_experiences.py

    # 仅提升前 20 条（按 id 升序）
    python scripts/promote_experiences.py --limit 20
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# 保证包根目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.experience_loop_service import promote_pending_experiences

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_promote(limit: int = 0) -> tuple[int, int, int]:
    """执行提升：委托 experience_loop_service，返回 (HIT 数, MISS 数, 总提升数)。"""
    hit_count, miss_count = promote_pending_experiences(limit=limit)
    total = hit_count + miss_count
    logger.info("提升完成：HIT %d 条 / MISS %d 条 / 总 %d 条", hit_count, miss_count, total)
    return hit_count, miss_count, total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="决策卡提升：将已复盘决策写入经验库（精选先例含反例）"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="最多提升的决策卡条数（0 = 不限制）",
    )
    args = parser.parse_args()

    logger.info("开始提升：limit=%s", args.limit or "unlimited")
    hit, miss, total = run_promote(limit=args.limit)
    logger.info("结束。共提升 HIT %d 条、MISS %d 条、总 %d 条", hit, miss, total)


if __name__ == "__main__":
    main()
