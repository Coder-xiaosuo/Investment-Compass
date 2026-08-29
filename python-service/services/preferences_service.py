"""偏好记忆服务 — memories/preferences.md 的读取与问卷初始化写入。

职责：
- 读取偏好文件为结构化数据（供前端判断是否已初始化、回显现有偏好）。
- 用新用户问卷结果初始化偏好文件（分区模板 + 来源标注，写前备份 .bak）。

语义约定（重要）：
- 偏好是【用户级全局】状态，不是会话级：单一文件，所有会话共享。
- `initialized` 是全局判定：新用户首次使用对话功能前由前端检查一次，
  未初始化则弹问卷（可跳过），提交后永久不再弹——与新建会话无关。
- 前端把「是否弹问卷」挂在用户级状态上，绝不挂在会话创建事件上。

本文件是前端问卷（API）与 Agent（edit_file）对偏好文件的共识结构；
分区与 memories/preferences.md 模板保持一致。
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_MEMORIES_DIR = Path(__file__).resolve().parent.parent / "memories"
PREFERENCES_PATH = _MEMORIES_DIR / "preferences.md"

# 分区顺序与标题（与偏好模板文件保持一致）
_SECTIONS = ["风险偏好", "决策风格", "关注板块与标的", "分析深度偏好"]

# 问卷答案字段 → 分区标题（多字段可合并进同一分区）
_FIELD_TO_SECTION = {
    "risk_preference": "风险偏好",
    "decision_style": "决策风格",
    "watch_sectors": "关注板块与标的",
    "watch_stocks": "关注板块与标的",
    "analysis_depth": "分析深度偏好",
}

# 模板占位标记：含这些词视为未初始化
_TEMPLATE_MARKERS = ("待确认", "示例")

_HEADER_COMMENT = """<!-- preferences.md — 用户偏好记忆文件。
     写入来源：初始化问卷（服务）/ 用户确认 / Agent 提炼（edit_file）。
     每条记录带来源标注；维护时保持分区结构。 -->
"""


def _render_content(answers: dict) -> str:
    """按分区模板组装偏好文件内容。answers 为问卷答案 dict（键见 _FIELD_TO_SECTION）。"""
    now = datetime.now().strftime("%Y-%m-%d")
    parts = [_HEADER_COMMENT, "# 用户偏好", ""]
    for section in _SECTIONS:
        parts.append(f"## {section}")
        if section == "关注板块与标的":
            secs = (answers.get("watch_sectors") or "").strip()
            stocks = (answers.get("watch_stocks") or "").strip()
            content = ""
            if secs:
                content += f"板块：{secs}"
            if stocks:
                content += ("；" if content else "") + f"标的：{stocks}"
            parts.append(f"<!-- 初始化问卷 {now} --> {content or '未填写'}")
        else:
            field = next(k for k, s in _FIELD_TO_SECTION.items() if s == section)
            content = (answers.get(field) or "").strip() or "未填写"
            parts.append(f"<!-- 初始化问卷 {now} --> {content}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def get_preferences() -> dict:
    """读取偏好文件，返回结构化数据。

    返回 dict:
      - initialized: bool      任一非模板区段有真实内容
      - sections: {分区: 内容}   标准 4 分区
      - evolution: str | None  自进化画像区段完整文本（不含标题）
      - raw: str               原始文件完整内容
    """
    if not PREFERENCES_PATH.exists():
        return {"initialized": False, "sections": {}, "evolution": None, "raw": ""}
    text = PREFERENCES_PATH.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    evolution_lines: list[str] = []
    in_evolution = False
    current: str | None = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            section_name = m.group(1).strip()
            if "投资风格画像" in section_name or "自进化" in section_name:
                in_evolution = True
                current = None
                continue
            in_evolution = False
            current = section_name
            sections[current] = ""
        elif in_evolution and line.strip():
            evolution_lines.append(line.strip())
        elif current and line.strip():
            stripped = re.sub(r"^<!--.*?-->\s*", "", line.strip())
            if stripped:
                sections[current] = (sections[current] + " " + stripped).strip()

    has_real = any(
        value and not any(marker in value for marker in _TEMPLATE_MARKERS)
        for value in sections.values()
    )
    evolution_text = "\n".join(evolution_lines) if evolution_lines else None
    return {
        "initialized": bool(has_real),
        "sections": sections,
        "evolution": evolution_text,
        "raw": text,
    }


def init_preferences(answers: dict) -> str:
    """用问卷答案初始化偏好文件（覆盖式，写前备份 .bak）。

    Args:
        answers: 问卷答案 dict，键为 _FIELD_TO_SECTION 的字段名。

    Returns:
        写入的完整内容；任何异常时告警并返回空串（绝不向上抛异常）。
    """
    try:
        _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = None
        if PREFERENCES_PATH.exists():
            backup_path = PREFERENCES_PATH.with_suffix(".md.bak")
            shutil.copy2(PREFERENCES_PATH, backup_path)
        content = _render_content(answers)
        PREFERENCES_PATH.write_text(content, encoding="utf-8")
        logger.info("preferences.md 已由问卷初始化（备份: %s）", backup_path or "无")
        return content
    except Exception as exc:
        logger.warning("初始化偏好失败: %s", exc)
        return ""
