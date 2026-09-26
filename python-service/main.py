"""FinAgentOS - Python Service

Provides A-share market data endpoints for Java backend integration.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services import cancel_registry
from services import chat_service as chat_svc
from services import interpret_service as interpret_svc
from services import market_data_service as mds
from services import news_service as news_svc
from services import stock_metadata_service as sms
from services import sync_service as sync_svc
from shared.config import settings

logger = logging.getLogger(__name__)


# ── Pydantic models ───────────────────────────────────────────────────────────

class FetchMarketRequest(BaseModel):
    symbols: list[str]


class FetchMarketResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[dict[str, Any]] = None


class RealtimeQuote(BaseModel):
    symbol: str
    close: Optional[float] = None
    change_pct: Optional[float] = None
    pre_close: Optional[float] = None
    trade_date: Optional[str] = None


class RealtimeQuoteResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: list[RealtimeQuote] = []


class KlineBar(BaseModel):
    symbol: str
    trade_date: str
    timeframe: str = "1d"
    ts_open: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    pct_chg: Optional[float] = None
    closed: int = 1


class KlineHistoryResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[dict[str, Any]] = None


class StockSearchItem(BaseModel):
    symbol: str
    stockName: str


class StockSearchResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: list[StockSearchItem] = []


class InitMetadataResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[dict[str, Any]] = None


class BatchFetchRequest(BaseModel):
    symbols: list[str]
    start_year: int
    end_year: int
    concurrency: int = 2


class BatchFetchResult(BaseModel):
    symbol: str
    success: bool
    records_fetched: int = 0
    message: str = ""
    task_id: Optional[int] = None


class BatchFetchResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[list[BatchFetchResult]] = None


class SyncTaskStatus(BaseModel):
    id: int
    symbol: str
    start_year: int
    end_year: int
    current_year: int
    status: str
    records_fetched: int
    retry_count: int
    error_msg: Optional[str] = None
    updated_at: Optional[str] = None


class SyncTaskStatusResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: list[SyncTaskStatus] = []


# ── Chat models ───────────────────────────────────────────────────────────────────────────

class ConversationRequest(BaseModel):
    title: str = "新会话"
    kind: str = "analysis"  # analysis=主控台 / panel=右侧对话栏


class SendMessageRequest(BaseModel):
    content: str
    content_type: str = "text"


class ResumeRequest(BaseModel):
    decisions: list[dict[str, Any]]


class CreateAndSendRequest(BaseModel):
    content: str
    title: str | None = None


class BaseResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None


# ── Preferences models（偏好记忆问卷初始化）────────────────────────────────

class PreferencesInitRequest(BaseModel):
    risk_preference: str = ""
    decision_style: str = ""
    watch_sectors: str = ""
    watch_stocks: str = ""
    analysis_depth: str = ""


# ── App ────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services import quote_publisher
    from services import sync_scheduler

    logger.info("Python Service starting (DB: %s)", settings.DATABASE_URL)

    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.ping()
        quote_publisher.start(redis_client)
        logger.info("Quote publisher started with Redis: %s", settings.REDIS_URL)
    except Exception as exc:
        redis_client = None
        logger.warning("Redis unavailable, quote publisher disabled: %s", exc)

    # 软取消标记：Redis 可用时跨进程生效；降级：进程内标记
    cancel_registry.bind_redis(redis_client)
    logger.info("Soft-cancel marker backend: %s", cancel_registry.backend_name())

    # 进程内数据同步调度器（收盘行情 + 资讯定时同步）
    sync_scheduler.start_scheduler()

    # 后台预加载快捷入口数据（异步，不阻塞启动）
    from services.demo_quick_entry_service import preload
    preload()

    yield

    sync_scheduler.stop_scheduler()
    if redis_client is not None:
        quote_publisher.stop()
        await redis_client.close()
    logger.info("Python Service shutting down")


app = FastAPI(title="FinAgentOS - Python Service", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Global exception: %s", exc)
    return JSONResponse(content={"code": -1, "message": str(exc), "data": None}, status_code=500)


@app.get("/health")
async def health():
    return {"code": 0, "message": "success", "data": {"service": "finagentos-python", "status": "ok", "version": "0.2.0"}}


# ── /api/preferences — 偏好记忆（问卷初始化）───────────────────────────────

@app.get("/api/preferences")
def get_preferences() -> BaseResponse:
    """读取偏好记忆：是否已初始化 + 各分区内容（前端据此决定是否弹问卷）。"""
    from services.preferences_service import get_preferences

    return BaseResponse(data=get_preferences())


@app.post("/api/preferences")
def init_preferences(req: PreferencesInitRequest) -> BaseResponse:
    """新用户问卷提交：初始化偏好记忆文件（覆盖式，写前备份 .bak）。"""
    from services.preferences_service import init_preferences

    content = init_preferences(req.model_dump())
    if not content:
        return BaseResponse(code=1, message="偏好初始化失败", data=None)
    return BaseResponse(data={"path": "memories/preferences.md", "content": content})


# ── /api/style_profile — 投资风格画像（6 维度雷达图）───────────────────────

@app.get("/api/style_profile")
def get_style_profile(user_id: str = "default") -> BaseResponse:
    """读取用户投资风格画像雷达图数据。

    Returns:
        RadarProfile dict，含 6 个维度的 score/label + summary。
    """
    from services.style_profiler import get_radar_profile
    return BaseResponse(data=get_radar_profile(user_id).model_dump())


@app.post("/api/style_profile/cold_start")
def cold_start_style(
    payload: dict,
    user_id: str = "default",
) -> BaseResponse:
    """新用户冷启动问卷初始化画像（一次性 12 题）。

    Body:
        {"answers": [
            {"question_id": "q01", "selected_label": "A"},
            {"question_id": "q02", "selected_label": "C"},
            ... 共 12 题
        ]}
    """
    from services.style_profiler import cold_start_init
    answers = payload.get("answers", [])
    if not answers or len(answers) < 6:
        return BaseResponse(code=1, message="answers 至少 6 题", data=None)
    result = cold_start_init(user_id, answers)
    return BaseResponse(data=result)


@app.get("/api/style_profile/questions")
def list_cold_start_questions() -> BaseResponse:
    """列出冷启动题库全部 12 道问卷题（前端展示问卷用）。"""
    import json
    from pathlib import Path
    path = Path(__file__).parent / "data" / "investment_styles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return BaseResponse(data={
        "cold_start_questions": data.get("cold_start_questions", []),
        "dimensions": data["dimensions"],
    })


@app.post("/api/style_profile/observe")
def observe_feedback_endpoint(
    payload: dict,
    user_id: str = "default",
) -> BaseResponse:
    """手动触发一次 HITL 反馈观察（调试/前端预览用）。

    生产环境由 main_agent.astream_agent_events 在 resume 时自动调用，
    无需前端显式调用此接口。

    Body:
        {
            "thread_id": "xxx",
            "advice_summary": "估值分85, PE=50, 建议进入技术分析",
            "advice_data": {"valuation_score": 85, "pe": 50, "action": "进入技术分析"},
            "user_action": "respond",
            "user_response": "PE太高了，等回调再买"
        }
    """
    from services.style_profiler import observe_feedback
    result = observe_feedback(
        user_id=user_id,
        thread_id=payload.get("thread_id", ""),
        advice_summary=payload.get("advice_summary", ""),
        advice_data=payload.get("advice_data", {}),
        user_action=payload.get("user_action", ""),
        user_response=payload.get("user_response", ""),
    )
    return BaseResponse(data=result)


# ── /api/fetch/market — 增量更新 ───────────────────────────────────────────

@app.post("/api/fetch/market")
def fetch_market(req: FetchMarketRequest) -> FetchMarketResponse:
    """POST 方式触发增量更新（Java/Python SDK 友好）。"""
    total_records, errors = sync_svc.sync_symbols(req.symbols)
    if errors:
        return FetchMarketResponse(
            code=0,
            message=f"部分成功: {len(errors)} 个失败 - {'; '.join(errors)}",
            data={"records_fetched": total_records},
        )
    return FetchMarketResponse(code=0, message="同步完成", data={"records_fetched": total_records})


@app.get("/api/fetch/market")
def fetch_market_get(
    symbols: str = Query(..., description="逗号分隔的股票代码，如 000001,600519"),
) -> FetchMarketResponse:
    """GET 方式触发增量更新（Java cron 触发友好）。

    Java DataSyncJob 可通过以下方式调用：
        curl "http://python:8002/api/fetch/market?symbols=000001,600519"
    """
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return FetchMarketResponse(code=-1, message="symbols 参数为空", data=None)
    total_records, errors = sync_svc.sync_symbols(sym_list)
    if errors:
        return FetchMarketResponse(
            code=0,
            message=f"部分成功: {len(errors)} 个失败 - {'; '.join(errors)}",
            data={"records_fetched": total_records},
        )
    return FetchMarketResponse(code=0, message="同步完成", data={"records_fetched": total_records})


# ── /api/fetch/batch — 批量历史回填 ──────────────────────────────────────────

@app.post("/api/fetch/batch")
def batch_fetch(req: BatchFetchRequest) -> BatchFetchResponse:
    """批量拉取指定股票的历史日线数据（断点续传 + 并发）。"""
    try:
        results = sync_svc.batch_fetch(req.symbols, req.start_year, req.end_year, req.concurrency)
        success_count = sum(1 for r in results if r["success"])
        total_records = sum(r["records_fetched"] for r in results)
        results_models = [BatchFetchResult(**r) for r in results]
        return BatchFetchResponse(
            code=0,
            message=f"批量同步完成: {success_count}/{len(req.symbols)} 成功, 共 {total_records} 条记录",
            data=results_models,
        )
    except ValueError as exc:
        return BatchFetchResponse(code=-1, message=str(exc), data=None)


# ── /api/fetch/batch/status — 任务状态查询 ───────────────────────────────────

@app.get("/api/fetch/batch/status")
def batch_fetch_status(
    symbols: str = Query(..., description="逗号分隔的股票代码"),
    start_year: int = Query(..., description="起始年份"),
    end_year: int = Query(..., description="结束年份"),
) -> SyncTaskStatusResponse:
    """查询批量回填任务状态（断点续传进度）。"""
    from services import sync_task_service as sts

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return SyncTaskStatusResponse(data=[])
    tasks = sts.get_task_status_by_symbols(sym_list, start_year, end_year)
    return SyncTaskStatusResponse(data=[SyncTaskStatus(**t) for t in tasks])


# ── /api/fetch/sync — 单只股票按需同步 ──────────────────────────────────────

class SyncSymbolRequest(BaseModel):
    symbol: str


@app.post("/api/fetch/sync")
def sync_symbol(req: SyncSymbolRequest):
    """单只股票按需同步（后台线程执行，不阻塞响应）。
    
    前端查不到 K 线时调用此接口，后台启动 AkShare 拉取数据到 market_data 表。
    """
    try:
        import threading
        threading.Thread(target=sync_svc.sync_one_symbol, args=(req.symbol,), daemon=True).start()
        return {"code": 0, "message": f"正在同步 {req.symbol} 的数据"}
    except Exception as exc:
        logger.error("sync_symbol failed: %s", exc)
        return {"code": -1, "message": f"同步启动失败: {exc}"}


# ── /api/quote/realtime — 实时行情 ──────────────────────────────────────────

@app.get("/api/quote/realtime")
def realtime_quote(
    symbols: str = Query(..., description="逗号分隔的股票代码"),
) -> RealtimeQuoteResponse:
    """查询最新行情（从 market_data 表读取最新交易日数据）。"""
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return RealtimeQuoteResponse(data=[])
    quotes_dict = mds.get_realtime_quote(sym_list)
    quotes = [RealtimeQuote(**q) for q in quotes_dict]
    return RealtimeQuoteResponse(data=quotes)


# ── /api/kline/history — 历史 K 线 ───────────────────────────────────────────

@app.get("/api/kline/history")
def kline_history(
    symbol: str = Query(..., description="股票代码，如 000001"),
    timeframe: str = Query("1d", description="K线周期，支持 1d/D/d"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(120, ge=1, le=1000, description="返回条数上限，默认120，最大1000"),
) -> KlineHistoryResponse:
    """查询历史 K 线数据（从 market_data 表读取，按日期升序返回）。"""
    tf = "1d" if timeframe.lower() in ("d", "1d", "daily") else timeframe
    bars = mds.get_kline_history(symbol, tf, start_date, end_date, limit)
    return KlineHistoryResponse(data={"symbol": symbol, "timeframe": tf, "bars": bars})


# ── /api/stock/search — 股票搜索 ────────────────────────────────────────────

@app.get("/api/stock/search")
def stock_search(
    keyword: str = Query(..., description="搜索关键词（代码或名称）"),
    limit: int = Query(10, description="返回条数上限"),
) -> StockSearchResponse:
    """搜索 A 股股票（代码或名称匹配）。"""
    results = sms.search_stocks(keyword, limit)
    items = [StockSearchItem(**r) for r in results]
    return StockSearchResponse(data=items)


# ── /api/stock/init-metadata — 全量初始化品种列表 ────────────────────────────

@app.post("/api/stock/init-metadata")
def init_metadata() -> InitMetadataResponse:
    """全量同步 A 股品种列表到 stock_metadata 表。"""
    try:
        data = sms.init_metadata()
        if data.get("total_count", 0) == 0:
            return InitMetadataResponse(code=-1, message="AkShare 未返回数据", data=None)
        return InitMetadataResponse(
            code=0,
            message=f"同步完成: {data['success_count']} 成功, {data['failed_count']} 失败",
            data=data,
        )
    except Exception as exc:
        logger.error("init_metadata failed: %s", exc)
        return InitMetadataResponse(code=-1, message=f"同步失败: {exc}", data=None)


# ── /api/chat/* — 对话管理 ──────────────────────────────────────────────────


@app.post("/api/chat/conversation")
def create_conversation(req: ConversationRequest):
    try:
        conv = chat_svc.create_conversation(req.title, req.kind)
        return BaseResponse(data=conv)
    except Exception as exc:
        logger.error("create_conversation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/chat/conversation/list")
def list_conversations(
    status: int = Query(1, description="会话状态：1-活跃 2-归档"),
    kind: str | None = Query(None, description="会话类型：analysis-主控台 / panel-右侧对话；不传=全部"),
):
    try:
        convs = chat_svc.list_conversations(status, kind)
        return BaseResponse(data=convs)
    except Exception as exc:
        logger.error("list_conversations failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.put("/api/chat/conversation/{conv_id}/title")
def rename_conversation(conv_id: int, req: ConversationRequest):
    """重命名会话标题（右侧对话栏顶部 ✎ 编辑；主控台侧边栏亦可复用）。"""
    try:
        success = chat_svc.rename_conversation(conv_id, req.title)
        if not success:
            return BaseResponse(code=404, message="会话不存在", data=None)
        return BaseResponse(data={"id": conv_id, "title": req.title})
    except Exception as exc:
        logger.error("rename_conversation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/chat/conversation/{conv_id}")
def get_conversation(conv_id: int):
    try:
        conv = chat_svc.get_conversation(conv_id)
        if conv is None:
            return BaseResponse(code=404, message="会话不存在", data=None)
        return BaseResponse(data=conv)
    except Exception as exc:
        logger.error("get_conversation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.put("/api/chat/conversation/{conv_id}/archive")
def archive_conversation(conv_id: int):
    try:
        success = chat_svc.archive_conversation(conv_id)
        if not success:
            return BaseResponse(code=404, message="会话不存在", data=None)
        return BaseResponse(data={"id": conv_id, "status": 2})
    except Exception as exc:
        logger.error("archive_conversation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.delete("/api/chat/conversation/{conv_id}")
def delete_conversation(conv_id: int):
    try:
        success = chat_svc.delete_conversation(conv_id)
        if not success:
            return BaseResponse(code=404, message="会话不存在", data=None)
        return BaseResponse(data={"id": conv_id, "deleted": True})
    except Exception as exc:
        logger.error("delete_conversation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/chat/conversation/{conv_id}/message")
def get_messages(
    conv_id: int,
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(30, ge=1, le=100, description="每页条数"),
):
    try:
        result = chat_svc.get_messages(conv_id, page, pageSize)
        return BaseResponse(data=result)
    except Exception as exc:
        logger.error("get_messages failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.post("/api/chat/conversation/{conv_id}/message")
def send_message(conv_id: int, req: SendMessageRequest):
    try:
        result = chat_svc.send_message(conv_id, req.content, req.content_type)
        return BaseResponse(data=result)
    except Exception as exc:
        logger.error("send_message failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.post("/api/chat/conversation/{conv_id}/message/stream")
async def stream_message(conv_id: int, req: SendMessageRequest):
    """流式对话：SSE 逐块输出主 Agent 回复（chunkSize=8, 15ms interval）。"""
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        chat_svc.stream_agent_reply(conv_id, req.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/conversation/{conv_id}/interrupt")
async def interrupt_stream(conv_id: int):
    """软取消该会话正在进行的流。

    与前端 AbortController 的「硬中断」严格区分：
    - 软取消：不断开连接，只写一个协作标记，Agent 在下一个安全检查点主动退出，
      已产出内容照常落库，写操作不会被截成两半；旧流随后以 done 正常结束。
    - 硬中断：前端直接 abort，服务端在 CancelledError 的 finally 中兜底落库。
    """
    try:
        await cancel_registry.mark(conv_id)
        return BaseResponse(data={"conversation_id": conv_id, "soft_cancelled": True})
    except Exception as exc:
        logger.error("interrupt_stream failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.post("/api/chat/{conversation_id}/resume")
async def resume_message(conversation_id: int, req: ResumeRequest):
    """恢复 HITL 中断的分析流：提交用户决策后 SSE 续流。

    body: {"decisions": [{"type": "approve"|"reject"|"respond", ...}]}
    事件格式与 /message/stream 一致（chunk / stage / interrupt / done 等）。
    """
    from fastapi.responses import StreamingResponse

    return StreamingResponse(
        chat_svc.resume_agent_reply(conversation_id, req.decisions),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/message")
def create_and_send(req: CreateAndSendRequest):
    try:
        result = chat_svc.create_and_send(req.content, req.title)
        return BaseResponse(data=result)
    except Exception as exc:
        logger.error("create_and_send failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


# ====================================================================
#  看板 AI 解读路由（ai_reader 卡片即时解读）
# ====================================================================


class InterpretRequest(BaseModel):
    """卡片 AI 解读请求：symbol + card_type。"""

    symbol: str
    card_type: str  # technical / fundflow / chip / target


@app.post("/api/analysis/interpret")
async def interpret_card(req: InterpretRequest):
    """运行 ai_reader 子 Agent 对指定股票的某张看板卡片做即时解读。

    body: {"symbol": "600519", "card_type": "technical"}
    返回 CardInterpretation（summary / key_points / risks）。
    """
    try:
        data = await interpret_svc.interpret_card(req.symbol.strip(), req.card_type)
        return BaseResponse(data=data)
    except Exception as exc:
        logger.error("interpret_card failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


# ====================================================================
#  资讯与研报路由
# ====================================================================


class NewsSyncRequest(BaseModel):
    """手动同步请求：指定要同步个股新闻的股票列表（可为空）。"""
    symbols: list[str] = []


@app.get("/api/news/list")
def news_list(
    symbol: Optional[str] = Query(None, description="股票代码过滤，如 600519；不填=返回全市场资讯+快讯"),
    source: Optional[str] = Query(None, description="em_news / cls_telegraph / em_global；不填=全部"),
    days: int = Query(7, ge=1, le=365, description="只查最近 N 天"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
):
    """查询新闻/快讯列表。

    DB 数据不足时自动触发 AkShare 实时拉取并入库后再返回。
    """
    try:
        rows = news_svc.list_news(symbol=symbol, source=source, days=days, limit=limit)
        return BaseResponse(data={"total": len(rows), "items": rows})
    except Exception as exc:
        logger.error("news_list failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/research/list")
def research_list(
    symbol: Optional[str] = Query(None, description="股票代码过滤"),
    institute: Optional[str] = Query(None, description="机构名过滤，模糊匹配，如 '国信' / '中信'"),
    rating: Optional[str] = Query(None, description="买入 / 增持 / 中性 / 减持 / 卖出"),
    days: int = Query(90, ge=1, le=730, description="只查最近 N 天"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数上限"),
):
    """查询券商研报列表。

    DB 数据不足时自动触发 AkShare 实时拉取并入库后再返回。
    """
    try:
        rows = news_svc.list_research_reports(
            symbol=symbol, institute=institute, rating=rating, days=days, limit=limit,
        )
        return BaseResponse(data={"total": len(rows), "items": rows})
    except Exception as exc:
        logger.error("research_list failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.post("/api/news/sync")
def news_sync(req: NewsSyncRequest = NewsSyncRequest()):
    """手动同步所有资讯来源：财联社电报 + 东方财富全球资讯 + 券商研报 + 指定股票的个股新闻。

    推荐调用方式（Java cron / 手动触发）：
        POST /api/news/sync  {"symbols": ["600519", "000001"]}
    """
    try:
        stats = news_svc.sync_all_news(symbols=req.symbols if req else [])
        total = sum(stats.values())
        return BaseResponse(
            data=stats,
            message=f"同步完成: total={total} 条",
        )
    except Exception as exc:
        logger.error("news_sync failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


# ====================================================================
#  /api/demo/* — 演示级数据源（技术面数据看板联调用）
#  DEMO 标注：本组接口为演示实现，供前端看板开发联调；生产环境需
#  替换/校验数据源（见 services/demo_flow_service.py）。
# ====================================================================


@app.get("/api/demo/fundflow")
def demo_fundflow(
    symbol: str = Query(..., description="股票代码，如 600519"),
    days: int = Query(10, ge=1, le=30, description="返回最近 N 个交易日"),
) -> BaseResponse:
    """个股资金流向（DEMO）：每日大单净流向 + 3/5/10 日净流入汇总。"""
    from services.demo_flow_service import get_stock_fundflow

    return BaseResponse(data=get_stock_fundflow(symbol, days))


@app.get("/api/demo/shareholders")
def demo_shareholders(
    symbol: str = Query(..., description="股票代码，如 600519"),
) -> BaseResponse:
    """股东户数历史（DEMO）：散户数量维度筹码情绪。"""
    from services.demo_flow_service import get_shareholder_count

    return BaseResponse(data=get_shareholder_count(symbol))


# ====================================================================
#  /api/demo/quick-entry/* — 演示级数据源（对话页投研快捷入口联调用）
# ====================================================================


@app.get("/api/demo/hot-sectors")
def demo_hot_sectors() -> BaseResponse:
    """今日热点板块（DEMO）。"""
    from services.demo_quick_entry_service import get_hot_sectors

    return BaseResponse(data=get_hot_sectors())


@app.get("/api/demo/calendar-events")
def demo_calendar_events() -> BaseResponse:
    """未来大事日历（DEMO）。"""
    from services.demo_quick_entry_service import get_calendar_events

    return BaseResponse(data=get_calendar_events())


@app.get("/api/demo/rankings")
def demo_rankings(
    type: str = Query(None, description="榜单类型过滤"),
) -> BaseResponse:
    """特色榜单（DEMO）。"""
    from services.demo_quick_entry_service import get_rankings

    return BaseResponse(data=get_rankings(type))


@app.get("/api/demo/strategies")
def demo_strategies() -> BaseResponse:
    """精选策略（DEMO）。"""
    from services.demo_quick_entry_service import get_strategies

    return BaseResponse(data=get_strategies())


# ====================================================================
#  /api/demo/market-overview — 市场概览看板数据源（聚合接口）
# ====================================================================


@app.get("/api/demo/market-overview")
def demo_market_overview() -> BaseResponse:
    """市场概览聚合数据（DEMO）：大盘指数 + 市场宽度 + 热点板块 + 北向资金 + 成交量。

    一次性返回市场概览看板所需全部数据，前端一个请求即可渲染五卡。
    """
    from services.demo_market_overview_service import get_market_overview

    return BaseResponse(data=get_market_overview())


# ====================================================================
#  /api/financial/* & /api/valuation — 基本面分析看板数据源
#  透传 financial_data_service / valuation_service 已有能力。
# ====================================================================


@app.get("/api/financial/abstract")
def financial_abstract(
    symbol: str = Query(..., description="股票代码，如 600519"),
) -> BaseResponse:
    """获取指定股票最新一期结构化财务摘要（ROE/毛利率/营收/利润等）。"""
    from services.financial_data_service import get_financial_abstract

    try:
        data = get_financial_abstract(symbol)
        return BaseResponse(data=data)
    except Exception as exc:
        logger.error("financial_abstract failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/financial/report")
def financial_report(
    symbol: str = Query(..., description="股票代码，如 600519"),
) -> BaseResponse:
    """获取指定股票最近 4 期完整财务报表。"""
    from services.financial_data_service import get_financial_report

    try:
        data = get_financial_report(symbol)
        return BaseResponse(data=data)
    except Exception as exc:
        logger.error("financial_report failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/valuation")
def valuation(
    symbol: str = Query(..., description="股票代码，如 600519"),
) -> BaseResponse:
    """获取指定股票最新估值数据（PE/PB/PS/市值等）。"""
    from services.valuation_service import get_valuation

    try:
        data = get_valuation(symbol)
        return BaseResponse(data=data)
    except Exception as exc:
        logger.error("valuation failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


# ====================================================================
#  /api/settings/* — 设置中心 CRUD + 连通性测试
# ====================================================================


@app.get("/api/settings")
def settings_get() -> BaseResponse:
    """获取当前配置视图：敏感字段只会以 xxx_masked + xxx_set 返回，不暴露密文与明文。"""
    from services.settings_service import get_view
    return BaseResponse(data=get_view())


@app.put("/api/settings")
def settings_update(body: dict) -> BaseResponse:
    """局部更新配置：敏感字段传明文→存密文；传 ""→清空；传 null / 不传→保持原值。"""
    from services.settings_service import update as _settings_update
    try:
        new_v, new_view = _settings_update(body)
        return BaseResponse(data={"version": new_v, "settings": new_view})
    except Exception as exc:
        logger.error("settings update failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.post("/api/settings/test-provider")
def settings_test_provider(body: dict) -> BaseResponse:
    """测试大模型连通性：body {model?, base_url?, api_key?, ...} 可选，缺省用已保存配置。"""
    from services.settings_service import test_provider
    return BaseResponse(data=test_provider(body or {}))


@app.post("/api/settings/test-notification")
def settings_test_notification(body: dict) -> BaseResponse:
    """测试通知渠道：body {type: "feishu"|"pushplus", params: {...}}。"""
    from services.settings_service import test_notification
    return BaseResponse(data=test_notification(body or {}))


@app.post("/api/settings/validate-llm")
def settings_validate_llm(body: dict) -> BaseResponse:
    """校验 LLM 参数：返回 ok + usage 明细，不写盘。"""
    from services.settings_service import validate_llm
    try:
        return BaseResponse(data=validate_llm(body or {}))
    except Exception as exc:
        logger.error("validate-llm failed: %s", exc)
        return BaseResponse(code=-1, message=str(exc), data=None)


@app.get("/api/settings/internal/full")
def settings_internal_full(
    request: Request,
    internal_token: str = Query(None, description="可选：通过 query 传递 INTERNAL_TOKEN"),
) -> BaseResponse:
    """【内部用】返回完整配置（含明文敏感字段）：仅限本机 IP 或携带合法 SETTINGS_INTERNAL_TOKEN。"""
    import os as _os
    from services.settings_service import get_full_internal
    client_host = getattr(request.client, "host", None)
    is_loopback = client_host in ("127.0.0.1", "::1", "localhost") or client_host is None
    header_token = request.headers.get("x-settings-internal-token") or request.headers.get("x-internal-token")
    expected_token = _os.getenv("SETTINGS_INTERNAL_TOKEN", "")
    token_ok = expected_token != "" and (internal_token == expected_token or header_token == expected_token)
    if not (is_loopback or token_ok):
        return BaseResponse(code=403, message="forbidden", data=None)
    try:
        data = get_full_internal(auth_ok=True)
        return BaseResponse(data=data)
    except PermissionError:
        return BaseResponse(code=403, message="forbidden", data=None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
