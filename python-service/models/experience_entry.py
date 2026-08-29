"""Experience entry data model for the experience library (RAG-powered)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperienceEntry(BaseModel):
    """A single experience entry stored in the experience library.

    Fields prefixed with ``filter_`` serve as structured filter keys
    for the three-tier RAG retrieval strategy.
    """

    model_config = ConfigDict(extra="forbid")

    # ── Identity ──────────────────────────────────────────────────────────────
    id: str = Field(..., description="Unique identifier (e.g. exp_20260719_001)")
    timestamp: datetime = Field(..., description="When this entry was created")

    # ── Stock identity ────────────────────────────────────────────────────────
    stock_code: str = Field(..., description="6-digit A-share code")
    stock_name: str = Field("", description="Stock short name")

    # ── Structured filter keys (used in tier-1 retrieval) ────────────────────
    market_cycle: str = Field(
        "", description="Market cycle position, e.g. 震荡市中后期"
    )
    pattern: str = Field(
        "", description="Pattern/morphology, e.g. 缩量回踩60日均线"
    )
    sector: str = Field("", description="Industry sector, e.g. 白酒")

    # ── Analysis result ───────────────────────────────────────────────────────
    analysis_summary: dict = Field(
        default_factory=dict,
        description=(
            "Structured analysis summary. Expected keys: "
            "valuation, pa_conclusion, final_decision"
        ),
    )

    # ── Backtest outcome (optional, filled by batch backfill or manually) ────
    outcome: dict = Field(
        default_factory=dict,
        description="Backtest result, e.g. actual_trend, profit_ratio",
    )

    # ── Embedding & ranking ───────────────────────────────────────────────────
    embedding: Optional[list[float]] = Field(
        None, description="Semantic embedding vector (for Chroma backend)"
    )
    weight: float = Field(
        1.0, description="Time-decay weight. Starts at 1.0, decays over time."
    )

    # ── Tags for flexible filtering ───────────────────────────────────────────
    tags: list[str] = Field(
        default_factory=list, description="Custom tags for additional filtering"
    )

    # ── Helper: build a text blob for embedding ──────────────────────────────
    def to_embedding_text(self) -> str:
        """Return a flattened text representation for embedding generation."""
        parts = [
            f"股票: {self.stock_name}({self.stock_code})",
            f"市场周期: {self.market_cycle}",
            f"形态: {self.pattern}",
            f"板块: {self.sector}",
        ]
        summary = self.analysis_summary
        if summary.get("valuation"):
            parts.append(f"估值结论: {summary['valuation']}")
        if summary.get("pa_conclusion"):
            parts.append(f"技术分析结论: {summary['pa_conclusion']}")
        if summary.get("final_decision"):
            parts.append(f"最终决策: {summary['final_decision']}")
        if self.tags:
            parts.append(f"标签: {', '.join(self.tags)}")
        return "\n".join(parts)


class ExperienceQuery(BaseModel):
    """Query parameters for the experience library retrieval."""

    model_config = ConfigDict(extra="forbid")

    # Structured filter tier
    market_cycle: str = ""
    sector: str = ""
    tags: list[str] = Field(default_factory=list)

    # Semantic query (used for embedding similarity)
    query_text: str = Field(
        "", description="Natural-language description of the current scenario"
    )

    # Time decay: entries older than ``max_months`` get score=0
    max_months: int = Field(12, description="Max age in months for decay")

    # Result control
    top_k: int = Field(3, ge=1, le=20, description="Number of entries to return")
