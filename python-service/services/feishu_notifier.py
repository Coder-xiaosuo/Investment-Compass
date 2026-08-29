"""飞书机器人通知模块（主系统重构版）。

由 PA_Agent 项目的飞书通知设计（PA_Agent/pa_agent/notify/feishu_notifier.py）重构而来，
适配主系统 python-service：
  - 配置来源：config/settings.json 的 "feishu" 段（enabled/webhook_url/secret/app_id/app_secret）
  - 自定义机器人 Webhook 推送（文本 / 交互卡片）
  - 可选签名校验（timestamp + secret 的 HMAC-SHA256，sign 拼接 "timestamp" + "\\n" + secret）
  - 可选图片上传（需 app_id/app_secret 换取 tenant_access_token）
  - tenant_access_token 进程内缓存（2 小时 TTL，提前 5 分钟刷新，线程安全）

未配置 webhook_url 时视为未启用：所有发送调用直接返回 False，仅 debug 日志，绝不抛异常。

飞书官方文档
------------
自定义机器人：https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
图片上传：    https://open.feishu.cn/document/server-docs/im-v1/image/create
获取 tenant_access_token：
    https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 飞书 Open API 端点 ─────────────────────────────────────────────────────────
_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_IMAGE_UPLOAD_URL = "https://open.feishu.cn/open-apis/im/v1/images"

# tenant_access_token 有效期 2 小时；提前 5 分钟刷新
_TOKEN_TTL_BUFFER_S = 300
_REQUEST_TIMEOUT_S = 12

# 主系统配置：python-service/config/settings.json
_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

# feishu 段默认值（settings.json 缺失/损坏时兜底）
_FEISHU_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "webhook_url": "",
    "secret": "",
    "app_id": "",
    "app_secret": "",
    "notify_on_order_only": True,
}


# ── Token 缓存（进程内单例，线程安全）────────────────────────────────────────────
class _TokenCache:
    """tenant_access_token 缓存：2 小时有效期，提前 5 分钟刷新。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str = ""
        self._expire_at: float = 0.0

    def get(self, app_id: str, app_secret: str) -> str | None:
        """返回有效的 tenant_access_token，过期则自动刷新。"""
        with self._lock:
            if self._token and time.time() < self._expire_at:
                return self._token
            return self._refresh(app_id, app_secret)

    def _refresh(self, app_id: str, app_secret: str) -> str | None:
        try:
            import requests  # type: ignore[import]

            resp = requests.post(
                _TOKEN_URL,
                json={"app_id": app_id, "app_secret": app_secret},
                headers={"Content-Type": "application/json"},
                timeout=_REQUEST_TIMEOUT_S,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning("飞书 token 获取失败: %s", data)
                return None
            self._token = data["tenant_access_token"]
            expire = int(data.get("expire", 7200))
            self._expire_at = time.time() + expire - _TOKEN_TTL_BUFFER_S
            logger.debug("飞书 tenant_access_token 已刷新，有效期 %ds", expire)
            return self._token
        except Exception as exc:
            logger.warning("飞书 token 刷新异常: %s", exc)
            return None


# ── 配置加载 ──────────────────────────────────────────────────────────────────
def _load_feishu_config() -> dict[str, Any]:
    """读取 config/settings.json 的 feishu 段；缺失/损坏时返回默认值，不抛异常。"""
    cfg = dict(_FEISHU_DEFAULTS)
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        cfg.update(raw.get("feishu") or {})
    except Exception as exc:
        logger.warning("读取 feishu 配置失败（%s），使用默认值: %s", _SETTINGS_PATH, exc)
    return cfg


# ── 签名 ──────────────────────────────────────────────────────────────────────
def _gen_sign(secret: str, timestamp: int) -> str:
    """按飞书规范计算 HmacSHA256 + Base64 签名。

    签名字符串：timestamp + "\\n" + secret
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


# ── 主类 ──────────────────────────────────────────────────────────────────────
class FeishuNotifier:
    """飞书自定义机器人通知器（requests 同步实现，超时 12s）。

    所有对外发送方法均不抛异常：未启用 / 请求失败时返回 False 并记录日志。
    """

    def __init__(self) -> None:
        self._token_cache = _TokenCache()

    def _config(self) -> dict[str, Any]:
        return _load_feishu_config()

    def is_enabled(self) -> bool:
        """是否启用：feishu.enabled 为 true 且 webhook_url 非空。"""
        cfg = self._config()
        if not cfg.get("enabled", True):
            return False
        return bool((cfg.get("webhook_url") or "").strip())

    def _post(self, payload: dict[str, Any]) -> bool:
        """向 Webhook 推送消息体（text / interactive 卡片通用）。"""
        cfg = self._config()
        if not cfg.get("enabled", True):
            logger.debug("飞书通知已禁用（settings.json feishu.enabled=false）")
            return False
        webhook_url = (cfg.get("webhook_url") or "").strip()
        if not webhook_url:
            logger.debug("飞书通知未启用：settings.json 未配置 feishu.webhook_url，跳过推送")
            return False

        # 可选签名：secret 非空时按飞书文档计算 sign
        secret = (cfg.get("secret") or "").strip()
        if secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = _gen_sign(secret, ts)

        try:
            import requests  # type: ignore[import]

            resp = requests.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=_REQUEST_TIMEOUT_S,
            )
            result = resp.json()
            # 飞书返回 code=0 或 StatusCode=0 均为成功
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                logger.info("飞书通知发送成功: msg_type=%s", payload.get("msg_type"))
                return True
            logger.warning("飞书通知返回错误: %s", result)
            return False
        except Exception as exc:
            logger.warning("飞书通知 HTTP 请求失败: %s", exc)
            return False

    def send_text(self, text: str) -> bool:
        """推送文本消息。未启用 / 失败返回 False，不抛异常。"""
        return self._post({"msg_type": "text", "content": {"text": text}})

    def send_card(self, card_json: dict) -> bool:
        """推送交互卡片（msg_type=interactive）。card_json 为卡片内容 dict。"""
        return self._post({"msg_type": "interactive", "card": card_json})

    def send_decision_card(self, text: str, image_bytes: bytes | None = None) -> bool:
        """推送投资决策交互卡片（K 线图 + 决策文本）。

        - image_bytes 非空时：先 ``upload_image`` 获取 image_key，成功则组装
          msg_type="interactive" 卡片（header 颜色按文本动作：买入绿 / 卖出红 / 其他蓝）。
          上传失败时立即重试一次（缓解 token/网络瞬时抖动），仍失败则回退文本。
        - image_bytes 为空或上传失败：回退 ``send_text`` 纯文本推送。
        - 未启用 / 失败返回 False，不抛异常（与其它发送方法一致）。
        """
        if not self.is_enabled():
            return False

        # 有图片 → 尝试上传并组装 interactive 卡片；失败重试一次后回退文本
        if image_bytes:
            image_key = self.upload_image(image_bytes, image_key_hint="kline_chart.png")
            if not image_key:
                # 保图优先：上传失败立即重试一次（仅一次，避免重复打扰飞书接口）
                logger.info("飞书图片上传失败，重试一次")
                image_key = self.upload_image(image_bytes, image_key_hint="kline_chart.png")
            if image_key:
                card = {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": "投资决策"},
                        "template": _card_template_from_text(text),
                    },
                    "elements": [
                        {
                            "tag": "img",
                            "img_key": image_key,
                            "alt": {"tag": "plain_text", "content": "K线图"},
                        },
                        {"tag": "markdown", "content": text},
                    ],
                }
                return self._post({"msg_type": "interactive", "card": card})
            logger.warning("飞书图片上传失败（已重试一次），回退文本推送决策卡片")

        return self.send_text(text)

    def upload_image(
        self, image_bytes: bytes, image_key_hint: str | None = None
    ) -> str | None:
        """上传图片到飞书，返回 image_key 或 None。

        需要配置 feishu.app_id / feishu.app_secret（企业自建应用，申请 im:resource 权限）；
        未配置或失败时返回 None。image_key_hint 用于提示文件名（可选）。
        """
        cfg = self._config()
        app_id = (cfg.get("app_id") or "").strip()
        app_secret = (cfg.get("app_secret") or "").strip()
        if not (app_id and app_secret):
            logger.debug("飞书图片上传：app_id/app_secret 未配置，跳过")
            return None
        if not image_bytes:
            return None
        token = self._token_cache.get(app_id, app_secret)
        if not token:
            logger.warning("飞书图片上传：无法获取 access_token，跳过图片")
            return None
        try:
            import requests  # type: ignore[import]

            filename = (image_key_hint or "").strip() or "image.png"
            resp = requests.post(
                _IMAGE_UPLOAD_URL,
                headers={"Authorization": f"Bearer {token}"},
                files={"image": (filename, image_bytes, "image/png")},
                data={"image_type": "message"},
                timeout=_REQUEST_TIMEOUT_S,
            )
            data = resp.json()
            if data.get("code") == 0:
                key = data["data"]["image_key"]
                logger.info("飞书图片上传成功: %s -> %s", filename, key)
                return key
            logger.warning("飞书图片上传失败: %s", data)
            return None
        except Exception as exc:
            logger.warning("飞书图片上传异常: %s", exc)
            return None


# ── 模块级单例 ────────────────────────────────────────────────────────────────
_notifier: FeishuNotifier | None = None
_singleton_lock = threading.Lock()


def get_feishu_notifier() -> FeishuNotifier:
    """获取进程内复用的 FeishuNotifier 单例（线程安全）。"""
    global _notifier
    if _notifier is None:
        with _singleton_lock:
            if _notifier is None:
                _notifier = FeishuNotifier()
    return _notifier


# ── 决策卡片文本（纯函数，便于单测） ──────────────────────────────────────────────
_ACTION_LABELS = {"BUY": "买入信号", "SELL": "卖出信号", "HOLD": "观望"}


def _card_template_from_text(text: str) -> str:
    """根据决策文本推断卡片 header 颜色模板。

    - 含「卖出」→ red（飞书卡片红色模板）
    - 含「买入」→ green（飞书卡片绿色模板）
    - 其他（观望等）→ blue（飞书卡片蓝色模板）
    """
    if "卖出" in text:
        return "red"
    if "买入" in text:
        return "green"
    return "blue"


def _fmt_num(value: Any) -> str:
    """数值安全格式化：空值返回 —，否则返回字符串原样。"""
    if value is None or value == "":
        return "—"
    return str(value)


def _fmt_pct(ratio: Any) -> str:
    """涨跌幅比例（如 0.0312）格式化为 +3.12%。"""
    try:
        return f"{float(ratio) * 100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def build_decision_card_text(decision: dict) -> str:
    """将 decision_cards 的一行（dict）格式化为结构化推送文本。

    输入键：symbol / stock_name / action / current_price /
           stop_loss_price / take_profit_price / market_cycle / pattern /
           reasoning / review_outcome
    review_outcome 为复盘回填 JSON（verdict: HIT/MISS, profit_ratio, ...），
    非空时附加复盘状态行（✅命中 / ❌未命中 + 实际涨跌）。

    输出结构：
        股票名(代码)
        动作：买入信号 / 卖出信号 / 观望
        现价：xxx
        支撑：xxx　阻力：xxx        （有则展示）
        市场周期与形态：xxx / xxx   （有则展示）
        分析理由：xxx               （非空则展示）
        复盘状态：✅ 命中（实际涨跌 +3.12%）  （review_outcome 非空则展示）
    """
    symbol = decision.get("symbol") or "—"
    stock_name = decision.get("stock_name") or ""
    title = f"{stock_name}({symbol})" if stock_name else str(symbol)

    action_raw = str(decision.get("action") or "HOLD").upper()
    action_label = _ACTION_LABELS.get(action_raw, action_raw)

    lines = [f"【{title}】", f"动作：{action_label}"]

    # 现价
    current_price = decision.get("current_price")
    lines.append(f"现价：{_fmt_num(current_price)}")

    # 支撑/阻力（有则展示）
    support = decision.get("stop_loss_price")
    resistance = decision.get("take_profit_price")
    if support not in (None, "") or resistance not in (None, ""):
        lines.append(f"支撑：{_fmt_num(support)}　阻力：{_fmt_num(resistance)}")

    # 市场周期与形态（有则展示）
    market_cycle = decision.get("market_cycle") or ""
    pattern = decision.get("pattern") or ""
    if market_cycle or pattern:
        cycle_part = market_cycle or "—"
        pattern_part = pattern or "—"
        lines.append(f"市场周期与形态：{cycle_part} / {pattern_part}")

    # 分析理由（非空则展示）
    reasoning = (decision.get("reasoning") or "").strip()
    if reasoning:
        lines.append(f"分析理由：\n{reasoning}")

    # 复盘状态（review_outcome 非空则展示）
    review = decision.get("review_outcome") or {}
    if review:
        verdict = review.get("verdict") or ""
        if str(verdict).upper() == "HIT":
            verdict_label = "✅ 命中"
        elif str(verdict).upper() == "MISS":
            verdict_label = "❌ 未命中"
        else:
            verdict_label = f"⚠️ {_fmt_num(verdict)}"
        line = f"复盘状态：{verdict_label}"
        profit_ratio = review.get("profit_ratio")
        if profit_ratio not in (None, ""):
            line += f"（实际涨跌 {_fmt_pct(profit_ratio)}）"
        lines.append(line)

    return "\n".join(lines)
