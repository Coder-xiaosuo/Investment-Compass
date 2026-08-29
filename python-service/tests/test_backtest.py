#!/usr/bin/env python3
"""历史回测能力系统测试（spec: .trae/specs/historical-backtest/ 相关验证）。

覆盖（LLM 回测模式删除规则层后的保留用例）：
1. report_available_on 披露日边界（Q1/Q2/Q3/Q4，含跨年；date 对象与字符串均支持）
2. _evaluate 决策验证口径（HIT/MISS、profit_ratio、future_bars 不足）
3. DB 相关：get_financial_abstract / get_valuation 的 as_of 回溯防未来函数

运行方式（本项目未安装 pytest，直接用解释器运行）：
    .venv/bin/python tests/test_backtest.py

若日后安装 pytest，本文件亦为 pytest 风格（def test_* + assert），可直接被 pytest 收集。
DB 用例失败时不影响其余用例；连接类错误会被标记为「环境限制」。
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import date

# 保证 python-service 包根目录可导入（tests/ 的上一级）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 被测模块（纯函数用例不依赖 DB；DB 用例连接惰性，未连接前不会抛错） ──
from services.backtest_service import _evaluate
from services.financial_data_service import report_available_on, get_financial_abstract
from services.valuation_service import get_valuation

DB_CASES = False  # 运行前由 __main__ 置为 True，用于区分 DB 用例与纯函数用例


# ══════════════════════════════════════════════════════════════════════
# 1. report_available_on 披露日边界
# ══════════════════════════════════════════════════════════════════════
def test_report_available_on_q1():
    """Q1（一季报）→ 当年 04-30。"""
    assert report_available_on("Q1", "2025-03-31") == date(2025, 4, 30)


def test_report_available_on_q2():
    """Q2（半年报）→ 当年 08-31。"""
    assert report_available_on("Q2", "2025-06-30") == date(2025, 8, 31)


def test_report_available_on_q3():
    """Q3（三季报）→ 当年 10-31。"""
    assert report_available_on("Q3", "2025-09-30") == date(2025, 10, 31)


def test_report_available_on_q4_cross_year():
    """Q4（年报）跨年 → 次年 04-30（2024 年报 2025-04-30 披露）。"""
    assert report_available_on("Q4", "2024-12-31") == date(2025, 4, 30)


def test_report_available_on_q4_2025():
    """Q4（年报）跨年 → 次年 04-30（2025 年报 2026-04-30 披露）。"""
    assert report_available_on("Q4", "2025-12-31") == date(2026, 4, 30)


def test_report_available_on_date_object():
    """输入为 date 对象时行为一致。"""
    assert report_available_on("Q1", date(2025, 3, 31)) == date(2025, 4, 30)
    assert report_available_on("Q2", date(2025, 6, 30)) == date(2025, 8, 31)
    assert report_available_on("Q4", date(2025, 12, 31)) == date(2026, 4, 30)


# ══════════════════════════════════════════════════════════════════════
# 2. _evaluate 决策验证口径（口径与 scripts/review_decisions.py 一致）
# ══════════════════════════════════════════════════════════════════════
def _future_bars(close: float, n: int, high: float | None = None, low: float | None = None) -> list[dict]:
    """构造 n 根 future_bars，每根 close/high/low 相同（high 默认 +1%，low 默认 -1%）。"""
    high = high if high is not None else round(close * 1.01, 2)
    low = low if low is not None else round(close * 0.99, 2)
    return [{"trade_date": f"2024-01-{i:02d}", "close": close, "high": high, "low": low}
            for i in range(1, n + 1)]


def test_evaluate_buy_hit():
    """BUY 且 close_10 > current_price → HIT，profit_ratio 按 close_10/current_price - 1 计算。"""
    current_price = 100.0
    bars = _future_bars(close=105.0, n=10, high=106.0, low=99.0)
    ev = _evaluate("BUY", current_price, bars, horizon=10)
    assert ev["evaluated"] is True
    assert ev["verdict"] == "HIT"
    assert ev["profit_ratio"] == 0.05          # round(105/100 - 1, 4)
    assert ev["high_ratio"] == 0.06            # round(106/100 - 1, 4)
    assert ev["low_ratio"] == -0.01            # round(99/100 - 1, 4)
    assert ev["close_10"] == 105.0
    assert ev["actual_trend"] == "上涨"


def test_evaluate_buy_miss():
    """BUY 但 close_10 <= current_price → MISS。"""
    bars = _future_bars(close=98.0, n=10)
    ev = _evaluate("BUY", 100.0, bars, horizon=10)
    assert ev["evaluated"] is True
    assert ev["verdict"] == "MISS"


def test_evaluate_sell_hit():
    """SELL 且 close_10 < current_price → HIT。"""
    bars = _future_bars(close=95.0, n=10, high=96.0, low=94.0)
    ev = _evaluate("SELL", 100.0, bars, horizon=10)
    assert ev["evaluated"] is True
    assert ev["verdict"] == "HIT"
    assert ev["profit_ratio"] == -0.05          # round(95/100 - 1, 4)
    assert ev["actual_trend"] == "下跌"


def test_evaluate_sell_miss():
    """SELL 但 close_10 >= current_price → MISS。"""
    bars = _future_bars(close=102.0, n=10)
    ev = _evaluate("SELL", 100.0, bars, horizon=10)
    assert ev["evaluated"] is True
    assert ev["verdict"] == "MISS"


def test_evaluate_insufficient_bars():
    """future_bars 不足 horizon 根 → evaluated=False，不产出 HIT/MISS。"""
    bars = _future_bars(close=105.0, n=5)  # 仅 5 根 < horizon 10
    ev = _evaluate("BUY", 100.0, bars, horizon=10)
    assert ev["evaluated"] is False
    assert ev["reason"] == "后续行情不足"


# ══════════════════════════════════════════════════════════════════════
# 3. DB 相关用例（600519 数据环境：market_data 2024 全年 / 2026 完整；
#    2025-01~2025-11 缺数据；估值历史已回填 2086+ 行）
# ══════════════════════════════════════════════════════════════════════
def test_db_financial_abstract_asof():
    """as_of 回溯防未来函数：2025-06-15 时点 Q2(2025-06-30) 未到披露日(08-31)，
    应取到已披露的 Q1 2025-03-31。"""
    abstract = get_financial_abstract("600519", as_of="2025-06-15")
    assert abstract.get("report_date") == "2025-03-31", (
        f"as_of 回溯取错期: {abstract.get('report_date')}"
    )
    assert abstract.get("report_type") == "Q1"


def test_db_financial_abstract_latest():
    """无 as_of 返回最新一期（当前为 2026-03-31）；仅断言非空且不早于 as_of 版本。"""
    latest = get_financial_abstract("600519")
    assert latest.get("report_date"), f"最新一期 report_date 为空: {latest}"
    assert latest.get("report_type"), f"最新一期 report_type 为空: {latest}"
    asof = get_financial_abstract("600519", as_of="2025-06-15")
    # YYYY-MM-DD 字典序即时间序；latest 不应早于 as_of 版本
    assert latest["report_date"] >= asof.get("report_date", ""), (
        f"最新一期 {latest['report_date']} 早于 as_of 版本 {asof.get('report_date')}"
    )


def test_db_valuation_asof():
    """估值 as_of 回溯：2025-06-15 时点返回 trade_date <= 2025-06-15 的最新一条。"""
    valuation = get_valuation("600519", as_of="2025-06-15")
    assert valuation, "as_of 估值查询返回空"
    assert valuation.get("trade_date") <= "2025-06-15", (
        f"估值 trade_date {valuation.get('trade_date')} 晚于 as_of"
    )


# ══════════════════════════════════════════════════════════════════════
# 手动 runner（pytest 不可用时直接运行本文件）
# ══════════════════════════════════════════════════════════════════════
def _collect_tests() -> list[tuple[str, callable]]:
    """收集本模块内所有 test_* 函数（按定义顺序）。"""
    import inspect
    return [(name, obj) for name, obj in inspect.getmembers(sys.modules[__name__])
            if name.startswith("test_") and callable(obj)]


def main() -> int:
    global DB_CASES
    tests = _collect_tests()
    passed, failed = 0, 0
    failures: list[tuple[str, str]] = []

    print(f"共发现 {len(tests)} 个用例\n")
    for name, fn in tests:
        # 按函数名标记 DB 用例（test_db_*），失败原因若是连接类错误记为环境限制
        is_db = name.startswith("test_db_")
        try:
            DB_CASES = is_db
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception:
            print(f"  [FAIL] {name}")
            tb = traceback.format_exc()
            print("         " + tb.replace("\n", "\n         "))
            failures.append((name, tb))
            failed += 1

    print("\n" + "=" * 60)
    print(f"通过: {passed} / {len(tests)}，失败: {failed}")
    for name, tb in failures:
        if name.startswith("test_db_"):
            # DB 连接类错误通常为环境限制（数据库不可达/数据缺失），
            # 与功能缺陷区分开：贴出错误，注明环境限制。
            if any(k in tb for k in ("OperationalError", "Connection refused",
                                     "Can't connect", "pymysql", "2003", "Access denied")):
                print(f"\n  [环境限制] {name} 因数据库不可达失败（不影响功能判断）:\n{tb}")
            else:
                print(f"\n  [失败] {name}（DB 用例，非连接类错误，请排查）:\n{tb}")
        else:
            print(f"\n  [失败] {name}（纯函数用例）:\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
