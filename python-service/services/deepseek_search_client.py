"""DeepSeek 原生联网搜索客户端（Responses API + web_search 工具）。

数据流：
  查询 → POST https://api.deepseek.com/responses (tools=[{"type": "web_search"}])
       → 服务端搜索并注入上下文 → 返回最终回答 + 模型 open_page 的 URL

已知限制（官方设计，非缺陷）：
  - 仅 Responses API 支持 web_search 工具；chat/completions 端点会 400 拒绝
  - 搜索结果是"黑盒注入"：标题/摘要/URL 列表客户端拿不到，只能拿到最终回答
  - URL 唯一暴露通道：模型主动执行 open_page 动作（需剥离 #ws_call_id= 追踪尾巴）

用途：资讯子 Agent 在本地检索（DB/AkShare）为空时降级启用，保证仍有信息可答。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.deepseek.com"
_TIMEOUT_S = 60.0


def _clean_url(url: str) -> str:
    """剥离服务端追踪尾巴：#ws_call_id=xxx。"""
    return (url or "").split("#ws_call_id=")[0].strip()


def deepseek_web_search(
    query: str,
    model: str | None = None,
    max_timeout: float = _TIMEOUT_S,
) -> dict[str, Any]:
    """调用 DeepSeek Responses API 原生联网搜索。

    Args:
        query: 搜索问题（自然语言）
        model: 模型名，默认取 settings.DEEPSEEK_SEARCH_MODEL（deepseek-v4-flash）
        max_timeout: 请求超时秒数（服务端搜索 + 生成通常 10-30s）

    Returns:
        {"answer": str, "sources": [{"url": str}, ...]}
        answer 为模型基于联网搜索生成的最终回答；
        sources 为模型实际 open_page 的页面 URL（黑盒限制下的唯一来源，可去重）。

    Raises:
        RuntimeError: 未配置 API Key / 未返回有效回答 / 调用异常
    """
    import os

    from openai import OpenAI

    from shared.config import settings

    api_key = settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，无法启用联网搜索降级")

    model = model or settings.DEEPSEEK_SEARCH_MODEL

    client = OpenAI(api_key=api_key, base_url=_BASE_URL, timeout=max_timeout)
    resp = client.responses.create(
        model=model,
        input=query,
        tools=[{"type": "web_search"}],
        stream=False,
    )

    answer = (getattr(resp, "output_text", "") or "").strip()

    sources: list[dict[str, str]] = []
    for item in resp.output or []:
        if getattr(item, "type", "") != "web_search_call":
            continue
        action = getattr(item, "action", None)
        if not action or getattr(action, "type", "") != "open_page":
            continue
        url = _clean_url(getattr(action, "url", ""))
        if url and not any(s["url"] == url for s in sources):
            sources.append({"url": url})

    if not answer:
        raise RuntimeError("DeepSeek 联网搜索未返回有效回答")

    logger.info(
        "DeepSeek web_search ok: model=%s, answer_len=%d, sources=%d",
        model, len(answer), len(sources),
    )
    return {"answer": answer, "sources": sources}
