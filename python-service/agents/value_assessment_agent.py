"""Value Assessment SubAgent — A 股价值评估子 Agent。

作为 DeepAgents SubAgent 注册，通过 `response_format` 返回结构化 JSON
给主 Agent，而非自由文本。
"""

from __future__ import annotations

from typing import Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

from shared.config import get_llm

# ──────────────────────────────────────────────────────────────────────────────
# 回测 as_of 上下文（模块级注入，避免污染工具 schema）
# ──────────────────────────────────────────────────────────────────────────────
# 在线模式下为 None（工具取最新数据）；LLM 回测时由回测引擎在调用前注入
# 历史时点 as_of，使 assess_value 拉取"当时已披露"的财务/估值数据。
_backtest_asof: str | None = None


def set_backtest_asof(as_of: str | None) -> None:
    """设置/清除回测时点上下文（as_of 为 None 时恢复在线模式）。"""
    global _backtest_asof
    _backtest_asof = as_of


def _get_backtest_asof() -> str | None:
    return _backtest_asof


# ──────────────────────────────────────────────────────────────────────────────
# Structured output schema
# ──────────────────────────────────────────────────────────────────────────────


class ValuationResult(BaseModel):
    """价值评估结构化结果——子 Agent 返回给主 Agent 的 Schema。"""

    stock_code: str = Field(description="股票代码")
    stock_name: str = Field(description="股票名称")
    blocked: bool = Field(description="是否被门控拦截（ST/新股/ROE<0 等）")
    block_reason: str = Field(default="", description="门控拦截原因")
    final_score: float = Field(ge=0, le=100, description="综合评分 0-100（可为小数）")
    final_level: str = Field(description="等级：优秀(good) / 良好(fair) / 一般(average) / 差(poor)")
    summary: str = Field(description="估值摘要，总结财务健康状况")
    recommend: bool = Field(description="是否推荐进入技术面分析")
    reason: str = Field(description="推荐/不推荐进入技术面分析的理由")
    warnings: list[str] = Field(default_factory=list, description="风险警告列表")
    industry: str = Field(default="", description="所属行业")
    pe_ratio: Optional[float] = Field(None, description="市盈率")
    pb_ratio: Optional[float] = Field(None, description="市净率")


# ──────────────────────────────────────────────────────────────────────────────
# Tool wrapper
# ──────────────────────────────────────────────────────────────────────────────


@tool
def assess_value(stock_identifier: str, stock_name: str = "") -> str:
    """执行 A 股价值评估（门控检查 + 规则评分），返回原始财务数据和评分结果。

    注意：此工具不执行 LLM 定性重评分——定性分析将在子 Agent 层完成。

    参数:
        stock_identifier: 股票代码（6位数字）或名称。
        stock_name: 股票名称（可选）。

    返回:
        包含财务摘要、行业、维度评分、规则总分和等级的 JSON 字符串。
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    # ── 1. 解析股票代码 ──────────────────────────────────────────────────────
    from agents.stock_utils import resolve_symbol
    code = (
        resolve_symbol(stock_identifier)
        if not (stock_identifier.isdigit() and len(stock_identifier) == 6)
        else stock_identifier
    )
    if not code:
        return json.dumps({
            "error": True,
            "error_message": f"无法识别股票代码: {stock_identifier}",
            "stock_code": stock_identifier,
            "stock_name": stock_name,
        }, ensure_ascii=False)

    # ── 2. 数据收集 ──────────────────────────────────────────────────────────
    from services.financial_data_service import get_financial_abstract, get_financial_report
    from services.industry_service import get_industry
    from services.valuation_service import get_valuation

    # 回测时点（LLM 回测注入的历史 as_of；在线为 None → 取最新）
    as_of = _get_backtest_asof()

    financial_abstract = None
    try:
        financial_abstract = get_financial_abstract(code, as_of=as_of)
    except Exception as e:
        logger.error("获取财务数据失败: %s, error=%s", code, e)

    industry_info = None
    try:
        industry_info = get_industry(code)
    except Exception as e:
        logger.error("获取行业数据失败: %s, error=%s", code, e)

    valuation_data = None
    try:
        valuation_data = get_valuation(code, as_of=as_of)
    except Exception as e:
        logger.error("获取估值数据失败: %s, error=%s", code, e)

    industry_name = None
    if industry_info:
        # 优先用 L2 粗分类（消费/医药/科技/金融/周期），使 scorer 行业调整生效
        industry_name = industry_info.get("industryL2") or industry_info.get("industryL1")
    if not stock_name and industry_info:
        stock_name = industry_info.get("stockName", stock_name)

    # 合并财务 + 估值数据（用于门控和评分）
    combined = dict(financial_abstract or {})
    if valuation_data:
        combined["pe_ttm"] = valuation_data.get("pe_ttm")
        combined["pb"] = valuation_data.get("pb")
        combined["close_price"] = valuation_data.get("close_price")
        combined["market_cap"] = valuation_data.get("market_cap")

    # ── 3. 门控检查 ──────────────────────────────────────────────────────────
    from agents.value_valuation.gates import  check_gates
    gate_result = check_gates(code, combined)
    warnings = list(gate_result.get("warnings", []))

    if gate_result.get("blocked", False):
        return json.dumps({
            "stock_code": code,
            "stock_name": stock_name,
            "blocked": True,
            "block_reason": gate_result.get("reason"),
            "warnings": warnings,
            "financial_abstract": financial_abstract,
            "industry": industry_name,
            "valuation_data": valuation_data,
        }, ensure_ascii=False)

    # ── 4. 规则评分 ──────────────────────────────────────────────────────────
    from agents.value_valuation.scorer import score
    score_result = score(combined, industry=industry_name)
    if not score_result:
        return json.dumps({
            "stock_code": code,
            "stock_name": stock_name,
            "blocked": False,
            "error": True,
            "error_message": "规则评分异常",
            "financial_abstract": financial_abstract,
            "industry": industry_name,
        }, ensure_ascii=False)

    rule_total = score_result.get("total_score", 0.0)
    rule_level = score_result.get("level", "差")
    dimensions = score_result.get("dimensions")

    # ── 5. 返回全量数据给子 Agent LLM ───────────────────────────────────────
    payload = {
        "stock_code": code,
        "stock_name": stock_name,
        "blocked": False,
        "block_reason": "",
        "rule_score": rule_total,
        "rule_level": rule_level,
        "dimensions": dimensions,
        "warnings": warnings,
        "industry": industry_name,
        "financial_abstract": financial_abstract,
        "valuation_data": valuation_data,
        "score_below_llm_threshold": rule_total < 40,
    }

    return json.dumps(payload, ensure_ascii=False, default=str)


# ──────────────────────────────────────────────────────────────────────────────
# LLM 回测单点调用
# ──────────────────────────────────────────────────────────────────────────────


def _strip_code_fence(text: str) -> str:
    """剥离 LLM 输出中可能包裹 JSON 的 markdown 代码块围栏。"""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _extract_valuation(result: Any, code: str, name: str) -> dict:
    """从 create_agent 的返回中解析 ValuationResult（兼容 JSON 字符串 / dict）。"""
    import json as _json

    messages = result.get("messages", [])
    for m in reversed(messages):
        content = getattr(m, "content", "")
        if isinstance(content, dict):
            return content
        if isinstance(content, str) and content.strip():
            try:
                parsed = _json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                continue
    return {
        "stock_code": code,
        "stock_name": name,
        "error": True,
        "error_message": "LLM 估值输出解析失败",
    }


async def run_value_assessment_llm(
    code: str, name: str = "", as_of: str | None = None
) -> dict:
    """LLM 回测单点：预执行 assess_value 工具（注入 as_of）+ LLM 定性分析。

    与真实 value_assessment 子 Agent 的差异仅在于：工具调用由回测引擎预执行
    （保证 as_of 可控、省去 LLM 反复调工具的轮次），LLM 只基于工具返回数据
    做定性分析并输出 ValuationResult。返回结构与子 Agent 的
    ``response_format=ValuationResult`` 一致（dict）。
    """
    import json as _json

    from langchain_core.messages import HumanMessage, SystemMessage

    from shared.config import get_llm

    set_backtest_asof(str(as_of) if as_of else None)
    try:
        tool_json = assess_value.func(code, name)
    finally:
        set_backtest_asof(None)

    if not tool_json:
        return {
            "stock_code": code,
            "stock_name": name,
            "error": True,
            "error_message": f"assess_value 无返回: {code}",
        }

    prompt = (
        VALUE_ASSESSMENT_SUBAGENT["system_prompt"]
        + f"\n\n## 回测提示\n本次分析时点为 {as_of}，`assess_value` 已基于该时点"
        "可用的财务/估值数据执行完毕。请直接基于下方工具返回的 JSON 做定性分析，"
        "并严格按照 ValuationResult 字段输出 JSON（字段：stock_code / stock_name / "
        "blocked / block_reason / final_score / final_level / summary / recommend / "
        "reason / warnings / industry / pe_ratio / pb_ratio），不要输出任何其他内容。"
    )
    response = get_llm().invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=tool_json),
    ])

    text = response.content if hasattr(response, "content") else str(response)
    try:
        parsed = _json.loads(_strip_code_fence(text))
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return _extract_valuation(
            {"messages": []}, code, name
        )


# ──────────────────────────────────────────────────────────────────────────────
# SubAgent definition
# ──────────────────────────────────────────────────────────────────────────────

VALUE_ASSESSMENT_SUBAGENT = {
    "name": "value_assessment",
    "description": "A 股价值评估：基于财务数据（ROE/PE/PB/负债率等）对股票进行估值打分，返回评分和等级",
    # 工具型结构化子 Agent：DeepSeek thinking 模式不支持 tool_choice，
    # 而 create_agent 对 response_format + tools 会强制 tool_choice → 必须关闭 thinking
    "model": get_llm(enable_thinking=False),
    "system_prompt": """你是一个 A 股价值评估专家。你调用 `assess_value` 工具获取门控结果和规则评分，然后结合原始财务数据做定性分析，最终输出结构化的 ValuationResult。

## 工作流程

1. 确认用户提供了股票代码或名称
2. 调用 `assess_value` 工具
3. 阅读返回的 JSON 中的 all 数据，进行定性分析
4. 基于评分与定性分析判断是否推荐进入技术面分析（recommend）
5. 输出 ValuationResult

## 定性分析要求（这是你的核心价值）

阅读 `financial_abstract`（财务摘要）、`dimensions`（各维度评分）和 `valuation_data`（估值数据），完成以下分析：

1. **数据质量判断**：财务数据是否完整、可信？如关键字段缺失，在 summary 中说明
2. **跨维度分析**：规则引擎独立计算各维度，但你能发现跨维度的矛盾信号（如营收增长但利润率下降，盈利好但现金流差）
3. **行业上下文**：结合 `industry` 判断评分是否合理（如周期股在低谷期 ROE 低是正常的）
4. **定性调整**：基于上述分析，在 summary 和 warnings 中给出比规则评分更细腻的判断

## 输出规则

- **final_score**: 直接使用 `rule_score`（规则评分），不要自行调整
- **final_level**: 根据 final_score 映射：>=80 优质(good), >=60 良好(fair), >=40 一般(average), <40 差(poor)
- **summary**: 2-3 句话，涵盖：财务健康状况、行业位置、你的定性判断
- **recommend**: 是否推荐进入技术面分析。评分较高（如 final_score >= 60）/ 基本面健康 / 值得继续看技术面 → true；被门控拦截（blocked=true）或基本面差（如 final_score < 40）→ false
- **reason**: 1-2 句话说明推荐/不推荐进入技术面分析的理由，需结合评分与定性判断，不要泛泛而谈
- **warnings**: 列出发现的异常信号（即使规则评分很高）
- 如果 `blocked=true`，在 summary 中说明拦截原因，final_score 填 0
- 如果 `score_below_llm_threshold=true`（规则评分 < 40），说明基本面较差，在 summary 中注明
- 如果 `error=true`，在 summary 中说明错误原因
- 如实反映工具返回的数据，不要编造""",
    "tools": [assess_value],
    "response_format": ValuationResult,
}
