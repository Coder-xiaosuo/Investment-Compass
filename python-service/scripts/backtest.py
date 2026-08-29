#!/usr/bin/env python3
"""LLM 模式历史回测命令行入口 — 对历史区间执行真实引擎决策回放并输出汇总。

复用 services/backtest_service.run_backtest_llm（真实 value_assessment +
technical_analysis 子 Agent 逐点分析 + horizon 日 HIT 率验证），控制台输出
中文汇总，可选用 --report 将完整结果（meta / decisions / summary）写入 JSON 文件。

Usage::

    # 回测比亚迪 2025 全年（step=5 交易日采样，horizon=10 日验证）
    python scripts/backtest.py --symbol 002594 --start 2025-01-01 --end 2025-12-31

    # 输出完整 JSON 报告（含逐点决策明细）
    python scripts/backtest.py --symbol 002594 --start 2025-01-01 --end 2025-12-31 \\
        --step 5 --horizon 10 --report out/backtest_002594_2025_llm.json

注意：LLM 模式逐点调用 2 次 LLM（估值定性 + 技术分析），区间越长耗时越久；
且 LLM 通用知识存在时点泄漏，结果仅代表引擎行为近似。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# 保证包根目录可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _pct(val, digits: int = 2) -> str:
    """把 0~1 比值格式化成百分比字符串（None 显示 N/A，保证对齐）。"""
    if val is None:
        return "N/A"
    return f"{float(val) * 100:.{digits}f}%"


def _fmt_count(val) -> str:
    """数值格式化（None 显示 N/A），供非百分比统计项使用。"""
    return "N/A" if val is None else str(val)


def _print_summary(meta: dict, summary: dict) -> None:
    """控制台输出汇总（中文、易读、冒号对齐）。

    meta 为回测参数（symbol/start/end/step/horizon 等），summary 为统计结果。
    """
    print("========== 回测汇总 ==========")
    for key in ("symbol", "start", "end", "step", "horizon", "mode"):
        print(f"  {key:<20}: {_fmt_count(meta.get(key))}")

    for key in ("total_trading_days", "sample_count"):
        print(f"  {key:<20}: {_fmt_count(summary.get(key))}")

    print(f"  {'total_analyzed':<20}: {_fmt_count(summary.get('total_analyzed'))}")
    print(f"  {'skipped_history':<20}: {_fmt_count(summary.get('skipped_history'))}")

    action_dist = summary.get("action_dist") or {}
    print(
        f"  {'action_dist':<20}: "
        f"BUY={action_dist.get('BUY', 0)} "
        f"SELL={action_dist.get('SELL', 0)} "
        f"HOLD={action_dist.get('HOLD', 0)}"
    )

    verdict_count = summary.get("verdict_count") or {}
    print(
        f"  {'evaluated_count':<20}: {_fmt_count(summary.get('evaluated_count'))}\n"
        f"  {'hit_count':<20}: {_fmt_count(summary.get('hit_count'))}\n"
        f"  {'hit_rate':<20}: {_pct(summary.get('hit_rate'))}\n"
        f"  {'verdict_count':<20}: "
        f"HIT={verdict_count.get('HIT', 0)} MISS={verdict_count.get('MISS', 0)}"
    )

    print(f"  {'avg_profit_ratio':<20}: {_pct(summary.get('avg_profit_ratio'))}")
    print(f"  {'avg_high_ratio':<20}: {_pct(summary.get('avg_high_ratio'))}")
    print(f"  {'avg_low_ratio':<20}: {_pct(summary.get('avg_low_ratio'))}")
    print(f"  {'valuation_missing_rate':<20}: {_pct(summary.get('valuation_missing_rate'))}")

    print("  per_action_stats:")
    per_action_stats = summary.get("per_action_stats") or {}
    for act in ("BUY", "SELL", "HOLD"):
        stat = per_action_stats.get(act) or {}
        print(
            f"    {act:<5}: count={stat.get('count', 0)}  "
            f"hit_rate={_pct(stat.get('hit_rate'))}  "
            f"avg_profit_ratio={_pct(stat.get('avg_profit_ratio'))}"
        )


def _write_report(result: dict, report_path: str) -> None:
    """把完整回测结果写入 JSON 文件（ensure_ascii=False，日期对象转字符串）。"""
    parent = os.path.dirname(os.path.abspath(report_path))
    os.makedirs(parent, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"报告已写入: {os.path.abspath(report_path)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="历史回测（LLM 模式）：对历史区间执行真实 VA+TA 子 Agent 决策回放"
        "并输出 HIT 率等汇总（走真实估值 LLM 定性 + 技术面 LLM 分析，逐点 2 次 LLM 调用）",
    )
    parser.add_argument("--symbol", required=True, help="股票代码（6 位数字，可带后缀如 600519.SH）")
    parser.add_argument("--start", required=True, help="回测起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="回测结束日期 YYYY-MM-DD")
    parser.add_argument("--step", type=int, default=5, help="交易日采样间隔（默认 5）")
    parser.add_argument("--horizon", type=int, default=10, help="验证窗口 K 线根数（默认 10）")
    parser.add_argument("--report", default=None, help="JSON 报告输出路径（可选）")
    args = parser.parse_args()

    # LLM 模式：真实 VA+TA 子 Agent（异步，逐点 2 次 LLM 调用）
    import asyncio

    from services.backtest_service import run_backtest_llm

    logger.info(
        "开始回测: symbol=%s start=%s end=%s step=%s horizon=%s mode=llm",
        args.symbol, args.start, args.end, args.step, args.horizon,
    )
    result = asyncio.run(
        run_backtest_llm(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            step=args.step,
            horizon=args.horizon,
        )
    )

    summary = result.get("summary") or {}
    meta = result.get("meta") or {}
    decisions = result.get("decisions") or []

    _print_summary(meta, summary)

    # 边界：无决策或全部被跳过（如区间内缺行情数据）时给出提示，但统计照常输出 0
    if not decisions:
        print(
            "\n[提示] 区间内未生成任何决策点：请确认 start/end 区间在 market_data "
            "中有数据（如 600519 在 2025-01~2025-11 缺数据）。"
        )
    elif summary.get("skipped_history", 0) == len(decisions):
        print(
            "\n[提示] 全部采样点均因数据不足被跳过（历史 K 线 < 30 根或验证行情不足），"
            "请检查 start 是否过晚 / end 是否过早。"
        )

    # 无 --report 时也打印一段 summary JSON，方便调用方解析
    if not args.report:
        print("\n---------- summary JSON ----------")
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

    # --report 指定时写入完整结果（meta / decisions / summary）
    if args.report:
        _write_report(result, args.report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
