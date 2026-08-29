"""端到端测试：主 Agent → 子 Agent 链路验证（方向一）。

用法: cd python-service && .venv/bin/python scripts/e2e_agent_test.py
"""

import asyncio
import os
import sys
import time

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVICE_DIR)
os.chdir(SERVICE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(SERVICE_DIR, ".env"))


async def run_case(name: str, user_input: str, timeout: float = 180) -> bool:
    print(f"\n{'=' * 70}")
    print(f"[测试] {name}")
    print(f"[输入] {user_input}")
    print(f"{'=' * 70}")

    from agents.main_agent import ainvoke

    t0 = time.time()
    try:
        result = await asyncio.wait_for(ainvoke(user_input), timeout=timeout)
        elapsed = time.time() - t0
        print(f"[耗时] {elapsed:.1f}s")

        if result.get("error_context"):
            print(f"[错误] {result['error_context']}")
            return False

        content = result.get("content", "")
        print(f"[回复]\n{content}")
        return True
    except Exception as e:
        print(f"[异常] {type(e).__name__}: {e}")
        return False


async def main() -> None:
    results: list[tuple[str, bool]] = []

    # ── 1. 自选股子 Agent（快速） ────────────────────────────────
    results.append(("自选股-添加", await run_case("自选股-添加", "帮我关注平安银行", timeout=60)))
    results.append(("自选股-查询", await run_case("自选股-查询", "我的自选股有哪些", timeout=60)))

    # ── 2. 投资分析子 Agent（慢，VA + 条件边 + PA） ───────────────
    results.append(("投资分析-茅台", await run_case("投资分析-茅台", "分析一下贵州茅台", timeout=240)))

    # ── 汇总 ────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("测试结果汇总：")
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
