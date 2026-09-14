#!/usr/bin/env python3
"""同步上市日期到 stock_metadata.list_date（L2 审计基准）。

不加 list_date 会把"上市前的年份"误算成数据缺口（例如 600519 于 2001 年上市，
若按 2020 起回溯，实际要求的是全区间而非从 2001 起），审计会自我欺骗。

用法：
    cd python-service && ./.venv/bin/python scripts/sync_list_dates.py

说明：接口只返回在市标的，故本脚本仅写 list_date，不推断 delist_date。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from services import stock_metadata_service as sms


def main() -> int:
    stats = sms.sync_list_dates()
    print("[SUCCESS] 上市日期同步完成")
    print(f"     交易所返回      : {stats['fetched']} 条")
    print(f"     库内已有 list_date: {stats['with_list_date']} 只")
    print(f"     STOCK 仍缺失     : {stats['stock_without_list_date']} 只")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
