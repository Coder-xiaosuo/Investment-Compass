"""
Technical Analysis CompiledSubAgent — A 股技术分析子 Agent。

通过 CompiledSubAgent 机制注册到主 Agent。内部是一个 LangGraph（Pa_Agent
两阶段编排：市场诊断 → 交易决策）：
  1. parse_node:           解析输入（JSON 或自然语言）→ 获取 K 线 → 算法计算市场数据  (纯函数)
  2. features_node:        pa_features 渲染程序结构特征文本（客观锚点）  (纯函数)
  3. stage1_node:          Stage1 市场诊断（LLM）：特征 + K 线摘要 → MarketDiagnosis  (1 次 LLM)
  4. load_strategies:      基于 Stage1 诊断 + 市场数据路由策略文本  (纯函数)
  5. inject_experience:    从经验库检索相似历史案例（含失败反例）注入 state  (读侧经验闭环)
  6. pa_node:              Stage2 交易决策（LLM）：诊断 + 特征 + 策略 + 经验 → TechnicalResult  (1 次 LLM)
  7. merge_node:           合并结果，设置 structured_response 返回主 Agent

估值（value_assessment）由主 Agent 先行委派，其摘要（va_summary）随输入 JSON
传入本 Agent，仅作为背景信息与决策落库使用，不参与技术分析计算。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any

from deepagents import CompiledSubAgent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import MessagesState

from agents.pa_agent import MarketDiagnosis, TechnicalResult
from shared.config import get_llm, settings
from shared.utils import generate_trace_id

logger = logging.getLogger(__name__)

# ── 飞书推送幂等：已推送过的 trace_id 进程内缓存 ───────────────────────────────
# 根因：TA 子 Agent 每次执行 merge_node 都会推送一次飞书；HITL resume / 主 Agent
# 重复委派会导致同一决策（同一 trace_id）被多次推送。落库已用 trace_id upsert
# 幂等，此处对推送同样做幂等：推送成功后才记录，重复 trace_id 直接跳过。
_pushed_feishu_trace_ids: set[str] = set()
_feishu_lock = threading.Lock()


def _feishu_already_pushed(trace_id: str) -> bool:
    """trace_id 是否已推送过（线程安全）。"""
    if not trace_id:
        return False
    with _feishu_lock:
        return trace_id in _pushed_feishu_trace_ids


def _mark_feishu_pushed(trace_id: str) -> None:
    """记录已推送的 trace_id（线程安全）。"""
    if not trace_id:
        return
    with _feishu_lock:
        _pushed_feishu_trace_ids.add(trace_id)

# ── Prompt 目录（策略 .txt 文件位置） ──────────────────────────────────────────
_PROMPT_DIR = Path(__file__).parent.parent / "pa_analyzer" / "prompts"

# ── 策略文件映射 ────────────────────────────────────────────────────────────────
_STRATEGY_FILES: dict[str, list[str]] = {
    "bull_channel": ["上涨通道分析识别.txt", "上涨通道交易策略.txt"],
    "bear_channel": ["下跌通道分析识别.txt", "下跌通道交易策略.txt"],
    "trading_range": ["震荡区间分析识别.txt", "震荡区间交易策略.txt"],
}
# 所有分析共用的基础文件
_BASE_STRATEGY_FILES = [
    "逐棒分析检查单.txt",
    "文件16-K线信号识别.txt",
    "文件17-止损和止盈与仓位管理.txt",
    "文件23-MeasuredMove与结构目标.txt",
]
# A 股专属补充
_A_SHORE_EXTRA = {
    "涨停": "A股涨停板策略.txt",
    "缺口": "A股缺口策略.txt",
    "支撑阻力": "A股支撑阻力.txt",
    "板块联动": "A股板块联动.txt",
}


# ── State ────────────────────────────────────────────────────────────────────


class InvestmentState(MessagesState):
    """LangGraph 状态，必须包含 ``messages`` 键。"""

    stock_code: str = ""
    stock_name: str = ""
    market_data: dict = {}  # _compute_market_data() 的算法输出
    va_summary: dict = {}  # 估值摘要（主 Agent 两阶段编排传入，含 score/final_level/summary/reason）
    pa_result: dict = {}  # 技术分析结果（含 direction / confidence）
    strategy_text: str = ""  # 加载的策略文本
    experience_refs: str = ""  # 经验库检索到的历史经验文本（读侧注入，空串兜底）
    backtest_mode: bool = False  # LLM 回测模式：禁用经验注入与决策落库/飞书推送
    trace_id: str = ""  # 决策幂等键：parse_node 一次生成，贯穿落库/报告/飞书
    structured_response: Any = None  # CompiledSubAgent 返回给父 Agent
    # ── Pa_Agent 两阶段编排新增字段 ──
    bars: list = []  # parse_node 存的 KlineBar 列表（newest-first，索引0=最新）
    features_text: str = ""  # pa_features 渲染的结构特征文本
    stage1_diagnosis: dict = {}  # MarketDiagnosis.model_dump()


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _load_txt(filename: str) -> str:
    """加载策略 .txt 文件内容。"""
    path = _PROMPT_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Strategy file not found: %s", path)
        return f"[{filename} not found]"


def _strip_code_fence(text: str) -> str:
    """剥离 LLM 输出中可能包裹 JSON 的 markdown 代码块围栏。

    参考 agents/value_assessment_agent.py 的 `_strip_code_fence` 写法。
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _kline_subset_json(market_data: dict) -> str:
    """取市场数据中给 LLM 的关键子集（kline_summary/trend/structure）序列化。"""
    subset = {
        k: market_data[k]
        for k in ("kline_summary", "trend", "structure")
        if market_data.get(k)
    }
    return json.dumps(subset, ensure_ascii=False, default=str)


def _coerce_diagnosis_json(parsed: dict) -> dict:
    """把 LLM 输出的 MarketDiagnosis JSON 规范化到 schema 兼容形态。

    常见偏差：support_levels/resistance_levels 输出为数值列表（应转字符串）、
    diagnosis_confidence 输出为浮点（应转整数）。schema 本身保持不变。
    """
    for key in ("support_levels", "resistance_levels"):
        vals = parsed.get(key)
        if isinstance(vals, list):
            parsed[key] = [str(v) for v in vals]
        elif not isinstance(vals, list):
            parsed[key] = []
    conf = parsed.get("diagnosis_confidence")
    if isinstance(conf, float):
        parsed["diagnosis_confidence"] = int(round(conf))
    return parsed


def _coerce_technical_json(parsed: dict, state: InvestmentState) -> dict:
    """把 LLM 输出的 TechnicalResult JSON 规范化到 schema 兼容形态。

    常见偏差：缺 stock_code/stock_name（程序侧已知，直接补全）、
    support/resistance 输出为列表（回退算法支撑阻力）、
    signals 输出为 dict（扁平化为字符串数组）。schema 本身保持不变。
    """
    parsed.setdefault("stock_code", _get_stock_code(state))
    parsed.setdefault("stock_name", _get_stock_name(state))

    # support/resistance 若输出为列表（常见误用），回退到算法计算的关键价位
    sr = (state.get("market_data") or {}).get("support_resistance") or {}
    for key, algo_key in (("support", "nearest_support"), ("resistance", "nearest_resistance")):
        val = parsed.get(key)
        if isinstance(val, list):
            parsed[key] = sr.get(algo_key)

    # signals 若输出为 dict（按方向分组），扁平化为字符串数组
    signals = parsed.get("signals")
    if isinstance(signals, dict):
        flat: list[str] = []
        for v in signals.values():
            if isinstance(v, list):
                flat.extend(str(x) for x in v)
            else:
                flat.append(str(v))
        parsed["signals"] = flat

    # estimated_win_rate 若输出为小数（如 0.62 表示 62%），转为 0-100 整数
    ew = parsed.get("estimated_win_rate")
    if isinstance(ew, float):
        parsed["estimated_win_rate"] = int(round(ew * 100)) if ew < 1 else int(round(ew))
    return parsed


def _route_strategy(market_data: dict) -> list[str]:
    """从算法市场数据路由到策略文件列表。"""
    files: list[str] = []

    # 通道/区间基础文件
    channel = market_data.get("structure", {}).get("channel_type", "trading_range")
    files.extend(_STRATEGY_FILES.get(channel, _STRATEGY_FILES["trading_range"]))

    # 宽窄通道补充
    atr_pct = market_data.get("volatility", {}).get("atr_pct", 0)
    if atr_pct < 1.0:
        files.append("文件13-窄通道与宽通道策略.txt")

    # 极速行情
    hl_trend = market_data.get("structure", {}).get("hl_trend_pct", 0)
    if abs(hl_trend) > 8:
        direction = "上涨" if hl_trend > 0 else "下跌"
        files.append(f"极速{direction}分析识别.txt")
        files.append(f"极速{direction}交易策略.txt")

    # 基础文件
    files.extend(_BASE_STRATEGY_FILES)

    # A 股专属（根据信号关键词匹配）
    signals = market_data.get("signals", [])
    for keyword, file in _A_SHORE_EXTRA.items():
        if any(keyword in s for s in signals):
            files.append(file)

    # 去重保序
    seen: set[str] = set()
    deduped: list[str] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


# ── 节点函数 ──────────────────────────────────────────────────────────────────


def _extract_user_input(state: InvestmentState) -> str:
    """从 messages 中提取用户输入，兼容 message 对象和 dict。

    langchain_core 的 HumanMessage 没有 ``role`` 属性（type='human'），
    因此不能依赖 ``getattr(m, 'role') == 'user'`` 判断。
    """
    msgs = state.get("messages", [])
    if not msgs:
        return ""

    for m in msgs:
        if isinstance(m, dict):
            if m.get("role") in ("user", "human"):
                return str(m.get("content", ""))
        else:
            mtype = getattr(m, "type", "")
            if mtype in ("human", "user"):
                return str(getattr(m, "content", "") or "")

    # 兜底：取最后一条消息的内容
    last = msgs[-1]
    if isinstance(last, dict):
        return str(last.get("content", ""))
    return str(getattr(last, "content", "") or "")


def parse_node(state: InvestmentState) -> dict:
    """解析输入 → 获取K线 → 算法计算市场数据。

    输入约定：用户消息可以是 JSON 字符串
    ``{"stock_identifier": "600519 贵州茅台", "va_summary": {"score": 80, ...}}``，
    先尝试 json.loads 解析，成功则取 stock_identifier 与 va_summary 存入 state；
    解析失败回退原文本提取股票（_extract_user_input / extract_stock_identifier）。
    """
    from agents.pa_agent import _compute_market_data
    from agents.stock_utils import extract_stock_identifier, get_kline_bars, resolve_symbol

    # 从 messages 提取用户输入
    user_msg = _extract_user_input(state).strip()
    if not user_msg:
        return {
            "stock_code": "",
            "stock_name": "",
            "structured_response": {"error": True, "error_message": "未识别到用户输入"},
        }

    # 尝试 JSON 解析（主 Agent 两阶段编排传入估值摘要；回测模式额外支持 as_of）
    va_summary: dict = {}
    as_of: str | None = None
    try:
        parsed = json.loads(user_msg)
        if not (isinstance(parsed, dict) and parsed.get("stock_identifier")):
            raise ValueError("非预期 JSON 结构")
        stock_identifier = str(parsed["stock_identifier"])
        va_summary = parsed.get("va_summary") or {}
        # 回测模式：历史时点（YYYY-MM-DD），仅取该日及之前的 K 线
        as_of = parsed.get("as_of") or None
        # 规范化标识：如 "600519 贵州茅台" → "600519"
        extracted = extract_stock_identifier(stock_identifier)
        if extracted:
            stock_identifier = extracted
    except (json.JSONDecodeError, ValueError):
        # 回退：从自然语言句子中提取股票标识
        stock_identifier = extract_stock_identifier(user_msg)

    code = resolve_symbol(stock_identifier) or stock_identifier
    if not code:
        return {
            "stock_code": "",
            "stock_name": "",
            "structured_response": {"error": True, "error_message": f"无法识别股票: {user_msg}"},
        }

    # 获取 K 线（回测模式按 as_of 截断，避免未来信息）
    bar_count = 100
    bars = get_kline_bars(code, "1d", bar_count, end_date=as_of)
    if not bars:
        return {
            "stock_code": code,
            "stock_name": "",
            "structured_response": {"error": True, "error_message": f"无法获取 {code} 的 K 线数据"},
        }

    # 算法计算
    market_data = _compute_market_data(bars)
    market_data["stock_code"] = code
    market_data["last_close"] = float(bars[0].close)

    # 获取股票名称
    from services.stock_metadata_service import search_stocks

    stock_name = stock_identifier
    try:
        matches = search_stocks(code, limit=1)
        if matches:
            stock_name = matches[0].get("stock_name", stock_identifier)
    except Exception:
        pass

    return {
        "stock_code": code,
        "stock_name": stock_name,
        "market_data": market_data,
        "va_summary": va_summary,
        "bars": bars,  # newest-first KlineBar 列表，供 features_node 渲染结构特征
        # 唯一一处生成决策幂等键：本次分析从此刻起 trace_id 固定，
        # 决策卡片落库（upsert）、报告文件命名、飞书推送均复用同一值
        "trace_id": generate_trace_id(),
    }


def _get_stock_code(state: InvestmentState) -> str:
    """安全获取股票代码，支持节点间状态传递。"""
    return state.get("stock_code", "") or ""


def _get_stock_name(state: InvestmentState) -> str:
    """安全获取股票名称。"""
    return state.get("stock_name", "") or ""


def _stream_stage_event(stage: str, status: str, **extra) -> None:
    """发送子 Agent 阶段自定义事件（langgraph custom stream update）。

    父级 `astream(stream_mode="custom", subgraphs=True)` 会收到
    ``{"event": "stage", "subagent": "technical_analysis", "stage": ..., "status": ...}``，
    供前端分阶段展示（技术分析中）。
    """
    from langgraph.config import get_stream_writer

    try:
        writer = get_stream_writer()
        writer({
            "event": "stage",
            "subagent": "technical_analysis",
            "stage": stage,
            "status": status,
            **extra,
        })
    except Exception:
        # 非流式调用（如 ainvoke）下 writer 不可用，静默忽略
        pass


def features_node(state: InvestmentState) -> dict:
    """程序结构特征：把 K 线 bars 渲染成 pa_features 特征文本（LLM 客观锚点）。

    惰性 import pa_features（从_bars 构造 KlineFrame → render_all_features 渲染）。
    无 bars 或渲染失败时返回空串并告警，绝不阻塞主流程。
    """
    bars = state.get("bars") or []
    if not bars:
        return {"features_text": ""}
    try:
        from pa_features import from_bars, render_all_features

        code = _get_stock_code(state)
        frame = from_bars(bars, symbol=code, timeframe="1d")
        text = render_all_features(frame)
        return {"features_text": text}
    except Exception as exc:
        logger.warning("pa_features 特征渲染失败: %s", exc)
        return {"features_text": ""}


def stage1_node(state: InvestmentState) -> dict:
    """Stage1 市场诊断（LLM）：程序结构特征 + K 线摘要 → MarketDiagnosis JSON。

    组装 system_prompt（人设 + 市场诊断框架 + 输出要求），user 消息为
    结构特征文本与 K 线关键子集；解析失败时兜底返回空诊断，不阻塞 Stage2。
    """
    code = _get_stock_code(state)
    name = _get_stock_name(state)
    _stream_stage_event("diagnosis", "started", stock_code=code, stock_name=name)

    features_text = state.get("features_text", "") or ""
    market_data = state.get("market_data") or {}
    kline_subset = _kline_subset_json(market_data)

    # system_prompt：人设与思维方式 + 市场诊断框架（stage1 参考 prompt） + 输出要求
    persona = _load_txt("提示词大纲_人设与思维方式.txt")
    framework = _load_txt("市场诊断框架.txt")
    system_prompt = (
        f"{persona}\n\n{framework}\n\n"
        "你是 A 股市场诊断专家。基于下方程序计算的结构特征（客观锚点）与 K 线摘要，\n"
        "先诊断市场当前状态，再输出 MarketDiagnosis JSON（字段：cycle_position / direction /\n"
        "market_phase / diagnosis_confidence / detected_patterns / key_signals /\n"
        "support_levels / resistance_levels / risk_warning）。不要输出任何其他内容。"
    )
    user_content = f"{features_text}\n\n## K线摘要\n{kline_subset}"

    try:
        response = get_llm().invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        text = response.content if hasattr(response, "content") else str(response)
        parsed = json.loads(_strip_code_fence(text))
        diagnosis = MarketDiagnosis.model_validate(_coerce_diagnosis_json(parsed))
    except Exception as exc:
        logger.warning("Stage1 市场诊断解析失败: %s", exc)
        diagnosis = MarketDiagnosis()

    _stream_stage_event(
        "diagnosis", "done",
        stock_code=code,
        cycle_position=diagnosis.cycle_position,
        direction=diagnosis.direction,
    )
    return {"stage1_diagnosis": diagnosis.model_dump()}


def _override_channel_files(files: list[str], direction: str) -> list[str]:
    """按 Stage1 诊断方向覆盖通道族文件选择（bullish→上涨通道 / bearish→下跌通道）。

    仅替换通道族文件（上涨/下跌通道、震荡区间），其余（极速、窄宽通道、
    基础文件、A 股专属）保持 _route_strategy 的原逻辑不变。
    """
    channel_files = (
        _STRATEGY_FILES["bull_channel"]
        if direction == "bullish"
        else _STRATEGY_FILES["bear_channel"]
    )
    all_channel = set(_STRATEGY_FILES["bull_channel"]) | set(
        _STRATEGY_FILES["bear_channel"]
    ) | set(_STRATEGY_FILES["trading_range"])
    kept = [f for f in files if f not in all_channel]
    return channel_files + kept


def load_strategies_node(state: InvestmentState) -> dict:
    """加载策略文本：基于 Stage1 诊断 + 算法市场数据路由选文件。

    兜底沿用 `_route_strategy(market_data)`；若 Stage1 诊断的 cycle_position
    明确（非 unknown）且 direction 明确（bullish/bearish），则按方向覆盖
    通道文件选择；其余（极速/窄宽通道/基础文件/A 股专属）逻辑保持不变。
    """
    files = _route_strategy(state.get("market_data", {}))

    # Stage1 诊断路由：direction 明确且 cycle_position 明确时按方向覆盖通道文件
    diagnosis = state.get("stage1_diagnosis") or {}
    cycle_position = diagnosis.get("cycle_position") or "unknown"
    direction = diagnosis.get("direction") or "neutral"
    if cycle_position != "unknown" and direction in ("bullish", "bearish"):
        files = _override_channel_files(files, direction)

    texts = [_load_txt(f) for f in files]
    return {"strategy_text": "\n\n---\n\n".join(texts)}


def inject_experience_node(state: InvestmentState) -> dict:
    """经验注入：从经验库检索相似历史案例写入 ``experience_refs``。

    读侧经验闭环——把系统复盘验证过的历史案例（含 MISS 失败反例）注入
    PA 分析上下文。任何失败仅告警并置空串，绝不阻塞主流程。
    """
    # 回测模式：历史时点之后积累的经验属于未来信息，禁用注入
    if state.get("backtest_mode"):
        return {"experience_refs": ""}

    from middleware.experience_injection import inject_experience

    try:
        code = _get_stock_code(state)
        name = _get_stock_name(state)
        market_data = state.get("market_data") or {}

        # user_intent：优先复用用户原始输入（parse_node 未落库原始字段时
        # 从 messages 提取；提取不到则空串）
        user_intent = _extract_user_input(state)

        # 结构信息（cycle_hint / channel_type）并入语义检索文本——
        # 不把 cycle_hint 作为结构化 market_cycle 硬 filter（不强依赖，
        # 避免 filter 过严导致检索为空），只增强 query_text 的语义相关性
        structure = market_data.get("structure") or {}
        context_hint = " ".join(
            x for x in [
                structure.get("cycle_hint", "") or "",
                structure.get("channel_type", "") or "",
            ] if x
        )
        if context_hint:
            user_intent = (
                f"{user_intent} {context_hint}".strip()
                if user_intent else context_hint
            )

        entities = {
            "stock_code": code,
            "stock_name": name,
        }

        ctx = inject_experience(entities, None, user_intent=user_intent)
        experience_refs = ctx.get("experience_refs", "") or ""
        if experience_refs:
            logger.info(
                "Experience injection: %d chars for %s %s",
                len(experience_refs), code, name,
            )
        return {"experience_refs": experience_refs}
    except Exception as exc:
        logger.warning("Experience injection failed: %s", exc)
        return {"experience_refs": ""}


def pa_node(state: InvestmentState) -> dict:
    """Stage2 交易决策（LLM）：Stage1 诊断 + 结构特征 + 策略 + 经验 → TechnicalResult。

    替换原单次分析：输入 = stage1_diagnosis + features_text + strategy_text +
    experience_refs + va_summary，输出含 order_type/entry_price 等扩展字段。
    """
    from agents.pa_agent import PA_SUBAGENT

    code = _get_stock_code(state)
    name = _get_stock_name(state)
    _stream_stage_event("technical", "started", stock_code=code, stock_name=name)

    # PA_SUBAGENT 基础 system_prompt + 两阶段编排（Stage2 交易决策）说明
    pa_prompt = PA_SUBAGENT["system_prompt"]
    stage2_prompt = (
        f"{pa_prompt}\n\n"
        "## 两阶段编排（Stage2 交易决策）\n"
        "你已获得 Stage1 市场诊断结果。请结合市场诊断、程序结构特征、交易策略库与\n"
        "历史经验，输出最终交易决策 TechnicalResult JSON（含 direction/confidence/\n"
        "market_cycle/patterns/support/resistance/signals/summary/risk_warnings，以及\n"
        "order_type/entry_price/take_profit_price/stop_loss_price/invalidation_price/\n"
        "estimated_win_rate/key_factors/watch_points）。不下单时 order_type=\"不下单\"\n"
        "且价格字段为 null。"
    )
    strategy = state.get("strategy_text", "")
    experience_refs = state.get("experience_refs", "") or ""
    stage1_diagnosis = state.get("stage1_diagnosis") or {}
    features_text = state.get("features_text", "") or ""
    kline_subset = _kline_subset_json(state.get("market_data") or {})

    # 历史经验参考小节（读侧经验注入）：仅在有注入内容时拼接
    exp_section = ""
    if experience_refs:
        exp_section = (
            "## 历史经验参考\n\n"
            "以下为系统复盘验证过的相似历史案例，供参考；失败反例请谨慎对待。\n\n"
            f"{experience_refs}\n\n"
        )

    full_prompt = (
        f"{stage2_prompt}\n\n"
        f"## 市场诊断（Stage1）\n{json.dumps(stage1_diagnosis, ensure_ascii=False, default=str)}\n\n"
        f"## 程序结构特征\n{features_text}\n\n"
        f"## 策略参考\n\n{strategy}\n\n"
        f"{exp_section}"
        f"## K线摘要\n{kline_subset}\n\n"
        "请输出 TechnicalResult JSON（含新字段），不要输出任何其他内容。\n"
        "格式注意：support/resistance 为单个数字或 null；signals 为字符串数组；"
        "必须包含 stock_code 与 stock_name（用题目给定的代码与名称）。"
    )

    response = get_llm().invoke([
        SystemMessage(content=full_prompt),
        HumanMessage(content=f"分析 {code} {name} 的技术面"),
    ])

    try:
        text = response.content if hasattr(response, "content") else str(response)
        parsed = json.loads(_strip_code_fence(text))
        pa = TechnicalResult.model_validate(_coerce_technical_json(parsed, state))
        _stream_stage_event("technical", "done", stock_code=code, direction=pa.direction)
        return {"pa_result": pa.model_dump()}
    except Exception as e:
        logger.warning("PA JSON parse failed: %s", e)
        _stream_stage_event("technical", "done", stock_code=code, direction="neutral")
        return {
            "pa_result": {
                "stock_code": code,
                "stock_name": name,
                "direction": "neutral",
                "confidence": 0.0,
                "summary": f"技术分析异常: {e}",
                "risk_warnings": ["LLM 输出解析失败"],
            }
        }


def _save_decision_card(state: InvestmentState) -> None:
    """将技术分析结果写入 decision_cards 表（全量决策事实层）。

    估值摘要取自 state["va_summary"]（由主 Agent 两阶段编排传入）。
    供后续复盘与经验提升使用；任何失败仅记录 warning，绝不向上抛异常。
    """
    from sqlalchemy.dialects.mysql import insert as mysql_insert
    from sqlalchemy.orm import Session

    from shared.config import _engine
    from shared.models import DecisionCard

    try:
        stock_code = state.get("stock_code", "") or ""
        stock_name = state.get("stock_name", "") or ""
        va_summary = state.get("va_summary") or {}
        pa_result = state.get("pa_result")
        market_data = state.get("market_data") or {}
        # 幂等键：优先用 parse_node 生成的稳定 trace_id，缺省才兜底生成
        trace_id = state.get("trace_id", "") or generate_trace_id()

        # action 映射：direction → buy→BUY / sell→SELL / 其他→HOLD
        action = "HOLD"
        if pa_result:
            direction = (pa_result or {}).get("direction", "")
            action = {"buy": "BUY", "sell": "SELL"}.get(direction, "HOLD")

        current_price = market_data.get("last_close")

        # 行业分类（DB 查询，异常或缺失填空字符串）
        sector = ""
        try:
            from services.industry_service import get_industry

            industry = get_industry(stock_code, auto_sync=False) or {}
            sector = industry.get("industryL1", "") or ""
        except Exception as exc:
            logger.warning("获取行业分类失败: %s", exc)

        market_cycle = (pa_result or {}).get("market_cycle", "") or ""
        patterns = (pa_result or {}).get("patterns") or [""]
        pattern = patterns[0] if patterns else ""

        # reasoning：估值摘要 + 技术分析摘要，用 "；" 分隔，缺则留空
        reasoning = ""
        parts = []
        if va_summary.get("summary"):
            parts.append(str(va_summary["summary"]))
        if pa_result and pa_result.get("summary"):
            parts.append(str(pa_result["summary"]))
        reasoning = "；".join(parts)

        # data_sources：数据源清单 + 估值/技术原始结果
        data_sources = {
            "sources": ["kline", "financial", "llm_valuation", "llm_technical"],
            "valuation": va_summary,
            "technical": pa_result,
        }

        session = Session(_engine)
        try:
            # 幂等 upsert：同 trace_id 重复执行收敛到同一行，不覆盖已有内容
            stmt = mysql_insert(DecisionCard).values(
                trace_id=trace_id,
                agent_id=settings.INVESTMENT_AGENT_ID,
                symbol=stock_code,
                stock_name=stock_name,
                action=action,
                current_price=current_price,
                stop_loss_price=(pa_result or {}).get("support"),
                take_profit_price=(pa_result or {}).get("resistance"),
                reasoning=reasoning,
                data_sources=data_sources,
                status="PENDING",
                market_cycle=market_cycle,
                sector=sector,
                pattern=pattern,
            ).on_duplicate_key_update(id=DecisionCard.id)
            session.execute(stmt)
            session.commit()
        finally:
            session.close()
    except Exception as exc:
        logger.warning("写入决策卡片失败: %s", exc)


# ── 飞书通知（决策推送）────────────────────────────────────────────────────────
def _build_decision_dict(state: InvestmentState) -> dict:
    """从 state 组装决策 dict（与 _save_decision_card 同源数据），用于飞书推送。

    字段与 decision_cards 表对齐：symbol/stock_name/action/current_price/
    stop_loss_price/take_profit_price/market_cycle/pattern/reasoning。
    review_outcome 为复盘回填字段，决策时通常为空。
    """
    stock_code = state.get("stock_code", "") or ""
    stock_name = state.get("stock_name", "") or ""
    va_summary = state.get("va_summary") or {}
    pa_result = state.get("pa_result") or {}
    market_data = state.get("market_data") or {}

    # action 映射：direction → buy→BUY / sell→SELL / 其他→HOLD
    action = "HOLD"
    direction = (pa_result or {}).get("direction", "")
    action = {"buy": "BUY", "sell": "SELL"}.get(direction, "HOLD")

    patterns = (pa_result or {}).get("patterns") or [""]
    pattern = patterns[0] if patterns else ""

    # reasoning：估值摘要 + 技术分析摘要，用 "；" 分隔，缺则留空
    reasoning = ""
    parts = []
    if va_summary.get("summary"):
        parts.append(str(va_summary["summary"]))
    if pa_result.get("summary"):
        parts.append(str(pa_result["summary"]))
    reasoning = "；".join(parts)

    return {
        "symbol": stock_code,
        "stock_name": stock_name,
        "action": action,
        "current_price": market_data.get("last_close"),
        "stop_loss_price": (pa_result or {}).get("support"),
        "take_profit_price": (pa_result or {}).get("resistance"),
        "market_cycle": (pa_result or {}).get("market_cycle", "") or "",
        "pattern": pattern,
        "reasoning": reasoning,
        "review_outcome": None,
    }


def _fetch_recent_bars(symbol: str, limit: int = 60) -> list[dict]:
    """从 market_data 表取最近 N 根已收盘日线（按时间升序），供 K 线绘图。

    parse_node 只把算法计算结果（market_data）存入 state，K 线原始 bars
    未落 state，因此推送时按 symbol 从库中补查。
    """
    from sqlalchemy import text

    from shared.config import _engine
    from sqlalchemy.orm import Session

    if not symbol:
        return []
    sql = (
        "SELECT trade_date, open, high, low, close, volume "
        "FROM market_data "
        "WHERE symbol = :sym AND LOWER(timeframe) = '1d' AND closed = TRUE "
        "ORDER BY trade_date DESC LIMIT :limit"
    )
    session = Session(_engine)
    try:
        rows = session.execute(text(sql), {"sym": symbol, "limit": limit}).fetchall()
    except Exception as exc:
        logger.warning("获取 %s 最近 K 线失败（跳过截图）: %s", symbol, exc)
        return []
    finally:
        session.close()

    bars: list[dict] = []
    for r in reversed(rows):  # DESC → ASC（旧 → 新），符合绘图输入约定
        td = r.trade_date
        if hasattr(td, "strftime"):
            td_str = td.strftime("%Y-%m-%d")
        else:
            td_str = str(td)
        bars.append({
            "trade_date": td_str,
            "open": float(r.open) if r.open is not None else 0.0,
            "high": float(r.high) if r.high is not None else 0.0,
            "low": float(r.low) if r.low is not None else 0.0,
            "close": float(r.close) if r.close is not None else 0.0,
            "volume": float(r.volume) if r.volume is not None else 0,
        })
    return bars


def _push_feishu_sync(state: InvestmentState) -> None:
    """同步推送飞书通知（无事件循环时的兜底路径）。

    决策文本（build_decision_card_text）+ K 线截图（render_kline_chart）组装
    交互卡片推送；截图或上传失败自动回退纯文本。未启用或失败仅告警，绝不抛异常。
    """
    # 幂等：同一 trace_id（同一决策）只推送一次，防 HITL resume / 重复委派多次发送
    trace_id = state.get("trace_id", "") or ""
    if _feishu_already_pushed(trace_id):
        logger.debug("飞书推送跳过（trace_id=%s 已推送过）", trace_id)
        return
    try:
        from services.feishu_notifier import (
            build_decision_card_text,
            get_feishu_notifier,
        )
        from services.kline_chart import render_kline_chart

        notifier = get_feishu_notifier()
        if not notifier.is_enabled():
            return
        decision = _build_decision_dict(state)
        text = build_decision_card_text(decision)

        # K 线截图：任何异常（无数据/绘图失败）回退文本推送，绝不中断
        image_bytes: bytes | None = None
        try:
            bars = _fetch_recent_bars(decision.get("symbol") or "")
            if bars:
                image_bytes = render_kline_chart(
                    bars,
                    symbol=decision.get("symbol") or "",
                    stock_name=decision.get("stock_name") or "",
                    support=decision.get("stop_loss_price"),
                    resistance=decision.get("take_profit_price"),
                )
        except Exception as exc:
            logger.warning("K 线截图生成失败，回退文本推送: %s", exc)
            image_bytes = None

        # 有截图 → 交互卡片；否则纯文本
        ok = notifier.send_decision_card(text, image_bytes)
        if ok and trace_id:
            _mark_feishu_pushed(trace_id)
    except Exception as exc:
        logger.warning("飞书通知同步推送失败: %s", exc)


async def _push_feishu_async(state: InvestmentState) -> None:
    """异步推送飞书通知（在线程池执行同步发送，避免阻塞事件循环）。"""
    try:
        await asyncio.to_thread(_push_feishu_sync, state)
    except Exception as exc:
        logger.warning("飞书通知异步推送失败: %s", exc)


def _notify_feishu(state: InvestmentState) -> None:
    """调度飞书决策通知：优先挂到事件循环异步执行，无事件循环则同步兜底。

    幂等：已推送过的 trace_id（同一决策）直接跳过，不创建多余任务。
    绝不阻塞 merge_node 返回，也绝不向上抛异常。
    """
    try:
        trace_id = state.get("trace_id", "") or ""
        if _feishu_already_pushed(trace_id):
            logger.debug("飞书推送跳过（trace_id=%s 已推送过）", trace_id)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(_push_feishu_async(state))
        else:
            _push_feishu_sync(state)
    except Exception as exc:
        logger.warning("飞书通知调度失败: %s", exc)


def merge_node(state: InvestmentState) -> dict:
    """合并结果，设置 structured_response 返回主 Agent。"""
    stock_code = _get_stock_code(state)
    stock_name = _get_stock_name(state)
    pa = state.get("pa_result") or {}

    # 构建技术分析结果（结构化输出 schema）
    result = TechnicalResult(
        stock_code=stock_code,
        stock_name=stock_name,
        direction=pa.get("direction", "neutral"),
        confidence=pa.get("confidence", 0.0),
        market_cycle=pa.get("market_cycle", ""),
        patterns=pa.get("patterns", []),
        support=pa.get("support"),
        resistance=pa.get("resistance"),
        signals=pa.get("signals", []),
        summary=pa.get("summary", ""),
        risk_warnings=pa.get("risk_warnings", []),
        trace_id=state.get("trace_id", ""),
        # Stage2 决策扩展字段（默认值向后兼容）
        order_type=pa.get("order_type", "不下单"),
        entry_price=pa.get("entry_price"),
        invalidation_price=pa.get("invalidation_price"),
        estimated_win_rate=pa.get("estimated_win_rate"),
        key_factors=pa.get("key_factors", []),
        watch_points=pa.get("watch_points", []),
    )

    # 决策落库（全量决策事实层，供复盘与经验提升）与飞书推送：
    # 回测模式旁路，避免污染线上决策事实层与触发真实推送
    if not state.get("backtest_mode"):
        _save_decision_card(state)
        _notify_feishu(state)

    # 完整结构化结果：TechnicalResult 基础上追加估值摘要/技术原始结果/融合决策，
    # 供主 Agent 汇总与 chat_service 组装前端决策卡片（value_assessment/pa_analysis/fusion）
    va_summary = state.get("va_summary") or {}
    pa_result = state.get("pa_result") or {}
    payload = result.model_dump()
    payload["va_summary"] = va_summary
    payload["pa_result"] = pa_result
    payload["fusion"] = _build_fusion(va_summary, pa_result)

    return {
        "messages": [AIMessage(content=f"{stock_code} {stock_name} 技术分析完成")],
        "structured_response": payload,
    }


def _build_fusion(va_summary: dict, pa_result: dict) -> dict:
    """组合估值摘要与技术分析结果，生成前端决策卡片的 fusion 字段。

    decision 与前端 DecisionCard 的 DECISION_STYLE key 对齐：
      不关注 / 买入 / 轻仓试水 / 等买点 / 减仓/警惕
    summary 拼接估值摘要 + 技术分析摘要（"；" 分隔，缺则留空）。
    """
    score = va_summary.get("final_score")
    if score is None:
        score = va_summary.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    blocked = bool(va_summary.get("blocked"))
    direction = (pa_result or {}).get("direction", "neutral")

    if blocked or (score_f is not None and score_f < 40):
        decision = "不关注"
    elif direction == "buy":
        decision = "买入" if (score_f is not None and score_f >= 60) else "轻仓试水"
    elif direction == "sell":
        decision = "减仓/警惕"
    else:
        decision = "等买点"

    parts: list[str] = []
    if va_summary.get("summary"):
        parts.append(str(va_summary["summary"]))
    if (pa_result or {}).get("summary"):
        parts.append(str(pa_result["summary"]))
    return {"decision": decision, "summary": "；".join(parts)}


# ── 构建 CompiledSubAgent ─────────────────────────────────────────────────────


def build_technical_analysis_agent() -> CompiledSubAgent:
    """构建并返回技术分析的 CompiledSubAgent。"""
    # Graph 定义（Pa_Agent 两阶段编排：市场诊断 → 交易决策）
    builder = StateGraph(InvestmentState)  # type: ignore

    builder.add_node("parse", parse_node)  # type: ignore
    builder.add_node("features", features_node)  # type: ignore
    builder.add_node("stage1", stage1_node)  # type: ignore
    builder.add_node("load_strategies", load_strategies_node)  # type: ignore
    builder.add_node("inject_experience", inject_experience_node)  # type: ignore
    builder.add_node("pa", pa_node)  # type: ignore  # stage2 决策
    builder.add_node("merge", merge_node)  # type: ignore

    builder.set_entry_point("parse")
    builder.add_edge("parse", "features")
    builder.add_edge("features", "stage1")
    builder.add_edge("stage1", "load_strategies")
    builder.add_edge("load_strategies", "inject_experience")
    builder.add_edge("inject_experience", "pa")
    builder.add_edge("pa", "merge")
    builder.add_edge("merge", END)

    graph = builder.compile()

    logger.info("Technical analysis CompiledSubAgent built")

    return CompiledSubAgent(
        name="technical_analysis",
        description="A 股技术分析：对指定股票做技术面分析，输出方向判断",
        runnable=graph,
    )
