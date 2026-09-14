#!/usr/bin/env python3
"""刷新 A 股交易日历文件（L1 审计基准）。

用法：
    cd python-service && ./.venv/bin/python scripts/sync_trading_calendar.py

产出：data/trading_calendar.json（静态参考数据，建议随仓库提交）
建议刷新频率：每季度一次，或交易所公布次年节假日安排后。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from services import trading_calendar_service as tcs


def main() -> int:
    n = tcs.refresh_from_source()
    info = tcs.stats()
    print(f"[OK] 交易日历已刷新：{n} 个交易日")
    print(f"     覆盖范围: {info['min_date']} ~ {info['max_date']}")
    print(f"     数据源  : {info['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
