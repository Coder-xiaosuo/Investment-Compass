"""投资风格画像数据模型 — 6 维度雷达图。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ── 6 维度常量 ───────────────────────────────────────────────────────────
DIMENSION_RISK_APPETITE = "risk_appetite"        # 风险偏好：保守-激进
DIMENSION_TIME_HORIZON = "time_horizon"          # 时间周期：短线-长线
DIMENSION_DECISION_BASIS = "decision_basis"      # 决策依据：技术-基本面
DIMENSION_TRADING_STYLE = "trading_style"         # 交易风格：左侧-右侧
DIMENSION_CONCENTRATION = "concentration"        # 仓位集中度：分散-集中
DIMENSION_EMOTION_PREF = "emotion_pref"          # 情绪偏好：防御-题材

DIMENSIONS = (
    DIMENSION_RISK_APPETITE,
    DIMENSION_TIME_HORIZON,
    DIMENSION_DECISION_BASIS,
    DIMENSION_TRADING_STYLE,
    DIMENSION_CONCENTRATION,
    DIMENSION_EMOTION_PREF,
)

class DimensionScore(BaseModel):
    """单个维度的画像状态。"""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    score: float = Field(0.0, ge=-1.0, le=1.0)
    evidence_count: int = 0
    matched_style_id: str = ""
    matched_style_label: str = ""
    updated_at: datetime = Field(default_factory=datetime.now)


class StyleProfile(BaseModel):
    """用户完整的六边形画像（6 维度）。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str = "default"
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    quiz_completed_count: int = 0
    stable: bool = False
    conversation_count: int = 0

    def get_score(self, dim: str) -> float:
        d = self.dimensions.get(dim)
        return d.score if d else 0.0


class QuizOption(BaseModel):
    """问卷选项。"""

    model_config = ConfigDict(extra="forbid")

    label: str               # "A" / "B" / "C"
    text: str                # 选项文案
    scores: dict[str, float] = Field(default_factory=dict)


class QuizQuestion(BaseModel):
    """问卷题目。"""

    model_config = ConfigDict(extra="forbid")

    id: str                  # "q01"
    scenario: str            # 题干
    options: list[QuizOption] = Field(default_factory=list)


class QuizSession(BaseModel):
    """一次问卷会话（含 2 题）。"""

    model_config = ConfigDict(extra="forbid")

    quiz_id: str             # "quiz_20260810_1"
    questions: list[QuizQuestion]
    user_id: str = "default"


class AnswerSubmission(BaseModel):
    """用户提交的作答。"""

    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    answers: list[dict] = Field(
        ...,
        description="作答列表，每项 {question_id, selected_label}",
    )


class RadarPoint(BaseModel):
    """雷达图单个数据点。"""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    label: str               # "风险偏好"
    axis_label: str          # "保守-激进"
    score: float             # [-1, +1] 标准化
    score_0_100: int          # [0, 100] 用于渲染雷达图
    matched_style: str       # "稳健型"
    evidence_count: int = 0  # 该维度累计信号数


class RadarProfile(BaseModel):
    """六边形雷达图完整数据（前端渲染用）。"""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    stable: bool
    quiz_completed_count: int
    conversation_count: int
    points: list[RadarPoint]
    summary: str             # "稳健型/中线趋势/混合派/左侧抄底/集中持有/价值型"
