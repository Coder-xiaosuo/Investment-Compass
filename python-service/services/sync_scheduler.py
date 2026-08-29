"""进程内数据同步调度器（apscheduler）。

在 FastAPI lifespan 中随进程启动/停止，摆脱对外部 cron 的依赖：

- 每日收盘后（默认 17:30）全量增量同步行情（东财主源，断路器自动切新浪）
- 每日定时（默认 17:00）同步全市场资讯/快讯/研报
- 同步完成后通过飞书推送结果与失败告警

配置（config/settings.json 的 ``scheduler`` 段）：
    enabled          是否启用（默认 true）
    market_sync_cron 行情同步 cron（默认 "30 17 * * 1-5" 周一至周五 17:30）
    news_sync_cron   资讯同步 cron（默认 "0 17 * * 1-5" 周一至周五 17:00）
    timezone         时区（默认 "Asia/Shanghai"）
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# apscheduler 依赖懒加载：未安装时导入失败仅告警，不影响主服务启动
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover
    BackgroundScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    logger.warning("apscheduler 未安装，数据同步调度器不可用")

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

_SCHEDULER_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "market_sync_cron": "30 17 * * 1-5",
    "news_sync_cron": "0 17 * * 1-5",
    "timezone": "Asia/Shanghai",
}

_scheduler: Any = None


def _load_scheduler_config() -> dict[str, Any]:
    """读取 config/settings.json 的 scheduler 段；缺失/损坏时返回默认值。"""
    cfg = dict(_SCHEDULER_DEFAULTS)
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        cfg.update(raw.get("scheduler") or {})
    except Exception as exc:
        logger.warning("读取 scheduler 配置失败（%s），使用默认值: %s", _SETTINGS_PATH, exc)
    return cfg


def _notify(text: str) -> None:
    """推送飞书文本消息（未启用/失败静默）。"""
    try:
        from services.feishu_notifier import get_feishu_notifier

        get_feishu_notifier().send_text(text)
    except Exception as exc:  # pragma: no cover - 通知失败不影响同步结果
        logger.warning("飞书告警发送异常: %s", exc)


# ── Job 实现 ──────────────────────────────────────────────────────────────────

def _market_sync_job() -> None:
    """收盘行情全量增量同步 + 飞书结果/失败告警。"""
    from services import stock_metadata_service as sms
    from services import sync_service as sync_svc
    from services.source_circuit_breaker import get_source_breaker

    symbols = [s["symbol"] for s in sms.list_all_symbols()]
    if not symbols:
        logger.warning("定时行情同步：stock_metadata 为空，跳过")
        _notify("【数据中台】定时行情同步跳过：股票列表为空")
        return

    breaker = get_source_breaker()
    started = time.time()
    total_records, errors = sync_svc.sync_symbols(symbols)
    elapsed = int(time.time() - started)

    lines = [
        "【数据中台】收盘行情同步完成",
        f"标的 {len(symbols)} 只 · 新增 {total_records} 条 · 耗时 {elapsed}s",
        f"当前数据源：{'东财' if breaker.current_source == 'eastmoney' else '新浪（熔断中）'}",
    ]
    if errors:
        lines.append(f"失败 {len(errors)} 只：")
        lines.extend(errors[:10])
        if len(errors) > 10:
            lines.append(f"... 共 {len(errors)} 只失败")
        logger.warning("行情同步完成但有失败: %d/%d", len(errors), len(symbols))
    else:
        logger.info("行情同步全部成功: %d 只", len(symbols))
    _notify("\n".join(lines))


def _news_sync_job() -> None:
    """全市场资讯/快讯/研报定时同步 + 飞书结果通知。"""
    from services import news_service as news_svc

    try:
        stats = news_svc.sync_all_news()
        total = sum(stats.values()) if stats else 0
        detail = " · ".join(f"{k}={v}" for k, v in (stats or {}).items())
        logger.info("资讯同步完成: total=%d (%s)", total, detail)
        _notify(f"【数据中台】资讯同步完成：共 {total} 条（{detail or '无'}）")
    except Exception as exc:
        logger.error("资讯同步异常: %s", exc)
        _notify(f"【数据中台】资讯同步异常：{exc}")


# ── 生命周期 ──────────────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """注册并启动调度器（幂等：已启动则跳过）。"""
    global _scheduler
    if _scheduler is not None:
        return
    if BackgroundScheduler is None:
        logger.warning("apscheduler 不可用，跳过调度器启动")
        return

    cfg = _load_scheduler_config()
    if not cfg.get("enabled", True):
        logger.info("数据同步调度器未启用（scheduler.enabled=false）")
        return

    tz = cfg.get("timezone", "Asia/Shanghai")
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        _market_sync_job,
        CronTrigger.from_crontab(cfg["market_sync_cron"], timezone=tz),
        id="market_daily_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _news_sync_job,
        CronTrigger.from_crontab(cfg["news_sync_cron"], timezone=tz),
        id="news_daily_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "数据同步调度器已启动：行情=%s 资讯=%s (tz=%s)",
        cfg["market_sync_cron"], cfg["news_sync_cron"], tz,
    )


def stop_scheduler() -> None:
    """停止调度器（幂等）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("数据同步调度器已停止")


def get_scheduler() -> Any:
    """返回调度器实例（供状态查询/调试）。"""
    return _scheduler
