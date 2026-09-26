"""Advisory CompiledSubAgent — 资讯问答子 Agent（Agentic RAG Demo）。

通过 CompiledSubAgent 机制注册到主 Agent。内部是一个 LangGraph 子图，
实现轻量 Agentic RAG 单轮循环（plan → retrieve → synthesize，信息不足可回
到 plan 一次，最多两轮）：

  1. plan_node:       意图识别 + 拆子问题（LLM）。识别是否需要检索
                       （概念解释不需要），并解析股票代码与查询意图
                       （stock_news / research_report / concept）
  2. retrieve_node:   并行检索新闻 + 研报（services.news_service），
                       概念解释则跳过检索
  3. synthesize_node: LLM 综合检索结果 + 用户问题 → AdvisoryResult（含引用）
  4. 条件边:          信息不足时回到 plan 一次（最多两轮）

能力边界：只做资讯问答（个股新闻、财联社快讯、券商研报的检索/摘要/对比）。
不碰行情/K线/买卖判断（那是 technical_analysis 的职责）。

数据来源：
  - services.news_service.list_news(symbol, source, days, limit, live_fetch)
  - services.news_service.list_research_reports(symbol, institute, rating, ...)
  - DB-first 查询：先查 MySQL，空则 live fetch AkShare 写入再查
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deepagents import CompiledSubAgent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import MessagesState
from pydantic import BaseModel, Field

from shared.config import get_llm

logger = logging.getLogger(__name__)


# ── 结构化输出 Schema ────────────────────────────────────────────────────────


class Citation(BaseModel):
    """单条引用来源。"""

    source: str = Field(description="数据源标识：em_news/cls_telegraph/em_global/research_reports")
    title: str = Field(description="新闻或研报标题")
    publish_time: str = Field(default="", description="发布时间（已格式化的字符串）")
    url: str = Field(default="", description="原文链接")


class AdvisoryResult(BaseModel):
    """资讯问答的结构化输出 — 子 Agent 返回给主 Agent 的 Schema。"""
    answer: str = Field(description="面向用户的资讯回答（含要点摘要与引用编号）")
    citations: list[Citation] = Field(default_factory=list, description="回答引用的来源列表（与 answer 中的编号对应）")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1：信息充足且一致→高；缺失或冲突→低")


# ── State ────────────────────────────────────────────────────────────────────


class AdvisoryState(MessagesState):
    """LangGraph 状态，必须包含 ``messages`` 键。"""

    user_query: str = ""  # 原始用户问题
    plan: dict = {}  # plan_node 输出：{stock_code, stock_name, intent, sub_queries, needs_retrieval}
    retrieved_news: list[dict] = []  # retrieve_node 取到的新闻条目
    retrieved_reports: list[dict] = []  # retrieve_node 取到的研报条目
    # 本地检索为空时的联网搜索降级结果（DeepSeek Responses web_search 黑盒返回）
    web_answer: str = ""  # 联网搜索生成的最终回答（存在则 synthesize 直接采用）
    web_sources: list[dict] = []  # 联网搜索模型 open_page 的 URL 列表 [{url}]
    advisory_result: dict = {}  # synthesize_node 输出（AdvisoryResult.model_dump()）
    loop_count: int = 0  # 已循环次数（条件边用来限制最多两轮）
    structured_response: Any = None  # CompiledSubAgent 返回给父 Agent


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _extract_user_input(state: AdvisoryState) -> str:
    """从 messages 中提取用户输入，兼容 message 对象和 dict。

    与 technical_analysis_agent._extract_user_input 同款写法。
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
    last = msgs[-1]
    if isinstance(last, dict):
        return str(last.get("content", ""))
    return str(getattr(last, "content", "") or "")


def _strip_code_fence(text: str) -> str:
    """剥离 LLM 输出中可能包裹 JSON 的 markdown 代码块围栏。"""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _stream_stage_event(stage: str, status: str, **extra) -> None:
    """发送子 Agent 阶段自定义事件（langgraph custom stream update）。

    父级 ``astream(stream_mode="custom", subgraphs=True)`` 会收到
    ``{"event": "stage", "subagent": "advisory", "stage": ..., "status": ...}``。
    """
    from langgraph.config import get_stream_writer

    try:
        writer = get_stream_writer()
        writer({
            "event": "stage",
            "subagent": "advisory",
            "stage": stage,
            "status": status,
            **extra,
        })
    except Exception:
        # 非流式调用（如 ainvoke）下 writer 不可用，静默忽略
        pass


def _web_search_fallback(user_query: str) -> dict | None:
    """DeepSeek 联网搜索降级：返回 {"answer", "citations"} 或 None（未启用/失败）。

    覆盖两类场景：
    - retrieve 阶段检索完全为空（retrieve_node 直接调用）
    - 检索非空但内容与问题无关，synthesize 综合后引用为空（本函数补充调用）

    黑盒限制：只能拿到最终回答 + 模型 open_page 的 URL。
    """
    from shared.config import settings

    if not settings.DEEPSEEK_SEARCH_ENABLED:
        logger.info("联网搜索降级未启用（DEEPSEEK_SEARCH_ENABLED=false）")
        return None
    try:
        from services.deepseek_search_client import deepseek_web_search

        search_res = deepseek_web_search(user_query)
        answer = search_res["answer"]
        sources = search_res["sources"]
        if sources:
            citations = [
                {
                    "source": "deepseek_web_search",
                    "title": f"联网搜索结果来源 {i + 1}",
                    "publish_time": "",
                    "url": s.get("url", ""),
                }
                for i, s in enumerate(sources[:8])
            ]
        else:
            citations = [{
                "source": "deepseek_web_search",
                "title": "基于 DeepSeek 联网搜索（未暴露具体页面）",
                "publish_time": "",
                "url": "",
            }]
        logger.info(
            "DeepSeek 联网搜索补充成功: answer_len=%d, sources=%d",
            len(answer), len(sources),
        )
        return {"answer": answer, "citations": citations}
    except Exception as exc:
        logger.warning("DeepSeek 联网搜索补充失败: %s", exc)
        return None


# ── 节点函数 ──────────────────────────────────────────────────────────────────


_PLAN_SYSTEM_PROMPT = """你是投资罗盘的资讯问答规划器。你的任务是把用户的资讯问题拆解为可执行的检索计划。

## 你的能力边界
- 可以检索：个股新闻、财联社快讯、东方财富全球资讯、券商研报
- 不可以：行情/K线/技术分析/买卖判断（这些由其他子 Agent 负责）

## 输出要求
输出严格的 JSON（不要任何其他文字、不要 markdown 代码块），schema：
{
  "stock_code": "6位股票代码或空字符串",
  "stock_name": "股票名称或空字符串",
  "intent": "stock_news | research_report | market_brief | concept",
  "sub_queries": ["检索关键词1", "检索关键词2"],
  "needs_retrieval": true/false,
  "reason": "简短说明计划依据"
}

## intent 判定
- stock_news: 用户问某只股票的近期新闻/事件/动态
- research_report: 用户问券商研报/机构评级/目标价/盈利预测
- market_brief: 用户问大盘/板块/全市场快讯（无具体个股）
- concept: 用户问概念解释（如"什么是市盈率"、"涨停板规则"）→ needs_retrieval=false

## 规则
- 用户提到具体股票名或6位代码时，填 stock_code 与 stock_name
- concept 类问题不检索，直接由 synthesize 节点用 LLM 知识回答
- sub_queries 最多 3 个，每个是一个简洁关键词
"""


def plan_node(state: AdvisoryState) -> dict:
    """意图识别 + 拆子问题（LLM）。

    用 LLM 解析用户问题，输出 plan JSON。解析失败时兜底：把整句当作
    sub_query，intent=market_brief，needs_retrieval=true，绝不阻塞主流程。
    """
    user_query = _extract_user_input(state).strip()
    if not user_query:
        return {
            "structured_response": AdvisoryResult(
                answer="未识别到您的问题，请告诉我您想了解哪只股票的资讯或哪个概念。",
                confidence=0.0,
            ).model_dump(),
        }

    _stream_stage_event("plan", "started")

    # 默认兜底计划（LLM 失败时用）
    fallback_plan = {
        "stock_code": "",
        "stock_name": "",
        "intent": "market_brief",
        "sub_queries": [user_query[:50]],
        "needs_retrieval": True,
        "reason": "LLM 解析失败，兜底按全市场快讯检索",
    }

    try:
        # 优先用规则补全股票代码（避免 LLM 偶发漏识别）
        from agents.stock_utils import extract_stock_identifier, resolve_symbol

        rule_identifier = extract_stock_identifier(user_query)
        rule_symbol = resolve_symbol(rule_identifier) if rule_identifier else None

        response = get_llm().invoke([
            SystemMessage(content=_PLAN_SYSTEM_PROMPT),
            HumanMessage(content=user_query),
        ])
        text = response.content if hasattr(response, "content") else str(response)
        parsed = json.loads(_strip_code_fence(text))
        if not isinstance(parsed, dict):
            raise ValueError("plan 非 dict")

        # 规则补全：LLM 漏识别股票时，用规则结果兜底
        if not parsed.get("stock_code") and rule_symbol:
            # 取 6 位数字代码
            digits = "".join(ch for ch in (rule_symbol or "") if ch.isdigit())
            if len(digits) >= 6:
                parsed["stock_code"] = digits[-6:]
                parsed.setdefault("stock_name", rule_identifier)
                if parsed.get("intent") in (None, "market_brief", "concept"):
                    parsed["intent"] = "stock_news"

        plan = parsed
    except Exception as exc:
        logger.warning("plan_node LLM 解析失败，使用兜底计划: %s", exc)
        plan = fallback_plan

    _stream_stage_event("plan", "done", intent=plan.get("intent", ""))
    return {
        "user_query": user_query,
        "plan": plan,
        "loop_count": (state.get("loop_count") or 0) + 1,
    }


def retrieve_node(state: AdvisoryState) -> dict:
    """并行检索新闻 + 研报（services.news_service）。

    - 概念解释（needs_retrieval=false）→ 跳过检索，直接进入 synthesize
    - stock_news / market_brief → 调 list_news
    - research_report → 调 list_research_reports
    - 同时要新闻和研报时（如 stock_news intent 下用户也问评级），两者都查
    - DB-first：list_news / list_research_reports 内部先查 DB，空则 live fetch

    任何失败仅告警并置空，绝不阻塞主流程。
    """
    plan = state.get("plan") or {}
    intent = plan.get("intent", "")
    needs_retrieval = bool(plan.get("needs_retrieval", True))
    stock_code = plan.get("stock_code", "") or ""

    if not needs_retrieval or intent == "concept":
        _stream_stage_event("retrieve", "done", reason="concept_skip")
        return {"retrieved_news": [], "retrieved_reports": []}

    _stream_stage_event("retrieve", "started", stock_code=stock_code, intent=intent)

    from services.news_service import list_news, list_research_reports

    news_items: list[dict] = []
    report_items: list[dict] = []

    # 新闻检索：
    # - stock_news + 有 stock_code：拉 60 天宽范围个股新闻 + 2 天市场快讯，
    #   再用 _rank_by_event_weight 按事件敏感度分级（财报2天/公告4天/舆情7天/战略60天）
    #   过滤+排序。避免固定 7 天窗口漏掉高价值事件或混入过期低权重事件。
    # - market_brief：只查全市场快讯（固定 7 天，不分级）。
    if intent == "stock_news" and stock_code:
        try:
            individual = list_news(
                symbol=stock_code, source="em_news",
                days=60, limit=100, live_fetch=True,
            )
            market = list_news(
                symbol=None, days=2, limit=15, live_fetch=False,
            )
            news_items = _rank_by_event_weight(individual + market, stock_code)
        except Exception as exc:
            logger.warning("retrieve_node list_news (stock_news) 失败: %s", exc)
    elif intent == "market_brief":
        try:
            news_items = list_news(
                symbol=None, days=7, limit=80, live_fetch=True,
            )
        except Exception as exc:
            logger.warning("retrieve_node list_news (market_brief) 失败: %s", exc)

    # 研报检索：必须有个股代码才查（研报按 symbol 索引，全市场研报语义弱）
    if intent in ("research_report", "stock_news") and stock_code:
        try:
            report_items = list_research_reports(
                symbol=stock_code,
                days=180,
                limit=30,
                live_fetch=True,
            )
        except Exception as exc:
            logger.warning("retrieve_node list_research_reports 失败: %s", exc)

    # 本地检索（DB/AkShare）为空且计划需要检索 → 降级 DeepSeek 原生联网搜索。
    # 黑盒限制：只能拿到最终回答 + 模型 open_page 的 URL；失败仅告警，不阻塞主流程。
    web_answer, web_sources = "", []
    if not news_items and not report_items and needs_retrieval:
        from shared.config import settings

        if settings.DEEPSEEK_SEARCH_ENABLED:
            _stream_stage_event("retrieve", "web_search_started")
            try:
                from services.deepseek_search_client import deepseek_web_search

                search_res = deepseek_web_search(state.get("user_query", ""))
                web_answer = search_res["answer"]
                web_sources = search_res["sources"]
                _stream_stage_event(
                    "retrieve", "web_search_done",
                    answer_len=len(web_answer), sources=len(web_sources),
                )
            except Exception as exc:
                logger.warning("retrieve_node 联网搜索降级失败: %s", exc)
                _stream_stage_event("retrieve", "web_search_failed")
        else:
            logger.info("联网搜索降级未启用（DEEPSEEK_SEARCH_ENABLED=false）")

    _stream_stage_event(
        "retrieve", "done",
        news_count=len(news_items),
        report_count=len(report_items),
        event_ranked=bool(stock_code and news_items),
        web_search=bool(web_answer),
    )
    return {
        "retrieved_news": news_items,
        "retrieved_reports": report_items,
        "web_answer": web_answer,
        "web_sources": web_sources,
    }


def _prioritize_symbol(items: list[dict], stock_code: str) -> list[dict]:
    """[已废弃] 被 _rank_by_event_weight 替代。保留仅为向后兼容。"""
    matched = [n for n in items if n.get("symbol") == stock_code]
    others = [n for n in items if n.get("symbol") != stock_code]
    return matched + others


# ── 事件类型权重与时间窗口（按价格敏感度分级） ──────────────────────────────
#
# 用户定义的"近期"召回权重：
#   - 最高权重：对价格敏感的事件（财报/业绩/并购）→ 1-2 交易日（老消息无价值）
#   - 次高权重：公告/龙虎榜 → 3-4 交易日
#   - 中等权重：舆情/研报/板块热度 → 1 周
#   - 低权重：公司战略/宏观/行业 → 1-2 月（变化慢，老消息仍有参考价值）
#
# 实现方式：拉 60 天个股新闻 → 按关键词分类事件类型 → 按对应窗口过滤 →
# 按权重排序（高权重在前，同权重内按时间倒序）→ 取前 N 条给 synthesize。
_EVENT_TIERS: list[dict] = [
    {
        "tier": "price_sensitive",
        "weight": 4,
        "days": 7,  # 放宽：原 2 天会漏掉分红/财报等持续性影响事件
        "keywords": [
            "财报", "业绩", "一季报", "半年报", "三季报", "年报", "预告", "快报",
            "并购", "重组", "借壳", "增发", "定增", "减持", "增持", "回购",
            "分红", "派息", "送转", "股权激励", "业绩说明会",
        ],
    },
    {
        "tier": "announcement",
        "weight": 3,
        "days": 10,  # 放宽：原 4 天会漏掉公告后续流程（如停复牌、股东大会）
        "keywords": [
            "公告", "龙虎榜", "异动", "停牌", "复牌", "股东大会", "担保",
            "质押", "解禁", "限售", "减持计划", "诉讼", "仲裁", "处罚",
        ],
    },
    {
        "tier": "sentiment",
        "weight": 2,
        "days": 7,  # 1 周
        "keywords": [
            "研报", "评级", "目标价", "机构", "上调", "下调", "买入", "增持",
            "板块", "概念", "资金流", "主力", "北向", "融资", "融券", "热度",
        ],
    },
    {
        "tier": "strategic",
        "weight": 1,
        "days": 60,  # 1-2 月（变化慢）
        "keywords": [
            "战略", "合作", "签约", "投产", "项目", "产能", "基地", "研发",
            "宏观", "政策", "行业", "景气", "周期", "规划", "愿景", "ESG",
        ],
    },
]
_TIER_DEFAULT = {"tier": "other", "weight": 0, "days": 7}


def _classify_event(text: str) -> dict:
    """按关键词匹配事件类型，返回 {tier, weight, days}。

    匹配规则：按权重从高到低扫描，命中第一个 tier 即返回（高权重优先）。
    text 为标题+内容拼接，匹配不到返回 other（weight=0, days=7 兜底）。
    """
    text = text or ""
    for tier in _EVENT_TIERS:
        if any(kw in text for kw in tier["keywords"]):
            return tier
    return _TIER_DEFAULT


def _rank_by_event_weight(items: list[dict], stock_code: str) -> list[dict]:
    """按事件权重分级 + 时间窗口过滤 + 排序。

    步骤：
      1. 个股新闻（symbol==stock_code）优先，全市场快讯降权
      2. 每条新闻按标题+内容分类事件类型（price_sensitive/announcement/...）
      3. 按事件类型的 days 过滤：publish_time >= now - days（超窗口的丢弃）
      4. 按 weight DESC + publish_time DESC 排序
      5. 限制返回条数（个股新闻 30 + 全市场快讯 10）

    全市场快讯（symbol=NULL）不参与事件分类（它们不是个股事件），
    统一按 2 天窗口 + 最低权重，仅作背景补充。
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    _CN_TZ = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz=_CN_TZ)

    individual: list[dict] = []
    market: list[dict] = []
    for n in items:
        if n.get("symbol") == stock_code:
            individual.append(n)
        else:
            market.append(n)

    # 个股新闻：去重 → 分类 → 按窗口过滤 → 按 weight DESC / time DESC 排序
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for n in individual:
        # 按 url 去重（url 为空则按 title 去重），DB 可能因多次同步产生重复
        key = n.get("url") or n.get("title") or ""
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        deduped.append(n)

    ranked: list[tuple[int, datetime, dict]] = []
    for n in deduped:
        text = f"{n.get('title', '')} {n.get('content', '')}"
        tier = _classify_event(text)
        # 按窗口过滤
        pub_str = n.get("publish_time") or ""
        try:
            pub = datetime.strptime(pub_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
        except (ValueError, TypeError):
            pub = now  # 解析失败不丢，按最新处理
        if (now - pub).days > tier["days"]:
            continue  # 超出事件窗口，丢弃
        ranked.append((tier["weight"], pub, n))
    # 排序：weight DESC, pub DESC（元组排序天然实现）
    ranked.sort(key=lambda x: (-x[0], -x[1].timestamp()))
    sorted_individual = [r[2] for r in ranked][:30]

    # 全市场快讯：仅保留 2 天内，按时间倒序取 10 条
    market_recent: list[dict] = []
    for n in market:
        pub_str = n.get("publish_time") or ""
        try:
            pub = datetime.strptime(pub_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
        except (ValueError, TypeError):
            continue
        if (now - pub).days <= 2:
            market_recent.append(n)
    market_recent.sort(
        key=lambda x: x.get("publish_time") or "",
        reverse=True,
    )
    sorted_market = market_recent[:10]

    return sorted_individual + sorted_market


_SYNTHESIZE_SYSTEM_PROMPT = """你是投资罗盘的资讯综合分析师。基于检索到的新闻与研报，回答用户的资讯问题。

## 你的能力边界
- 可以：摘要新闻、对比研报评级/盈利预测、解释检索到的事实
- 不可以：行情判断、K线分析、买卖建议（由其他子 Agent 负责）

## 输出要求
输出严格的 JSON（不要任何其他文字、不要 markdown 代码块），schema：
{
  "answer": "面向用户的中文回答，可在文中用 [1] [2] 标注引用",
  "citations": [
    {"source": "em_news|cls_telegraph|em_global|research_reports",
     "title": "标题",
     "publish_time": "已格式化的时间字符串",
     "url": "原文链接"}
  ],
  "confidence": 0.0 到 1.0 之间的浮点数
}

## 规则
- 回答中所有具体事实/数据/观点必须能对应到某条 citation
- 检索非空时，citations 必须非空，answer 中每个 [N] 标注都必须对应一条 citation，
  且每条 citation 的 url 字段不能为空（直接从检索结果的 url 取，不要编造）
- 检索为空且非概念解释时，confidence 不超过 0.3，并说明信息不足
- 引用按 answer 中出现的顺序排列，最多 8 条（避免冗长）
- 概念解释类（无检索）：直接用知识回答，citations 填一条
  {source: "llm_knowledge", title: "基于通用金融知识（无实时检索）", url: ""}，
  表明回答来源是模型知识而非实时数据
- 不要编造未在检索结果中出现的标题/时间/链接
"""


def synthesize_node(state: AdvisoryState) -> dict:
    """LLM 综合检索结果 + 用户问题 → AdvisoryResult（含引用）。

    解析失败时兜底返回低置信度文本结果，绝不向上抛异常。
    """
    user_query = state.get("user_query", "")
    plan = state.get("plan") or {}
    news = state.get("retrieved_news") or []
    reports = state.get("retrieved_reports") or []

    _stream_stage_event("synthesize", "started")

    # 联网搜索降级路径：本地检索为空时 retrieve_node 已拿到黑盒回答，
    # 直接采用（已基于实时联网信息生成），不再二次综合，避免重复成本。
    web_answer = (state.get("web_answer") or "").strip()
    if web_answer:
        web_sources = state.get("web_sources") or []
        citations: list[dict] = []
        if web_sources:
            citations = [
                {
                    "source": "deepseek_web_search",
                    "title": f"联网搜索结果来源 {i + 1}",
                    "publish_time": "",
                    "url": s.get("url", ""),
                }
                for i, s in enumerate(web_sources[:8])
            ]
        else:
            citations = [{
                "source": "deepseek_web_search",
                "title": "基于 DeepSeek 联网搜索（未暴露具体页面）",
                "publish_time": "",
                "url": "",
            }]
        result = AdvisoryResult(answer=web_answer, citations=citations, confidence=0.6)
        _stream_stage_event(
            "synthesize", "done",
            confidence=result.confidence, citations=len(result.citations),
            fallback="web_search",
        )
        return {"advisory_result": result.model_dump()}

    # 组装检索上下文（限制条数避免 prompt 过长）
    news_ctx = _format_news_for_prompt(news[:15])
    reports_ctx = _format_reports_for_prompt(reports[:10])
    plan_ctx = json.dumps(plan, ensure_ascii=False, default=str)

    user_content = (
        f"## 用户问题\n{user_query}\n\n"
        f"## 计划\n{plan_ctx}\n\n"
        f"## 检索到的新闻\n{news_ctx or '[无]'}\n\n"
        f"## 检索到的研报\n{reports_ctx or '[无]'}\n\n"
        "请基于上述信息输出 AdvisoryResult JSON。"
    )

    try:
        response = get_llm().invoke([
            SystemMessage(content=_SYNTHESIZE_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        text = response.content if hasattr(response, "content") else str(response)
        parsed = json.loads(_strip_code_fence(text))
        if not isinstance(parsed, dict):
            raise ValueError("AdvisoryResult 非 dict")

        # 字段兜底
        parsed.setdefault("answer", "")
        parsed.setdefault("citations", [])
        parsed.setdefault("confidence", 0.5)
        # citations 元素规范化
        norm_cites: list[dict] = []
        for c in parsed["citations"]:
            if isinstance(c, dict):
                norm_cites.append({
                    "source": str(c.get("source", "")),
                    "title": str(c.get("title", "")),
                    "publish_time": str(c.get("publish_time", "") or ""),
                    "url": str(c.get("url", "") or ""),
                })
        parsed["citations"] = norm_cites
        # confidence 强制 0-1
        try:
            conf = float(parsed["confidence"])
            parsed["confidence"] = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            parsed["confidence"] = 0.5

        # 来源校验：确保每次回答都附上信息来源
        has_retrieval = bool(news or reports)
        needs_retrieval = bool(plan.get("needs_retrieval", True))
        if not parsed["citations"] and needs_retrieval:
            # 引用为空（可能检索到内容但与问题无关，如 market_brief 混入不相关快讯）
            # → 降级联网搜索补充一轮，覆盖"本地检索非空但无有效内容"的场景。
            # retrieve 阶段已联网成功时（web_answer 非空）本分支不会到达。
            _stream_stage_event("retrieve", "web_search_started")
            supplement = _web_search_fallback(user_query)
            if supplement:
                parsed["answer"] = supplement["answer"]
                parsed["citations"] = supplement["citations"]
                parsed["confidence"] = 0.6
                _stream_stage_event(
                    "retrieve", "web_search_done",
                    answer_len=len(supplement["answer"]),
                    sources=len(supplement["citations"]),
                )
            else:
                _stream_stage_event("retrieve", "web_search_failed")
        if not parsed["citations"]:
            # 仍未拿到来源：按原逻辑降级 / 兜底
            if has_retrieval:
                # 检索非空但 LLM 没给 citations → 降级 + 提示
                parsed["confidence"] = min(parsed["confidence"], 0.3)
                if parsed["answer"]:
                    parsed["answer"] += "\n\n[注：本次未能附上信息来源链接，请谨慎参考]"
            else:
                # 概念解释类兜底：补一条 llm_knowledge 来源
                parsed["citations"] = [{
                    "source": "llm_knowledge",
                    "title": "基于通用金融知识（无实时检索）",
                    "publish_time": "",
                    "url": "",
                }]

        result = AdvisoryResult.model_validate(parsed)
        _stream_stage_event(
            "synthesize", "done",
            confidence=result.confidence,
            citations=len(result.citations),
        )
        return {"advisory_result": result.model_dump()}
    except Exception as exc:
        logger.warning("synthesize_node LLM 解析失败: %s", exc)
        # 兜底：把检索到的事实直接列出来
        fallback_answer = _build_fallback_answer(user_query, news, reports)
        result = AdvisoryResult(
            answer=fallback_answer,
            citations=[],
            confidence=0.2,
        )
        _stream_stage_event("synthesize", "done", confidence=0.2)
        return {"advisory_result": result.model_dump()}


def merge_node(state: AdvisoryState) -> dict:
    """合并结果，设置 structured_response 返回主 Agent。"""
    advisory = state.get("advisory_result") or {}
    result = AdvisoryResult(
        answer=advisory.get("answer", ""),
        citations=[Citation(**c) for c in advisory.get("citations", []) if isinstance(c, dict)],
        confidence=float(advisory.get("confidence", 0.0)),
    )

    answer_preview = result.answer[:80] + ("..." if len(result.answer) > 80 else "")
    return {
        "messages": [AIMessage(content=answer_preview)],
        "structured_response": result.model_dump(),
    }


# ── 条件边：信息不足时回到 plan（最多两轮） ──────────────────────────────────


def _route_after_synthesize(state: AdvisoryState) -> str:
    """综合完成后路由：信息不足且未达上限 → plan；否则 → merge。

    判定"信息不足"的启发式：
      1. needs_retrieval=true 但 news+reports 都为空 → 信息不足
      2. confidence < 0.3 且未达到 2 轮 → 信息不足
    """
    plan = state.get("plan") or {}
    if not plan.get("needs_retrieval", True):
        return "merge"

    # 联网搜索降级已给出回答（黑盒结果基于实时信息），直接收尾，不再回退重试
    if (state.get("web_answer") or "").strip():
        return "merge"

    loop_count = state.get("loop_count") or 0
    if loop_count >= 2:
        return "merge"

    news = state.get("retrieved_news") or []
    reports = state.get("retrieved_reports") or []
    advisory = state.get("advisory_result") or {}
    confidence = float(advisory.get("confidence", 0.0))

    if not news and not reports:
        # 检索完全为空，第二轮放宽为全市场快讯（去掉 symbol filter）
        if loop_count == 1 and plan.get("stock_code"):
            plan["stock_code"] = ""
            plan["intent"] = "market_brief"
            plan["sub_queries"] = [state.get("user_query", "")[:50]]
            plan["reason"] = "第二轮：个股检索为空，放宽为全市场快讯"
            state["plan"] = plan
        return "plan"
    if confidence < 0.3:
        return "plan"
    return "merge"


# ── 辅助：检索结果格式化 ─────────────────────────────────────────────────────


def _format_news_for_prompt(news: list[dict]) -> str:
    """把新闻列表格式化成 prompt 友好的文本（带编号，便于 LLM 引用）。"""
    if not news:
        return ""
    lines = []
    for i, n in enumerate(news, start=1):
        title = (n.get("title") or "").strip()
        src = n.get("source") or ""
        src_name = n.get("source_name") or ""
        pub = n.get("publish_time") or ""
        url = n.get("url") or ""
        content = (n.get("content") or "").strip()
        if content and len(content) > 200:
            content = content[:200] + "..."
        lines.append(
            f"[{i}] [{src}|{src_name}] {pub}\n"
            f"  标题: {title}\n"
            f"  摘要: {content}\n"
            f"  URL: {url}"
        )
    return "\n".join(lines)


def _format_reports_for_prompt(reports: list[dict]) -> str:
    """把研报列表格式化成 prompt 友好的文本。"""
    if not reports:
        return ""
    lines = []
    for i, r in enumerate(reports, start=1):
        title = (r.get("title") or "").strip()
        inst = r.get("institute") or ""
        rating = r.get("rating") or ""
        pub = r.get("publish_date") or ""
        url = r.get("pdf_url") or ""
        eps = r.get("eps_2026")
        pe = r.get("pe_2026")
        lines.append(
            f"[{i}] {pub} | {inst} | 评级:{rating} | EPS26:{eps} | PE26:{pe}\n"
            f"  标题: {title}\n"
            f"  URL: {url}"
        )
    return "\n".join(lines)


def _build_fallback_answer(user_query: str, news: list[dict], reports: list[dict]) -> str:
    """LLM 解析失败时的兜底回答：把检索到的事实直接列出来。"""
    parts = [f"针对您的问题「{user_query}」，整理检索到的事实如下："]
    if news:
        parts.append("\n【近期新闻】")
        for i, n in enumerate(news[:5], start=1):
            parts.append(f"{i}. [{n.get('publish_time', '')}] {n.get('title', '')}")
    if reports:
        parts.append("\n【近期研报】")
        for i, r in enumerate(reports[:5], start=1):
            parts.append(
                f"{i}. [{r.get('publish_date', '')}] {r.get('institute', '')} "
                f"| 评级:{r.get('rating', '')} | {r.get('title', '')}"
            )
    if not news and not reports:
        parts.append("\n未检索到相关信息，建议稍后重试或换一种问法。")
    parts.append("\n（注：本次为兜底回答，LLM 综合分析失败）")
    return "\n".join(parts)


# ── 构建 CompiledSubAgent ─────────────────────────────────────────────────────


def build_advisory_agent() -> CompiledSubAgent:
    """构建并返回资讯问答的 CompiledSubAgent。"""
    builder = StateGraph(AdvisoryState)  # type: ignore

    builder.add_node("plan", plan_node)  # type: ignore
    builder.add_node("retrieve", retrieve_node)  # type: ignore
    builder.add_node("synthesize", synthesize_node)  # type: ignore
    builder.add_node("merge", merge_node)  # type: ignore

    builder.set_entry_point("plan")
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "synthesize")
    builder.add_conditional_edges(
        "synthesize",
        _route_after_synthesize,
        {"plan": "plan", "merge": "merge"},
    )
    builder.add_edge("merge", END)

    graph = builder.compile()

    logger.info("Advisory CompiledSubAgent built")
    return CompiledSubAgent(
        name="advisory",
        description=(
            "资讯问答：检索个股新闻、财联社快讯、券商研报并综合回答。"
            "适用于「XX股票最近有什么新闻」「券商怎么看茅台」「什么是市盈率」等问题。"
            "不处理行情/K线/买卖判断。"
        ),
        runnable=graph,
    )
