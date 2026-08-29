"""
基于规则的价值估值评分引擎。

对个股的财务数据进行多维度打分，输出综合价值评分和等级。
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── 维度权重（基础） ──────────────────────────────────────────────
PROFIT_WEIGHT = 0.30       # 盈利能力
GROWTH_WEIGHT = 0.25       # 成长性
VAL_WEIGHT = 0.20          # 估值
HEALTH_WEIGHT = 0.15       # 财务健康
QUALITY_WEIGHT = 0.10      # 收益质量

# ── 行业调整映射 ──────────────────────────────────────────────────
# 格式: (profit_adj, growth_adj, val_adj, health_adj, quality_adj)
INDUSTRY_ADJUSTMENTS = {
    "消费":    (0.05, -0.05, 0.00, 0.00, 0.00),
    "医药":    (0.05, -0.05, 0.00, 0.00, 0.00),
    "科技":    (-0.05, 0.10, 0.00, 0.00, 0.00),
    "金融":    (0.05, -0.10, 0.00, 0.05, 0.00),
    "周期":    (0.00, -0.05, 0.10, 0.00, 0.00),
}

# ── 等级阈值 ──────────────────────────────────────────────────
LEVEL_THRESHOLDS = [
    (80, "优质"),
    (60, "良好"),
    (40, "一般"),
]


def _safe_float(value, default: float = None) -> Optional[float]:
    """安全地将值转为 float，None 或无效时返回 default。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score_roe(roe: Optional[float]) -> tuple:
    """ROE 评分。
    
    <5% → 0分, 5-10% → 40分, 10-15% → 60分, 15-20% → 80分, >20% → 100分
    """
    v = _safe_float(roe)
    if v is None:
        return 0, "ROE 数据缺失，得 0 分"
    if v < 5:
        return 0, f"ROE={v:.1f}% < 5%，得 0 分"
    if v < 10:
        return 40, f"ROE={v:.1f}% 在 5-10% 区间，得 40 分"
    if v < 15:
        return 60, f"ROE={v:.1f}% 在 10-15% 区间，得 60 分"
    if v < 20:
        return 80, f"ROE={v:.1f}% 在 15-20% 区间，得 80 分"
    return 100, f"ROE={v:.1f}% > 20%，得 100 分"


def _score_gross_margin(margin: Optional[float]) -> tuple:
    """毛利率评分。
    
    <20% → 0分, 20-40% → 40分, 40-60% → 70分, 60-80% → 85分, >80% → 100分
    """
    v = _safe_float(margin)
    if v is None:
        return 0, "毛利率数据缺失，得 0 分"
    if v < 20:
        return 0, f"毛利率={v:.1f}% < 20%，得 0 分"
    if v < 40:
        return 40, f"毛利率={v:.1f}% 在 20-40% 区间，得 40 分"
    if v < 60:
        return 70, f"毛利率={v:.1f}% 在 40-60% 区间，得 70 分"
    if v < 80:
        return 85, f"毛利率={v:.1f}% 在 60-80% 区间，得 85 分"
    return 100, f"毛利率={v:.1f}% > 80%，得 100 分"


def _score_net_margin(margin: Optional[float]) -> tuple:
    """净利率评分。
    
    <5% → 0分, 5-10% → 40分, 10-20% → 70分, >20% → 90分
    """
    v = _safe_float(margin)
    if v is None:
        return 0, "净利率数据缺失，得 0 分"
    if v < 5:
        return 0, f"净利率={v:.1f}% < 5%，得 0 分"
    if v < 10:
        return 40, f"净利率={v:.1f}% 在 5-10% 区间，得 40 分"
    if v < 20:
        return 70, f"净利率={v:.1f}% 在 10-20% 区间，得 70 分"
    return 90, f"净利率={v:.1f}% > 20%，得 90 分"


def _score_revenue_growth(growth: Optional[float]) -> tuple:
    """营收增速评分。
    
    <0% → 0分, 0-10% → 40分, 10-20% → 70分, 20-30% → 85分, >30% → 100分
    """
    v = _safe_float(growth)
    if v is None:
        return 0, "营收增速数据缺失，得 0 分"
    if v < 0:
        return 0, f"营收增速={v:.1f}% 为负，得 0 分"
    if v < 10:
        return 40, f"营收增速={v:.1f}% 在 0-10% 区间，得 40 分"
    if v < 20:
        return 70, f"营收增速={v:.1f}% 在 10-20% 区间，得 70 分"
    if v < 30:
        return 85, f"营收增速={v:.1f}% 在 20-30% 区间，得 85 分"
    return 100, f"营收增速={v:.1f}% > 30%，得 100 分"


def _score_profit_growth(growth: Optional[float]) -> tuple:
    """利润增速评分。
    
    <0% → 0分, 0-10% → 40分, 10-20% → 70分, 20-30% → 85分, >30% → 100分
    """
    v = _safe_float(growth)
    if v is None:
        return 0, "利润增速数据缺失，得 0 分"
    if v < 0:
        return 0, f"利润增速={v:.1f}% 为负，得 0 分"
    if v < 10:
        return 40, f"利润增速={v:.1f}% 在 0-10% 区间，得 40 分"
    if v < 20:
        return 70, f"利润增速={v:.1f}% 在 10-20% 区间，得 70 分"
    if v < 30:
        return 85, f"利润增速={v:.1f}% 在 20-30% 区间，得 85 分"
    return 100, f"利润增速={v:.1f}% > 30%，得 100 分"


def _score_pe(pe: Optional[float]) -> tuple:
    """PE 评分（越低越好）。
    
    >50 → 10分, 30-50 → 30分, 15-30 → 60分, 10-15 → 80分, <10 → 90分
    """
    v = _safe_float(pe)
    if v is None:
        return None, "PE 数据缺失"  # None 表示缺失，外部处理
    if v > 50:
        return 10, f"PE={v:.1f} > 50，估值较高，得 10 分"
    if v > 30:
        return 30, f"PE={v:.1f} 在 30-50 区间，得 30 分"
    if v > 15:
        return 60, f"PE={v:.1f} 在 15-30 区间，得 60 分"
    if v > 10:
        return 80, f"PE={v:.1f} 在 10-15 区间，得 80 分"
    return 90, f"PE={v:.1f} < 10，估值较低，得 90 分"


def _score_pb(pb: Optional[float]) -> tuple:
    """PB 评分（越低越好）。
    
    >10 → 10分, 5-10 → 30分, 3-5 → 50分, 1-3 → 80分, <1 → 90分
    """
    v = _safe_float(pb)
    if v is None:
        return None, "PB 数据缺失"  # None 表示缺失，外部处理
    if v > 10:
        return 10, f"PB={v:.1f} > 10，估值较高，得 10 分"
    if v > 5:
        return 30, f"PB={v:.1f} 在 5-10 区间，得 30 分"
    if v > 3:
        return 50, f"PB={v:.1f} 在 3-5 区间，得 50 分"
    if v > 1:
        return 80, f"PB={v:.1f} 在 1-3 区间，得 80 分"
    return 90, f"PB={v:.1f} < 1，估值较低，得 90 分"


def _score_debt_ratio(ratio: Optional[float]) -> tuple:
    """资产负债率评分。
    
    <30% → 90分, 30-50% → 70分, 50-70% → 40分, >70% → 10分
    """
    v = _safe_float(ratio)
    if v is None:
        return 0, "资产负债率数据缺失，得 0 分"
    if v < 30:
        return 90, f"资产负债率={v:.1f}% < 30%，负债水平低，得 90 分"
    if v < 50:
        return 70, f"资产负债率={v:.1f}% 在 30-50% 区间，得 70 分"
    if v < 70:
        return 40, f"资产负债率={v:.1f}% 在 50-70% 区间，得 40 分"
    return 10, f"资产负债率={v:.1f}% > 70%，负债水平高，得 10 分"


def _score_current_ratio(ratio: Optional[float]) -> tuple:
    """流动比率评分。
    
    >2.0 → 90分, 1.5-2.0 → 70分, 1.0-1.5 → 40分, <1.0 → 10分
    """
    v = _safe_float(ratio)
    if v is None:
        return 0, "流动比率数据缺失，得 0 分"
    if v > 2.0:
        return 90, f"流动比率={v:.2f} > 2.0，流动性好，得 90 分"
    if v > 1.5:
        return 70, f"流动比率={v:.2f} 在 1.5-2.0 区间，得 70 分"
    if v > 1.0:
        return 40, f"流动比率={v:.2f} 在 1.0-1.5 区间，得 40 分"
    return 10, f"流动比率={v:.2f} < 1.0，流动性差，得 10 分"


def _score_cash_ratio(ratio: Optional[float]) -> tuple:
    """经营现金流/净利润评分。
    
    >1.0 → 90分, 0.5-1.0 → 60分, <0.5 → 20分
    """
    v = _safe_float(ratio)
    if v is None:
        return 0, "经营现金流/净利润数据缺失，得 0 分"
    if v > 1.0:
        return 90, f"现金流/净利润={v:.2f} > 1.0，收益质量高，得 90 分"
    if v > 0.5:
        return 60, f"现金流/净利润={v:.2f} 在 0.5-1.0 区间，得 60 分"
    return 20, f"现金流/净利润={v:.2f} < 0.5，收益质量低，得 20 分"


def _compute_profitability(data: dict) -> dict:
    """计算盈利能力维度得分。"""
    roe_score, roe_detail = _score_roe(data.get("roe"))
    gm_score, gm_detail = _score_gross_margin(data.get("gross_margin"))
    nm_score, nm_detail = _score_net_margin(data.get("net_margin"))

    # 任一子项缺失不影响其他项计算
    score = roe_score * 0.4 + gm_score * 0.3 + nm_score * 0.3
    details = [roe_detail, gm_detail, nm_detail]

    return {"score": round(score, 2), "details": details}


def _compute_growth(data: dict) -> dict:
    """计算成长性维度得分。"""
    rev_score, rev_detail = _score_revenue_growth(data.get("revenue_growth"))
    prof_score, prof_detail = _score_profit_growth(data.get("profit_growth"))

    score = rev_score * 0.5 + prof_score * 0.5
    details = [rev_detail, prof_detail]

    return {"score": round(score, 2), "details": details}


def _compute_valuation(data: dict, val_weight: float, profit_weight: float) -> dict:
    """计算估值维度得分。
    
    如 PE 和 PB 均缺失，返回 score=None，将该维度权重转移给盈利能力。
    """
    pe_result = _score_pe(data.get("pe_ttm"))
    pb_result = _score_pb(data.get("pb"))

    pe_score, pe_detail = pe_result
    pb_score, pb_detail = pb_result

    # 收集有效得分
    scores = []
    details = []
    if pe_score is not None:
        scores.append(pe_score)
        details.append(pe_detail)
    else:
        details.append(pe_detail)
    if pb_score is not None:
        scores.append(pb_score)
        details.append(pb_detail)
    else:
        details.append(pb_detail)

    if not scores:
        # 两者均缺失，标记为缺失
        return {"score": None, "details": details, "weight_transferred": True}

    score = sum(scores) / len(scores)
    return {"score": round(score, 2), "details": details, "weight_transferred": False}


def _compute_health(data: dict) -> dict:
    """计算财务健康维度得分。"""
    debt_score, debt_detail = _score_debt_ratio(data.get("debt_ratio"))
    curr_score, curr_detail = _score_current_ratio(data.get("current_ratio"))

    score = debt_score * 0.6 + curr_score * 0.4
    details = [debt_detail, curr_detail]

    return {"score": round(score, 2), "details": details}


def _compute_quality(data: dict) -> dict:
    """计算收益质量维度得分。"""
    cash_score, cash_detail = _score_cash_ratio(data.get("cash_ratio"))
    return {"score": round(cash_score, 2), "details": [cash_detail]}


def _get_industry_adjustment(industry: Optional[str]) -> dict:
    """根据行业获取权重调整量。
    
    Args:
        industry: 行业（L1 分类）
        
    Returns:
        包含各维度调整量的 dict
    """
    if not industry:
        return {}

    # 模糊匹配：检查行业名是否包含调整表中任意key
    for key, (p_adj, g_adj, v_adj, h_adj, q_adj) in INDUSTRY_ADJUSTMENTS.items():
        if key in industry:
            logger.info("行业 '%s' 匹配调整规则 '%s'", industry, key)
            return {
                "profit_adj": p_adj,
                "growth_adj": g_adj,
                "val_adj": v_adj,
                "health_adj": h_adj,
                "quality_adj": q_adj,
            }

    return {}


def _get_level(total_score: float) -> str:
    """根据总分确定等级。"""
    for threshold, level in LEVEL_THRESHOLDS:
        if total_score >= threshold:
            return level
    return "差"


def score(financial_data: dict, industry: str = None) -> dict:
    """
    Score a stock based on its financial data.
    
    Args:
        financial_data: dict with financial metrics, expected to contain:
            - roe: float (ROE percentage)
            - gross_margin: float (毛利率 percentage)
            - net_margin: float (净利率 percentage)
            - revenue_growth: float (营收增速 percentage)
            - profit_growth: float (利润增速 percentage)
            - debt_ratio: float (资产负债率 percentage)
            - current_ratio: float (流动比率, dimensionless)
            - cash_ratio: float (经营现金流/净利润 ratio, dimensionless)
            - pe_ttm: float (PE TTM, from valuation)
            - pb: float (PB, from valuation)
            - report_date: str (latest report date, optional)
        industry: Industry classification (L1), e.g. "食品饮料", "银行", "科技"
            
    Returns:
        dict with:
            - total_score: float (0-100)
            - level: str ("优质" / "良好" / "一般" / "差")
            - dimensions: dict with sub-scores
            - details: list of str explanations
    """
    logger.info("开始评分，行业=%s", industry)

    # ── 计算各维度得分 ──────────────────────────────────────
    profit = _compute_profitability(financial_data)
    growth = _compute_growth(financial_data)
    health = _compute_health(financial_data)
    quality = _compute_quality(financial_data)

    # 估值（特殊处理缺失）
    adj = _get_industry_adjustment(industry)

    # 基础权重
    w_profit = PROFIT_WEIGHT
    w_growth = GROWTH_WEIGHT
    w_val = VAL_WEIGHT
    w_health = HEALTH_WEIGHT
    w_quality = QUALITY_WEIGHT

    # 行业调整
    w_profit += adj.get("profit_adj", 0.0)
    w_growth += adj.get("growth_adj", 0.0)
    w_val += adj.get("val_adj", 0.0)
    w_health += adj.get("health_adj", 0.0)
    w_quality += adj.get("quality_adj", 0.0)

    # 估值计算（含缺失处理）
    valuation = _compute_valuation(financial_data, w_val, w_profit)

    if valuation.get("weight_transferred"):
        # PE 和 PB 均缺失：估值权重转移给盈利能力
        logger.info("PE 和 PB 数据均缺失，估值权重 %.0f%% 转移至盈利能力", w_val * 100)
        w_profit += w_val
        w_val = 0.0
        val_score = 0.0
    else:
        val_score = valuation["score"]

    # 重新归一化权重（确保总和为 100%，考虑可能的行业调整后非整数）
    total_w = w_profit + w_growth + w_val + w_health + w_quality
    if total_w > 0:
        w_profit /= total_w
        w_growth /= total_w
        w_val /= total_w
        w_health /= total_w
        w_quality /= total_w

    # ── 计算总分 ──────────────────────────────────────────────
    total_score = (
        profit["score"] * w_profit
        + growth["score"] * w_growth
        + val_score * w_val
        + health["score"] * w_health
        + quality["score"] * w_quality
    )
    total_score = round(total_score, 2)

    level = _get_level(total_score)

    # ── 组织返回 ──────────────────────────────────────────────
    dimensions = {
        "盈利能力": {"score": profit["score"], "weight": round(w_profit * 100, 1)},
        "成长性": {"score": growth["score"], "weight": round(w_growth * 100, 1)},
        "估值": {"score": val_score, "weight": round(w_val * 100, 1)},
        "财务健康": {"score": health["score"], "weight": round(w_health * 100, 1)},
        "收益质量": {"score": quality["score"], "weight": round(w_quality * 100, 1)},
    }

    details = []
    details.extend(profit["details"])
    details.extend(growth["details"])
    details.extend(valuation["details"])
    details.extend(health["details"])
    details.extend(quality["details"])

    if adj:
        details.append(f"行业'{industry}'触发调整：{adj}")

    result = {
        "total_score": total_score,
        "level": level,
        "dimensions": dimensions,
        "details": details,
    }

    logger.info("评分完成：总分=%.2f，等级=%s", total_score, level)
    return result
