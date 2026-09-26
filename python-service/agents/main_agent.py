"""
Investment Compass Main Agent — 基于 LangChain Deep Agents 的主控 Agent。

职责：统一接收用户输入，通过 SubAgent middleware 委派子 Agent，汇总输出。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.memory import MemoryMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import PIIMiddleware, ModelCallLimitMiddleware, TodoListMiddleware
from langchain.tools import tool
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from agents.advisory_agent import build_advisory_agent
from agents.ai_reader_agent import build_ai_reader_subagent
from agents.technical_analysis_agent import build_technical_analysis_agent
from agents.value_assessment_agent import VALUE_ASSESSMENT_SUBAGENT
from agents.watchlist import WATCHLIST_SUBAGENT
from shared.config import deepseek_model_kwargs, settings
from shared.deepseek_llm import DeepSeekChatOpenAI

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# HITL Checkpointer（Redis Stack 单例）
# ──────────────────────────────────────────────────────────────────────────────

_checkpointer: Any | None = None


async def get_checkpointer():
    """获取 Redis checkpointer（进程级单例）。

    供 create_deep_agent 的 interrupt_on 使用：估值完成后中断征求用户决策。
    - 单例复用：agent 重建不会丢失既有线程状态（状态存于 Redis）。
    - 后端要求 Redis Stack：AsyncRedisSaver 经 redisvl 建 RediSearch 索引，
      并用 RedisJSON 读写 checkpoint；普通 Redis 缺少 JSON.SET / FT.CREATE
      会在 asetup 阶段失败（见 docker-compose.redis.yml）。
    - 初始化失败（Redis 不可用 / 缺模块）时告警并返回 None，
      调用方（build_main_agent）据此降级为无中断流程。
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    try:
        saver = AsyncRedisSaver(redis_url=settings.REDIS_URL)
        # 建索引：已存在则跳过（redisvl create(overwrite=False) 语义），
        # 多 worker 并发启动安全
        await saver.asetup()
        _checkpointer = saver
        logger.info("Redis checkpointer 初始化成功: %s", settings.REDIS_URL)
    except Exception as e:
        logger.warning(
            "Redis checkpointer 初始化失败（HITL 不可用）: %s", e, exc_info=True
        )
        _checkpointer = None
    return _checkpointer


# ──────────────────────────────────────────────────────────────────────────────
# HITL 确认工具
# ──────────────────────────────────────────────────────────────────────────────


@tool
def confirm_proceed_analysis(stock_identifier: str, recommend: bool, reason: str) -> str:
    """向用户征求是否进入技术面分析。工具本身不执行任何操作，用于暂停流程等待用户决策。

    参数:
        stock_identifier: 股票代码或名称（沿用估值阶段的标识）。
        recommend: 估值阶段的推荐结论（是否推荐进入技术面分析）。
        reason: 估值阶段给出的推荐/不推荐理由。
    """
    # 该工具仅作为中断标记：被调用时 HumanInTheLoopMiddleware 会暂停图执行
    # 并征求用户决策（approve=进入 / reject=跳过 / respond=直接回复）。
    # 注意：仅在用户 approve（或直接调用）后工具才真正被执行，返回文本会
    # 作为 ToolMessage 交给模型，必须明确表达"用户已批准、继续委派技术分析"，
    # 否则模型会误以为仍需征求决策而重复中断/空转。
    return (
        f"用户已批准对 {stock_identifier} 进入技术面分析（决策：approve）。"
        "请立即委派 technical_analysis 子 Agent 执行技术分析，"
        "并以 JSON 传入 {\"stock_identifier\": \"...\", \"va_summary\": {...}}。"
    )

# ──────────────────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是投资罗盘（Investment Compass）的主控智能体，负责 A 股投研分析。

## 你的身份
你是用户的投研分析伙伴与团队主管：统筹分析任务，将专业工作分派给合适的执行者，汇集各执行者的结论后，向用户给出清晰、可执行、有依据的综合判断。

## 行为准则
- 先理解用户意图，再组织工作；需要专业分工时，把任务交给合适的执行者（可用执行者、任务编排、文件与数据规范详见 AGENTS.md）。
- 汇集各执行者返回的结果，整合为一份面向用户的最终回答，并引用其数据作为依据。
- 结论存在矛盾或不确定性时，如实向用户说明风险；绝不编造数据。
- 涉及决策类工作时，遵循 AGENTS.md 中规定的征求确认流程，把关键决策交给用户拍板。
- 输出简洁、结构化；始终以中文回答。

## 输出要求
- 投资分析结果必须给出明确的综合判断：强烈买入 / 轻仓试水 / 等买点 / 不关注 / 减仓警惕 / 清仓
- 引用执行者返回的估值分数与技术面信号作为依据
- 估值与技术面矛盾时，明确提示用户注意风险

## A 股市场约束
- T+1 交易制度：当日买入不可当日卖出
- 涨跌停限制：主板 ±10%，创业板/科创板 ±20%
- 交易时间：工作日 9:30-11:30、13:00-15:00
- 量价信号：量比 > 2 为放量确认，量比 < 0.5 为缩量警示
- 推荐使用日线（1d）作为默认分析周期

## 记忆维护（自我进化）
你的长期记忆文件为 `/memories/preferences.md`（位置与规范见 AGENTS.md）。它只承载**跨会话依然有价值**的信息，帮助你在未来对话中更贴合用户。

**值得记录的内容**（用户在对话中自然透露时，主动写入）：
- 身份信息：称呼、职业、背景等（如"我是程序员"、"叫我小萧"）
- 投资偏好：风险偏好、决策风格、关注板块/标的、分析深度、仓位习惯
- 长期事实：持仓标的、常用周期、对某类信号的态度
- 反馈修正：用户明确纠正或强调过的偏好（如"我只看技术面"）

**不值得记录的内容**（即使提及也不写入）：
- 一次性问题、临时请求、当前任务上下文
- 寒暄、问候、闲聊
- 时效性信息（如"今天想看看 XX"）
- 敏感信息：API Key、密码、账号、身份证号等

写入要求：简洁、不冗余、保持既有文件结构；不确定是否值得记录时宁可少写，不重复已有内容。"""




# ──────────────────────────────────────────────────────────────────────────────
# Agent factory
# ──────────────────────────────────────────────────────────────────────────────

_agent: Any = None


async def build_main_agent():
    """构建并返回主控 Agent 实例（单例）。

    异步化原因：需要 await get_checkpointer() 获取 HITL checkpointer。
    """
    global _agent
    if _agent is not None:
        return _agent

    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY 未配置，主 Agent 将无法正常使用")
        _agent = None
        return None

    model = DeepSeekChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        extra_body=deepseek_model_kwargs(),
    )

    # 构建 CompiledSubAgent（两阶段编排：value_assessment → technical_analysis）
    technical_agent = build_technical_analysis_agent()
    advisory_agent = build_advisory_agent()
    subagents = [VALUE_ASSESSMENT_SUBAGENT, technical_agent, WATCHLIST_SUBAGENT, advisory_agent]
    # HITL checkpointer（单例；Redis 不可用时为 None，HITL 降级为无中断流程）
    checkpointer = await get_checkpointer()

    # 文件系统 backend（CompositeBackend 分层）：
    # - default  -> data/workspace  内部数据（大结果卸载 /large_tool_results/、对话历史 /conversation_history/）落盘持久
    # - /reports/ -> data/reports   分析报告归档（只读保护）
    # - /memories/ -> memories/     用户偏好记忆（agent 可写，edit_file 自学）
    # 写权限限定：仅允许写 /memories/，其余路径 deny（防止 agent 篡改报告/内部数据/项目文件）
    PROJECT = Path(__file__).resolve().parent.parent  # python-service/
    reports_dir = PROJECT / "data" / "reports"
    workspace_dir = PROJECT / "data" / "workspace"
    memories_dir = PROJECT / "memories"
    for _d in (reports_dir, workspace_dir, memories_dir):
        os.makedirs(_d, exist_ok=True)
    backend = CompositeBackend(
        default=FilesystemBackend(root_dir=workspace_dir, virtual_mode=True),
        routes={
            "/reports/": FilesystemBackend(root_dir=reports_dir, virtual_mode=True),
            "/memories/": FilesystemBackend(root_dir=memories_dir, virtual_mode=True),
        },
    )
    # 记忆读取 backend：与主 Agent MemoryMiddleware 共用同一实例，保证记忆统一
    memory_backend = FilesystemBackend(root_dir=PROJECT, virtual_mode=True)
    fs_permissions = [
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ]

    # ai_reader（看板卡片解读）：复用同一 memory_backend 挂 MemoryMiddleware → 记忆统一
    subagents.append(build_ai_reader_subagent(memory_backend))

    _agent = create_deep_agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[confirm_proceed_analysis],
        subagents=subagents,
        middleware=[
            PIIMiddleware("email", strategy="redact"),
            ModelCallLimitMiddleware(run_limit=50),
            TodoListMiddleware(),
            MemoryMiddleware(
                backend=memory_backend,
                sources=["/AGENTS.md", "/memories/preferences.md"],
            ),
            # 上下文压缩：达到 DeepSeek 64K 窗口 ~85% 时自动摘要有损压缩，
            # 保留最近 6000 tokens 完整消息；与 chat_service 落库统计同一口径（count_tokens_approximately）
            SummarizationMiddleware(
                model=model,
                backend=backend,
                trigger=("tokens", 54000),
                keep=("tokens", 6000),
            ),
        ],
        backend=backend,
        permissions=fs_permissions,
        # 估值完成后中断征求用户决策（approve进入/reject跳过/respond直接回复）
        interrupt_on={
            "confirm_proceed_analysis": {
                "allowed_decisions": ["approve", "reject", "respond"],
            }
        },
        checkpointer=checkpointer,
        debug=False,
    )
    logger.info(
        "Main agent filesystem backend ready: /reports/ -> %s, /memories/ -> %s, workspace -> %s",
        reports_dir, memories_dir, workspace_dir,
    )
    logger.info(
        "Main agent built with model=%s, subagents=%s, checkpointer=%s",
        model.model_name,
        [s["name"] for s in subagents],
        checkpointer is not None,
    )
    return _agent


def reset_agent():
    """重置单例（用于测试）。"""
    global _agent
    _agent = None


async def ainvoke(user_input: str) -> Dict[str, Any]:
    """异步调用主 Agent，返回原始响应。

    如果主 Agent 未就绪（API Key 未配置等），返回错误 dict。
    """
    agent = await build_main_agent()
    if agent is None:
        return {
            "content": "",
            "error_context": {
                "code": "agent_unavailable",
                "reason": "missing_api_key",
                "detail": "主 Agent 未就绪：DEEPSEEK_API_KEY 未配置",
            },
        }

    try:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": user_input}],
        })

        messages = result.get("messages", [])
        # 回溯找最后一条非空 AIMessage（DeepSeek 偶发产生空尾随消息）
        content = ""
        for msg in reversed(messages):
            if isinstance(msg, dict):
                if msg.get("type") == "ai" and msg.get("content"):
                    content = msg["content"]
                    break
                if msg.get("content"):
                    content = str(msg["content"])
                    break
            elif getattr(msg, "type", "") == "ai":
                text = getattr(msg, "content", "") or ""
                if text:
                    content = text
                    break

        return {"content": content, "raw": result}

    except Exception as e:
        logger.error("Main agent invoke failed: %s", e, exc_info=True)
        return {
            "content": "",
            "error_context": {
                "code": "agent_error",
                "reason": str(e),
            },
        }


async def astream_agent_events(
    user_input: str,
    thread_id: str | None = None,
    resume_decisions: list | None = None,
    user_id: str = "default",
    should_stop: Callable[[], Awaitable[bool]] | None = None,
):
    """结构化事件流（v2 子图流）：主 Agent token + 子 Agent 生命周期 + 阶段事件 + HITL 中断。

    基于 ``astream(stream_mode=["messages", "custom", "updates"], subgraphs=True)``，
    按 namespace（``ns``）区分主 Agent 与子 Agent 事件。产出的事件 dict：

    - ``{"type": "token", "content": str}``
        主 Agent 最终回复的 token 增量。
    - ``{"type": "subagent_started", "subagent": str, "task_id": str}``
        主 Agent 发出 ``task`` 工具调用（子 Agent 启动）。
    - ``{"type": "subagent_completed", "subagent": str, "task_id": str}``
        ``task`` 工具返回结果（子 Agent 完成）。
    - ``{"type": "subagent_result", "subagent": str, "task_id": str, "result": dict}``
        子 Agent 返回的结构化结果（CompiledSubAgent 的 ``structured_response``，
        解析成功时在 ``subagent_completed`` 之前产出）。
    - ``{"type": "stage", "subagent": str, "stage": str, "status": str, ...}``
        子 Agent 内部自定义阶段事件（如 valuation/technical 的 started/done）。
    - ``{"type": "interrupt", "data": HITLRequest, "ns"?: list}``
        HITL 中断事件：估值完成后征求用户决策。``data`` 为 HITLRequest dict
        （``{"action_requests": [...], "review_configs": [...]}``）；``ns`` 仅在
        子图内中断时存在（主图级中断出现在空 namespace）。
    - ``{"type": "style_evolved", "inferred": dict, "applied_dims": list, "stable": bool}``
        风格画像自进化事件：HITL resume 时，LLM 推断器从「Agent 建议 + 用户反馈」
        推断 6 维度 score 调整，并应用到 style_profiles 矩阵。前端可据此显示
        「已记住你的风格偏好」提示，并刷新雷达图。
    - ``{"type": "done", "interrupted": bool}``
        本轮事件流结束；``interrupted`` 标记是否因 HITL 中断而结束。
    - ``{"type": "cancelled"}``
        软取消命中：本轮在安全检查点主动退出（不抛异常，调用方可正常落库收尾）。

    Args:
        user_input: 用户输入（resume 模式下被忽略，不会追加为新消息）。
        thread_id: langgraph 线程 ID，必传才有 resume 语义；为 None 时内部
            用 uuid7 生成一个并在本次调用内复用（不落库）。
        resume_decisions: 非空时进入 resume 模式：用
            ``Command(resume={"decisions": ...})`` 续流同一线程。
        user_id: 用户ID（默认 'default'，单用户场景）。用于风格画像匹配与
        长期记忆持久化；正常对话流忽略此参数。
        should_stop: 软取消检查函数（协作式取消）。每个事件边界调用一次，
            返回 True 时本轮主动退出：内部事件流被显式关闭，避免图继续后台推进。

    主 Agent 未就绪（缺少 API Key）时仅产出 done 事件。
    """
    agent = await build_main_agent()
    if agent is None:
        logger.warning("astream_agent_events: 主 Agent 未就绪（缺少 API Key）")
        yield {"type": "done", "interrupted": False}
        return

    # thread_id 必传才有 resume 语义；未传时生成一个并在本调用内复用
    if not thread_id:
        from langchain_core.utils.uuid import uuid7
        thread_id = str(uuid7())

    config = {"configurable": {"thread_id": thread_id}}

    # resume 模式：用 Command(resume=...) 续流同一线程，不再追加新的 user 消息
    if resume_decisions:
        from langgraph.types import Command
        graph_input = Command(resume={"decisions": resume_decisions})
        # 告警：checkpointer 不可用时线程状态未持久化，resume 必然失败
        try:
            if await get_checkpointer() is None:
                logger.warning(
                    "astream_agent_events: resume 请求但 Redis checkpointer 不可用，"
                    "该线程无法真正续流（thread_id=%s）",
                    thread_id,
                )
        except Exception:
            logger.warning(
                "astream_agent_events: 检查 checkpointer 可用性失败，"
                "resume 可能失败（thread_id=%s）",
                thread_id,
            )
    else:
        graph_input = {"messages": [{"role": "user", "content": user_input}]}

    # ── HITL 反馈观察：resume 模式下，对用户的 approve/reject/respond 调用 ──
    # LLM 推断器，自动调整 style_profiles 矩阵（用户无感自进化）。
    # 仅 resume 模式触发；非 resume 是新对话，无 HITL 反馈可观察。
    if resume_decisions:
        try:
            from services.style_profiler import observe_feedback
            # 从 resume_decisions 提取动作与文本
            decisions_list = (
                resume_decisions.get("decisions", [])
                if isinstance(resume_decisions, dict)
                else (resume_decisions if isinstance(resume_decisions, list) else [])
            )
            for dec in decisions_list:
                if not isinstance(dec, dict):
                    continue
                action = dec.get("type") or dec.get("action") or ""
                response_text = dec.get("args", {}).get("response", "") if isinstance(dec.get("args"), dict) else ""
                # Agent 建议上下文（从 thread state 或 dec 提取）
                advice_summary = dec.get("args", {}).get("advice_summary", "") if isinstance(dec.get("args"), dict) else ""
                advice_data = dec.get("args", {}).get("advice_data", {}) if isinstance(dec.get("args"), dict) else {}
                if action in ("approve", "reject", "respond"):
                    result = observe_feedback(
                        user_id=user_id,
                        thread_id=thread_id,
                        advice_summary=advice_summary or "Agent 给出投资分析建议",
                        advice_data=advice_data,
                        user_action=action,
                        user_response=response_text,
                    )
                    # 产出 style_evolved SSE 事件（前端可显示"已记住你的风格偏好"）
                    if result.get("applied_dims"):
                        yield {
                            "type": "style_evolved",
                            "inferred": result["inferred"],
                            "applied_dims": result["applied_dims"],
                            "stable": result["stable"],
                        }
        except Exception:
            logger.warning(
                "astream_agent_events: HITL 反馈观察失败（不影响主流程）",
                exc_info=True,
            )

    # task 工具调用 ID -> 子 Agent 名称
    active_tasks: dict[str, str] = {}

    def _tool_call_args(args: Any) -> dict:
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    interrupted = False

    # 真实上下文用量采集：每次模型调用（主/子 Agent）的 usage_metadata，
    # 以"最后一次模型调用"为准（input_tokens 即当前送入模型的上下文量）。
    # 仅在该值较上次变化时产出 usage 事件，避免同值重复透传。
    latest_usage: dict[str, Any] = {}
    last_usage_yielded: int = -1

    soft_cancelled = False
    try:
        # 事件流句柄显式持有：软取消退出时 aclose，避免图在后台继续推进
        event_stream = agent.astream(
            graph_input,
            config=config,
            stream_mode=["messages", "custom", "updates"],
            subgraphs=True,
            version="v2",
        )
        async for chunk in event_stream:
            # 安全检查点：每个事件边界检查一次软取消标记（工具内部的长任务
            # 无法中途打断，退化为在下一个边界退出，属预期粒度）
            if should_stop is not None and await should_stop():
                soft_cancelled = True
                yield {"type": "cancelled"}
                break

            ctype = chunk.get("type")
            ns = chunk.get("ns")
            data = chunk.get("data")

            # 0.5 真实 usage 采集：updates 中 model 节点的完整 AIMessage 携带
            #     usage_metadata（含子 Agent 内部调用）。取最后一次非空值，
            #     产出 usage 事件供前端/会话 token 统计使用。
            if ctype == "updates" and isinstance(data, dict):
                for node, payload in data.items():
                    if not isinstance(payload, dict):
                        continue
                    for m in payload.get("messages", []):
                        if getattr(m, "type", "") != "ai":
                            continue
                        um = getattr(m, "usage_metadata", None)
                        if not um:
                            continue
                        latest_usage = {
                            "input_tokens": um.get("input_tokens") or um.get("prompt_tokens") or 0,
                            "output_tokens": um.get("output_tokens") or um.get("completion_tokens") or 0,
                            "total_tokens": um.get("total_tokens") or 0,
                        }
                inp = latest_usage.get("input_tokens") or 0
                if latest_usage and inp != last_usage_yielded:
                    last_usage_yielded = inp
                    yield {
                        "type": "usage",
                        "input_tokens": latest_usage["input_tokens"],
                        "output_tokens": latest_usage["output_tokens"],
                        "total_tokens": latest_usage["total_tokens"],
                    }

            # 0. HITL 中断检测：updates 中出现 __interrupt__ 即流程暂停征求用户决策。
            #    v2 子图流中：主图级中断出现在空 namespace（()）的 updates，
            #    子图内中断出现在对应子图 namespace；两处都检测并保留 ns。
            if ctype == "updates" and isinstance(data, dict) and "__interrupt__" in data:
                interrupted = True
                raw = data.get("__interrupt__")
                # raw 为 (Interrupt(...),) 元组，取首个元素；payload 是
                # Interrupt 对象时取其 .value（即 HITLRequest dict）
                payload = raw[0] if isinstance(raw, (list, tuple)) and raw else raw
                if payload is not None and hasattr(payload, "value"):
                    payload = payload.value
                event: dict = {"type": "interrupt", "data": payload}
                if ns:
                    # 子图内中断：保留 namespace（最后一个元素为子图名）
                    event["ns"] = list(ns)
                yield event
                break

            # 1. 主 Agent 最终回复 token 增量（仅顶层、model 节点）
            if ctype == "messages":
                if ns:
                    continue
                msg, meta = data
                if meta.get("langgraph_node") != "model":
                    continue
                # 思维链增量（DeepSeek thinking 模式返回 reasoning_content，
                # langchain 存放在 additional_kwargs；与 content 同为流式增量片段）
                reasoning = getattr(msg, "additional_kwargs", {}).get("reasoning_content") or ""
                if reasoning:
                    yield {"type": "thinking", "content": reasoning}
                content = getattr(msg, "content", "") or ""
                if content:
                    yield {"type": "token", "content": content}
                continue

            # 2. 子 Agent 自定义阶段事件
            if ctype == "custom":
                if ns and isinstance(data, dict) and data.get("event") == "stage":
                    # 从 namespace（("tools:<task_id>",)）提取 task 工具调用 ID
                    task_id = ""
                    if ns[0].startswith("tools:"):
                        task_id = ns[0].split(":", 1)[1]
                    # 兼容修复：namespace 提取的 task_id 是子图内部工具调用 ID，
                    # 与 subagent_started/completed 使用的主 Agent task 调用 ID 不一致，
                    # 会导致前端 stage 事件无法匹配到子 Agent 卡片。
                    # 用 subagent 名称反查 active_tasks，保证 stage 与 started 同 ID。
                    subagent = data.get("subagent", "")
                    if task_id not in active_tasks:
                        for _tid, _name in active_tasks.items():
                            if _name == subagent:
                                task_id = _tid
                                break
                    yield {
                        "type": "stage",
                        "subagent": subagent,
                        "task_id": task_id,
                        "stage": data.get("stage", ""),
                        "status": data.get("status", ""),
                        "score": data.get("score"),
                        "direction": data.get("direction"),
                        "stock_code": data.get("stock_code", ""),
                        "stock_name": data.get("stock_name", ""),
                        # advisory 阶段附加字段（plan/retrieve/synthesize）
                        "intent": data.get("intent"),
                        "news_count": data.get("news_count"),
                        "report_count": data.get("report_count"),
                        "confidence": data.get("confidence"),
                        "citations": data.get("citations"),
                    }
                continue

            # 3. 子 Agent 生命周期：从主 Agent 的 tool_calls / tool 结果推断
            if ctype == "updates":
                if ns:
                    continue
                # 0.5 待办列表：write_todos 工具通过 Command(update={"todos": ...}) 写回，
                #    在 tools 节点更新或顶层 state 更新中携带；完整替换，直接透传
                todos = data.get("todos")
                if todos is None and "tools" in data:
                    todos = data["tools"].get("todos")
                if todos is not None:
                    yield {"type": "todos", "todos": todos}
                if "model" in data:
                    for m in data["model"].get("messages", []):
                        if getattr(m, "type", "") != "ai":
                            continue
                        for tc in getattr(m, "tool_calls", []) or []:
                            if tc.get("name") != "task":
                                continue
                            args = _tool_call_args(tc.get("args"))
                            sub_name = args.get("subagent_type", "")
                            if sub_name:
                                active_tasks[tc.get("id", "")] = sub_name
                                yield {
                                    "type": "subagent_started",
                                    "subagent": sub_name,
                                    "task_id": tc.get("id", ""),
                                }
                if "tools" in data:
                    for m in data["tools"].get("messages", []):
                        if getattr(m, "type", "") != "tool":
                            continue
                        if getattr(m, "name", "") != "task":
                            continue
                        task_id = getattr(m, "tool_call_id", "")
                        sub_name = active_tasks.pop(task_id, "")
                        # CompiledSubAgent 的 structured_response 会 JSON 序列化进
                        # ToolMessage.content，尝试解析为结构化结果事件
                        content = getattr(m, "content", "")
                        if isinstance(content, str) and content.strip():
                            try:
                                parsed = json.loads(content)
                                if isinstance(parsed, dict):
                                    yield {
                                        "type": "subagent_result",
                                        "subagent": sub_name,
                                        "task_id": task_id,
                                        "result": parsed,
                                    }
                            except (json.JSONDecodeError, TypeError):
                                pass
                        yield {
                            "type": "subagent_completed",
                            "subagent": sub_name,
                            "task_id": task_id,
                        }
                continue
    except Exception as e:
        logger.error("Main agent event stream failed: %s", e, exc_info=True)
    finally:
        if soft_cancelled:
            # 停止消费后显式关闭内部事件流，触发 langgraph 侧的取消，
            # 否则图可能在后台继续执行（例如启动下一个子 Agent）
            try:
                await event_stream.aclose()
            except Exception:
                logger.warning("关闭主 Agent 事件流失败", exc_info=True)

    # 结束事件：标记本轮是否因 HITL 中断而结束
    yield {"type": "done", "interrupted": interrupted}


async def astream_reply(
    user_input: str,
    thread_id: str | None = None,
    resume_decisions: list | None = None,
):
    """流式生成主 Agent 回复的 token 片段（异步生成器）。

    兼容旧接口：内部走结构化事件流，仅提取主 Agent 最终回复的 token。
    子 Agent 内部输出与主 Agent 工具调用指令均被过滤。
    """
    async for event in astream_agent_events(
        user_input, thread_id=thread_id, resume_decisions=resume_decisions
    ):
        if event.get("type") == "token":
            yield event["content"]
