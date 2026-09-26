"""
FinAgentOS — 全局配置
支持环境变量覆盖，适配 MySQL / PostgreSQL / SQLite
"""
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine

from shared.deepseek_llm import DeepSeekChatOpenAI

logger = logging.getLogger(__name__)

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root@localhost:3306/investment_compass?charset=utf8mb4"
    )
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "5"))
    DATABASE_POOL_RECYCLE: int = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    # 与 config/settings.json 的 provider.model 对齐（V4 才支持 thinking 思考模式）
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    # DeepSeek 思考模式（reasoning_content 思维链）：与 config/settings.json 的 provider.thinking 对齐
    DEEPSEEK_THINKING: bool = os.getenv("DEEPSEEK_THINKING", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    # 思考强度：none | low | high | max
    DEEPSEEK_REASONING_EFFORT: str = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")
    # DeepSeek 原生联网搜索（Responses API web_search 工具，仅 V4 模型支持）
    DEEPSEEK_SEARCH_MODEL: str = os.getenv("DEEPSEEK_SEARCH_MODEL", "deepseek-v4-flash")
    DEEPSEEK_SEARCH_ENABLED: bool = os.getenv(
        "DEEPSEEK_SEARCH_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
    QWEN_API_KEY: Optional[str] = os.getenv("QWEN_API_KEY")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    AKDATA_CACHE_DIR: str = os.getenv("AKDATA_CACHE_DIR", "data/market")
    # 交易日历（K线完整性审计基准，静态文件，随仓库 pin 住）
    TRADING_CALENDAR_PATH: str = os.getenv(
        "TRADING_CALENDAR_PATH", "data/trading_calendar.json"
    )
    # 覆盖率达标阈值（%）：>= 该值判 COMPLETE。放宽可容忍停牌造成的缺口
    KLINE_COVERAGE_COMPLETE_THRESHOLD: float = float(
        os.getenv("KLINE_COVERAGE_COMPLETE_THRESHOLD", "99.0")
    )
    # 回填意图回溯起点（审计的 expected_from 默认值）
    KLINE_BACKFILL_FROM: str = os.getenv("KLINE_BACKFILL_FROM", "2020-01-01")
    AGENT_PORT: int = int(os.getenv("AGENT_PORT", "8001"))
    AUDIT_PORT: int = int(os.getenv("AUDIT_PORT", "8088"))
    STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))
    DAILY_LOSS_LIMIT: float = float(os.getenv("DAILY_LOSS_LIMIT", "5.0"))
    MONTHLY_DRAWDOWN_LIMIT: float = float(os.getenv("MONTHLY_DRAWDOWN_LIMIT", "10.0"))
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Experience Library ────────────────────────────────────────────────────
    EXPERIENCE_LIBRARY_DIR: str = os.getenv(
        "EXPERIENCE_LIBRARY_DIR", "data/experience_library"
    )
    EXPERIENCE_MAX_MONTHS: int = int(
        os.getenv("EXPERIENCE_MAX_MONTHS", "12")
    )
    EXPERIENCE_FILL_STRATEGY: str = os.getenv(
        "EXPERIENCE_FILL_STRATEGY", "auto"
    )
    INVESTMENT_AGENT_ID: int = int(os.getenv("INVESTMENT_AGENT_ID", "1"))

    # ── 统一 RAG（策略知识库 / 资讯研报向量化召回） ────────────────────────────
    # 向量持久化目录（不含经验库，经验库沿用 EXPERIENCE_LIBRARY_DIR）
    RAG_VECTOR_DIR: str = os.getenv("RAG_VECTOR_DIR", "data/vector_store")
    RAG_STRATEGY_COLLECTION: str = os.getenv(
        "RAG_STRATEGY_COLLECTION", "strategy_kb"
    )
    RAG_INTEL_COLLECTION: str = os.getenv("RAG_INTEL_COLLECTION", "market_intel")
    # 资讯/研报索引保留天数（超期条目在索引时清理）
    RAG_INTEL_RETENTION_DAYS: int = int(
        os.getenv("RAG_INTEL_RETENTION_DAYS", "180")
    )


settings = Settings()

# ===== Task 5 热刷新：version 变化即重建 =====
_llm = None
_llm_no_thinking = None
_llm_version = -1
import threading as _llm_t_lock_mod
_llm_lock = _llm_t_lock_mod.RLock()


def get_llm(*, enable_thinking: bool | None = None) -> Any:
    """获取懒初始化的 LLM 实例（配置了 DeepSeek 的 ChatOpenAI）。

    Task 5 热刷新策略：
    - 每次调用读取 runtime_settings.version；若 version 比缓存时的 _llm_version 新 → 同时清空 _llm 与 _llm_no_thinking，重建
    - enable_thinking=True/False 独立两份缓存；version 变化时两份同时作废
    - DEEPSEEK_API_KEY 未配置时打 warning，不抛异常

    Args:
        enable_thinking: 是否启用 thinking 模式。
            None（默认）→ 跟随 settings.DEEPSEEK_THINKING；
            False → 强制关闭（工具型子 Agent 用，规避 thinking 与 tool_choice 冲突）。
    """
    global _llm, _llm_no_thinking, _llm_version
    api_key = settings.DEEPSEEK_API_KEY or ""
    model = settings.DEEPSEEK_MODEL
    base_url = settings.DEEPSEEK_BASE_URL if hasattr(settings, "DEEPSEEK_BASE_URL") else "https://api.deepseek.com"
    thinking_globals = settings.DEEPSEEK_THINKING
    reasoning_effort = settings.DEEPSEEK_REASONING_EFFORT

    cur_v = runtime_settings.version
    with _llm_lock:
        if cur_v != _llm_version:
            _llm = None
            _llm_no_thinking = None
            _llm_version = cur_v

        use_thinking = thinking_globals if enable_thinking is None else enable_thinking

        if not use_thinking:
            if _llm_no_thinking is None:
                _llm_no_thinking = DeepSeekChatOpenAI(
                    model=model,
                    api_key=api_key,
                    base_url=base_url.rstrip("/") + "/v1",
                    extra_body={"thinking": {"type": "disabled"}},
                )
                if not api_key:
                    logger.warning("DEEPSEEK_API_KEY 未设置，请在设置中配置后再调用 LLM")
            return _llm_no_thinking

        if _llm is None:
            extra_body = {}
            if thinking_globals:
                extra_body["thinking"] = {"type": "enabled"}
                extra_body["reasoning_effort"] = reasoning_effort
            _llm = DeepSeekChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url.rstrip("/") + "/v1",
                extra_body=extra_body,
            )
            if not api_key:
                logger.warning("DEEPSEEK_API_KEY 未设置，请在设置中配置后再调用 LLM")
        return _llm


def deepseek_model_kwargs() -> dict:
    """组装 DeepSeek 的 extra_body（thinking / reasoning_effort）。

    供主 Agent 直接构造模型时使用（agents/main_agent.py）。与 get_llm() 的
    extra_body 同口径，并经 runtime_settings 热刷新：前端「系统设置」改动后
    新建的 Agent 即生效。
    """
    if settings.DEEPSEEK_THINKING:
        return {
            "thinking": {"type": "enabled"},
            "reasoning_effort": settings.DEEPSEEK_REASONING_EFFORT,
        }
    return {"thinking": {"type": "disabled"}}


# ── Shared DB engine (used by services that need direct SQLAlchemy access) ──
_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_timeout=30,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 兼容层导出：RuntimeSettings 热更新配置 + 旧 DEEPSEEK_* 访问转发
# ═══════════════════════════════════════════════════════════════════════════════
from shared.runtime_settings import runtime_settings as _runtime_settings

_original_settings = settings


def _int_or_float_or_str(val):
    if val is None or val == "":
        return val
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    s = str(val)
    try:
        if "." in s:
            return float(s)
        return int(s)
    except (ValueError, TypeError):
        return s


class _LegacySettingsCompat:
    """兼容层：访问 settings.DEEPSEEK_* 自动转发到 runtime_settings"""

    def __getattr__(self, name):
        snap = _runtime_settings.snapshot_dict()
        prov = snap.get("provider", {})
        gen = snap.get("general", {})
        MAPPING = {
            "DEEPSEEK_API_KEY": (
                lambda: _runtime_settings.get_plaintext_api_key()
                or os.getenv("DEEPSEEK_API_KEY")
            ),
            "DEEPSEEK_MODEL": (
                lambda: prov.get(
                    "model", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
                )
            ),
            "DEEPSEEK_THINKING": (
                lambda: prov.get(
                    "thinking",
                    os.getenv("DEEPSEEK_THINKING", "true").lower()
                    in ("1", "true", "yes"),
                )
            ),
            "DEEPSEEK_REASONING_EFFORT": (
                lambda: prov.get(
                    "reasoning_effort",
                    os.getenv("DEEPSEEK_REASONING_EFFORT", "high"),
                )
            ),
            "DEEPSEEK_BASE_URL": (lambda: prov.get("base_url", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))),
            "DEEPSEEK_SEARCH_MODEL": (
                lambda: prov.get(
                    "search_model",
                    os.getenv("DEEPSEEK_SEARCH_MODEL", "deepseek-v4-flash"),
                )
            ),
            "DEEPSEEK_SEARCH_ENABLED": (
                lambda: prov.get(
                    "search_enabled",
                    os.getenv("DEEPSEEK_SEARCH_ENABLED", "true").lower()
                    in ("1", "true", "yes"),
                )
            ),
            "QWEN_API_KEY": (
                lambda: _runtime_settings.get_plaintext("qwen.api_key")
                or os.getenv("QWEN_API_KEY")
            ),
            "DATABASE_URL": (
                lambda: os.getenv(
                    "DATABASE_URL",
                    snap.get("database", {}).get(
                        "url",
                        "mysql+pymysql://root@localhost:3306/investment_compass?charset=utf8mb4",
                    ),
                )
            ),
        }
        for k in [
            "DATABASE_POOL_SIZE",
            "DATABASE_MAX_OVERFLOW",
            "DATABASE_POOL_RECYCLE",
            "EMBEDDING_MODEL",
            "AKDATA_CACHE_DIR",
            "AGENT_PORT",
            "AUDIT_PORT",
            "STREAMLIT_PORT",
            "DAILY_LOSS_LIMIT",
            "MONTHLY_DRAWDOWN_LIMIT",
            "REDIS_URL",
            "EXPERIENCE_LIBRARY_DIR",
            "EXPERIENCE_MAX_MONTHS",
            "EXPERIENCE_FILL_STRATEGY",
            "INVESTMENT_AGENT_ID",
        ]:
            if k not in MAPPING:
                MAPPING[k] = lambda k=k: _int_or_float_or_str(
                    os.getenv(k, getattr(_original_settings, k, ""))
                )
        if name in MAPPING:
            return MAPPING[name]()
        return getattr(_original_settings, name)


settings = _LegacySettingsCompat()
runtime_settings = _runtime_settings
