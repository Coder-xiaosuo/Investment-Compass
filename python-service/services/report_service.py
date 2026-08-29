"""Report service — 分析报告落盘。"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = _BASE_DIR / "data" / "reports"


def write_decision_report(
    content: str,
    card_data: dict | None,
    trace_id: str | None = None,
) -> str | None:
    """将主 Agent 的决策分析报告落盘（Markdown 全文 + JSON 元数据）。

    Args:
        content: 完整消息文本（Markdown）。
        card_data: 复合决策卡片数据，可为 None（此时 JSON 落 ``{}``）。
        trace_id: 决策幂等键，作为文件名主体（``{trace_id}.md/.json``）；
            缺省回退时间戳命名，保证幂等重放收敛到同一文件。

    Returns:
        写入的 Markdown 文件相对路径（相对 python-service 根目录）；
        任何异常时告警并返回 None（绝不向上抛异常）。
    """
    try:
        symbol = (card_data or {}).get("symbol") or "_misc"
        # 稳定幂等键优先；重放（同 trace_id）会覆盖写同一文件而非新建
        file_stem = trace_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = REPORTS_DIR / symbol
        os.makedirs(target_dir, exist_ok=True)

        md_path = target_dir / f"{file_stem}.md"
        md_path.write_text(content or "", encoding="utf-8")

        json_path = target_dir / f"{file_stem}.json"
        payload = card_data if card_data is not None else {}
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return str(md_path.relative_to(_BASE_DIR))
    except Exception:
        logger.warning("write_decision_report failed", exc_info=True)
        return None
