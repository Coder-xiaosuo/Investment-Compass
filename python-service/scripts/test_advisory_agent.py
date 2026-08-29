"""Advisory Agent Demo 测试脚本。

直接调用 advisory 子 Agent 的内部 LangGraph（绕过主 Agent 编排），
验证 Agentic RAG 流程（plan → retrieve → synthesize）能正常工作。

测试场景：
  1. 个股新闻查询：「贵州茅台最近有什么新闻」
  2. 券商研报查询：「券商怎么看宁德时代」
  3. 概念解释（不查数据）：「什么是市盈率」

用法:
    cd python-service
    .\\venv\\Scripts\\python.exe scripts/test_advisory_agent.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time

# Ensure python-service directory is on sys.path (for scripts/ subdir runs)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Windows 中文输出兜底
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

SEP = "=" * 70
SUB = "-" * 70


def hdr(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


def sub(title: str) -> None:
    print(f"\n{SUB}\n  {title}\n{SUB}")


async def run_case(name: str, user_input: str, timeout: float = 120) -> dict:
    """运行单个测试用例，直接调用 advisory 子 Agent 的图。

    返回 structured_response（AdvisoryResult.model_dump()）。
    """
    print(f"\n{SEP}")
    print(f"  [测试] {name}")
    print(f"  [输入] {user_input}")
    print(f"{SEP}")

    from agents.advisory_agent import build_advisory_agent

    agent = build_advisory_agent()
    # CompiledSubAgent 在 deepagents 0.7.x 中是 dict 子类，字段经 [] 访问
    graph = agent["runnable"] if isinstance(agent, dict) else getattr(agent, "runnable", None)

    t0 = time.time()
    try:
        result = await asyncio.wait_for(
            graph.ainvoke({"messages": [{"role": "user", "content": user_input}]}),
            timeout=timeout,
        )
        elapsed = time.time() - t0
        print(f"[耗时] {elapsed:.1f}s")

        sr = result.get("structured_response") or {}
        if not sr:
            # 兜底：从 messages 取最后一条
            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                content = getattr(last, "content", "") or (
                    last.get("content", "") if isinstance(last, dict) else ""
                )
                sr = {"answer": content, "citations": [], "confidence": 0.0}

        # 打印结果
        sub("结果")
        answer = sr.get("answer", "")
        print(f"  confidence: {sr.get('confidence', 0.0):.2f}")
        print(f"  answer ({len(answer)} chars):")
        print("  " + answer.replace("\n", "\n  "))

        citations = sr.get("citations") or []
        if citations:
            sub(f"引用 ({len(citations)} 条)")
            for i, c in enumerate(citations, start=1):
                print(f"  [{i}] {c.get('source', '')} | {c.get('publish_time', '')}")
                print(f"      {c.get('title', '')}")
                if c.get("url"):
                    print(f"      {c.get('url', '')}")
        else:
            print("  [无引用]")

        # 也打印中间状态（便于调试 Agentic RAG 流程）
        sub("内部状态")
        plan = result.get("plan") or {}
        print(f"  plan.intent: {plan.get('intent', '')}")
        print(f"  plan.stock_code: {plan.get('stock_code', '')}")
        print(f"  plan.stock_name: {plan.get('stock_name', '')}")
        print(f"  plan.needs_retrieval: {plan.get('needs_retrieval', True)}")
        print(f"  loop_count: {result.get('loop_count', 0)}")
        print(f"  retrieved_news: {len(result.get('retrieved_news', []))} 条")
        print(f"  retrieved_reports: {len(result.get('retrieved_reports', []))} 条")
        return sr
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"[失败] {elapsed:.1f}s - {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc(limit=3)
        return {}


async def main() -> None:
    hdr("Step 0: Init DB / Create tables")
    from shared.config import _engine, settings
    from shared.models import Base
    print(f"  DB URL: {settings.DATABASE_URL}")
    Base.metadata.create_all(_engine)
    print("  OK")

    hdr("Step 1: 检查 LLM 配置")
    from shared.config import settings as s
    print(f"  DEEPSEEK_MODEL: {s.DEEPSEEK_MODEL}")
    print(f"  DEEPSEEK_API_KEY: {'已配置' if s.DEEPSEEK_API_KEY else '未配置（将失败）'}")

    results: list[tuple[str, bool]] = []

    # ── 1. 个股新闻查询 ──────────────────────────────────────────
    hdr("Step 2: 个股新闻查询")
    sr1 = await run_case("个股新闻-茅台", "贵州茅台最近有什么新闻？", timeout=120)
    results.append(("个股新闻-茅台", bool(sr1.get("answer")) and sr1.get("confidence", 0) > 0))

    # ── 2. 券商研报查询 ──────────────────────────────────────────
    hdr("Step 3: 券商研报查询")
    sr2 = await run_case("券商研报-宁德时代", "券商怎么看宁德时代？", timeout=120)
    results.append(("券商研报-宁德时代", bool(sr2.get("answer")) and sr2.get("confidence", 0) > 0))

    # ── 3. 概念解释（不查数据，应跳过 retrieve） ─────────────────
    hdr("Step 4: 概念解释（不检索）")
    sr3 = await run_case("概念解释-市盈率", "什么是市盈率？为什么要看这个指标？", timeout=60)
    # 概念解释：不需要有 citations，但 answer 应非空
    results.append(("概念解释-市盈率", bool(sr3.get("answer"))))

    # ── 汇总 ────────────────────────────────────────────────────
    hdr("测试结果汇总")
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
