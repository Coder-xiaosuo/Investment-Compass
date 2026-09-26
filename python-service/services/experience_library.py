"""Experience Library — RAG-powered historical case retrieval system.

Architecture
------------
Three-tier retrieval strategy (as defined in spec):

1. **Structured filter**: Exact match on ``market_cycle`` and ``sector``
2. **Semantic ranking**: Cosine similarity on embedding vectors (Chroma)
3. **Time decay**: ``weight = 1 / (1 + 0.1 * months_elapsed)``

Usage
-----
::

    lib = get_experience_library()

    # Save an entry after analysis
    entry = ExperienceEntry(...)
    lib.save(entry)

    # Query relevant history before sub-agent analysis
    query = ExperienceQuery(market_cycle="震荡市中后期", sector="白酒", query_text="...")
    results = lib.query(query)
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from shared.config import settings

from models.experience_entry import ExperienceEntry, ExperienceQuery
from services.rag.vector_store import embed_texts, get_or_create_collection

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_EXPERIENCE_DIR = Path(settings.EXPERIENCE_LIBRARY_DIR)
_CHROMA_COLLECTION = "experience_library_zh"
_TIME_DECAY_FACTOR = 0.1  # weight = 1 / (1 + factor * months_elapsed)

# 中文语义嵌入与 Chroma 客户端由 services.rag.vector_store 统一提供
# （embed_texts / get_or_create_collection），此处只保留业务侧常量。


def _time_decay_weight(timestamp: datetime, now: datetime | None = None) -> float:
    """Calculate time-decay weight for an entry.

    ``weight = 1 / (1 + 0.1 * months_elapsed)``

    Returns a value in ``(0, 1]``.  Entries older than
    ``EXPERIENCE_MAX_MONTHS`` get ``0.0``.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Make timestamp timezone-aware for comparison
    ts = timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    days_elapsed = (now - ts).days
    # 时间戳晚于 now（时钟漂移 / 未来时间）时 timedelta.days 向下取整为负数，
    # 会把权重放大到 >1。按 0 处理，保证返回值恒在 (0, 1]。
    months_elapsed = max(0.0, days_elapsed / 30.0)

    if months_elapsed > settings.EXPERIENCE_MAX_MONTHS:
        return 0.0

    return 1.0 / (1.0 + _TIME_DECAY_FACTOR * months_elapsed)


def _compute_final_score(
    entry: ExperienceEntry,
    query: ExperienceQuery,
    semantic_score: float,
) -> float:
    """Combine structural match, semantic similarity, time decay, and validation weight.

    Final score = structural_hit * semantic_score * time_decay_weight * validation_weight

    * ``structural_hit`` = 1.0 if both market_cycle and sector match (at
      least empty-string equality), else 0.5 if one matches, else 0.0.
    * ``validation_weight`` = 复盘验证权重，根据 ``entry.outcome.verdict`` 决定：
      ``HIT`` → 1.0（命中先例保持原分）；``MISS`` → 0.5（反例降权）；
      其他（无 outcome / 老条目）→ 1.0。
    """
    # Tier 1: structural filter score
    cycle_match = (
        query.market_cycle
        and entry.market_cycle == query.market_cycle
    )
    sector_match = (
        query.sector
        and entry.sector == query.sector
    )

    if cycle_match and sector_match:
        structural_hit = 1.0
    elif cycle_match or sector_match:
        structural_hit = 0.5
    else:
        structural_hit = 0.0

    # Tier 3: time decay
    decay = _time_decay_weight(entry.timestamp)

    # Tier 4: 复盘验证权重（HIT 保持原分，MISS 反例降权至 0.5）
    verdict = entry.outcome.get("verdict")
    validation_weight = 0.5 if verdict == "MISS" else 1.0

    # Combined score
    return structural_hit * semantic_score * decay * validation_weight


# ──────────────────────────────────────────────────────────────────────────────
# Abstract backend
# ──────────────────────────────────────────────────────────────────────────────


class ExperienceBackend(ABC):
    """Abstract storage backend for the experience library."""

    @abstractmethod
    def save(self, entry: ExperienceEntry) -> str:
        """Persist *entry* and return its ID."""

    @abstractmethod
    def query(self, query: ExperienceQuery) -> list[ExperienceEntry]:
        """Retrieve entries matching *query*, sorted by relevance descending."""


# ──────────────────────────────────────────────────────────────────────────────
# Chroma backend
# ──────────────────────────────────────────────────────────────────────────────


class ChromaExperienceBackend(ExperienceBackend):
    """ChromaDB-based backend with metadata filtering and vector search."""

    def __init__(self, collection_name: str | None = None) -> None:
        self._collection_name = collection_name or _CHROMA_COLLECTION
        self._collection = self._init_collection()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, entry: ExperienceEntry) -> str:
        collection = self._collection
        doc_id = entry.id

        # Generate embedding text
        embedding_text = entry.to_embedding_text()

        metadata = {
            "market_cycle": entry.market_cycle or "",
            "sector": entry.sector or "",
            "stock_code": entry.stock_code,
            "stock_name": entry.stock_name,
            "timestamp": entry.timestamp.isoformat(),
            "pattern": entry.pattern or "",
            "tags": json.dumps(entry.tags, ensure_ascii=False),
            # 复盘结论（可能为空 dict，直接序列化；检索侧据此做反例降权）
            "outcome": json.dumps(entry.outcome, ensure_ascii=False),
        }

        kwargs: dict[str, Any] = {}
        embeddings = embed_texts([embedding_text])
        if embeddings:
            kwargs["embeddings"] = embeddings

        collection.upsert(
            ids=[doc_id],
            documents=[embedding_text],
            metadatas=[metadata],
            **kwargs,
        )
        logger.info(
            "ChromaExperienceBackend: saved entry %s (%s)",
            doc_id, entry.stock_name,
        )
        return doc_id

    def query(self, query: ExperienceQuery) -> list[ExperienceEntry]:
        collection = self._collection

        # Tier 1: build metadata filter（新版 chromadb 多条件需 $and 语法）
        where_filters: list[dict[str, Any]] = []
        if query.market_cycle:
            where_filters.append({"market_cycle": query.market_cycle})
        if query.sector:
            where_filters.append({"sector": query.sector})
        where_clause: dict[str, Any] | None = None
        if len(where_filters) == 1:
            where_clause = where_filters[0]
        elif len(where_filters) > 1:
            where_clause = {"$and": where_filters}

        # Pull a larger candidate set for post-filtering
        n_results = max(query.top_k * 3, 20)

        # 中文向量嵌入（不可用时回退 query_texts 走 Chroma 默认嵌入）
        query_embeddings = None
        if query.query_text:
            query_embeddings = embed_texts([query.query_text])

        def _run_query(*, filtered: bool):
            if query_embeddings:
                return collection.query(
                    query_embeddings=query_embeddings,
                    where=where_clause if filtered and where_clause else None,
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"],
                )
            return collection.query(
                query_texts=[query.query_text] if query.query_text else None,
                where=where_clause if filtered and where_clause else None,
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

        try:
            results = _run_query(filtered=True)
        except Exception:
            logger.warning(
                "ChromaExperienceBackend: query with structured filter failed, "
                "falling back to unfiltered query",
                exc_info=True,
            )
            results = _run_query(filtered=False)

        if not results or not results.get("ids") or not results["ids"][0]:
            logger.info("ChromaExperienceBackend: no results for query")
            return []

        entries: list[tuple[float, ExperienceEntry]] = []

        for i, doc_id in enumerate(results["ids"][0]):
            meta = (results["metadatas"][0][i] or {}) if results.get("metadatas") else {}

            # 读取复盘结论 outcome（老条目可能无此键；JSON 解析异常时兜底为空 dict）
            try:
                outcome = json.loads(meta.get("outcome", "{}"))
                if not isinstance(outcome, dict):
                    outcome = {}
            except (TypeError, ValueError):
                outcome = {}

            # Reconstruct ExperienceEntry from metadata
            entry = ExperienceEntry(
                id=doc_id,
                timestamp=datetime.fromisoformat(
                    meta.get("timestamp", datetime.now(timezone.utc).isoformat())
                ),
                stock_code=meta.get("stock_code", ""),
                stock_name=meta.get("stock_name", ""),
                market_cycle=meta.get("market_cycle", ""),
                sector=meta.get("sector", ""),
                pattern=meta.get("pattern", ""),
                tags=json.loads(meta.get("tags", "[]")),
                outcome=outcome,
            )

            # Tier 2: semantic distance → similarity score
            distances = results.get("distances")
            semantic_score = 1.0
            if distances and distances[0] and i < len(distances[0]):
                # Convert L2 distance to similarity (1 / (1 + dist))
                dist = distances[0][i]
                semantic_score = 1.0 / (1.0 + dist)

            final_score = _compute_final_score(entry, query, semantic_score)
            entries.append((final_score, entry))

        # Sort by final score descending, take top_k
        entries.sort(key=lambda t: t[0], reverse=True)
        return [e for _, e in entries[: query.top_k]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_collection(self):
        """Lazy-init Chroma client and collection（委托公共向量层）。"""
        return get_or_create_collection(self._collection_name, _EXPERIENCE_DIR)


# ──────────────────────────────────────────────────────────────────────────────
# Factory / singleton
# ──────────────────────────────────────────────────────────────────────────────

_backend: ExperienceBackend | None = None


def _create_backend() -> ExperienceBackend:
    """Create the default Chroma backend (singleton factory)."""
    return ChromaExperienceBackend()


def get_experience_library() -> ExperienceBackend:
    """Return the singleton experience library backend."""
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend


def reset_backend_for_testing() -> None:
    """Reset the singleton (used in unit tests)."""
    global _backend
    _backend = None
