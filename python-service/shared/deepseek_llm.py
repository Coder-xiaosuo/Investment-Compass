"""DeepSeek ChatOpenAI 子类：保留 thinking 模式的 reasoning_content 思维链。

背景：langchain-openai 1.3.x 的模块级转换函数（_convert_dict_to_message /
_convert_delta_to_message_chunk）会丢弃 OpenAI 兼容响应中的非标准字段
（如 DeepSeek thinking 模式返回的 reasoning_content），导致事件流拿不到思维链。

本子类在两个转换入口补回该字段：
- 流式：_convert_chunk_to_generation_chunk（delta.reasoning_content，天然为增量片段）
- 非流式：_create_chat_result（message.reasoning_content）

使用方式与 ChatOpenAI 完全一致（含 extra_body 思考参数透传）。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages.ai import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI


class DeepSeekChatOpenAI(ChatOpenAI):
    """保留 DeepSeek reasoning_content 思维链的 ChatOpenAI 子类。"""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> Any:
        """流式：把 delta.reasoning_content 注入 AIMessageChunk.additional_kwargs。"""
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is not None:
            choices = (
                chunk.get("choices", [])
                or chunk.get("chunk", {}).get("choices", [])
            )
            if choices:
                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content")
                if reasoning and isinstance(generation_chunk.message, AIMessageChunk):
                    generation_chunk.message.additional_kwargs[
                        "reasoning_content"
                    ] = reasoning
        return generation_chunk

    def _create_chat_result(
        self,
        response: Any,
        generation_info: dict | None = None,
    ) -> Any:
        """非流式：把 message.reasoning_content 注入 AIMessage.additional_kwargs。"""
        result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(warnings=False)
        )
        for i, choice in enumerate(response_dict.get("choices") or []):
            reasoning = (choice.get("message") or {}).get("reasoning_content")
            if reasoning and i < len(result.generations):
                message = result.generations[i].message
                if isinstance(message, AIMessage):
                    message.additional_kwargs["reasoning_content"] = reasoning
        return result
