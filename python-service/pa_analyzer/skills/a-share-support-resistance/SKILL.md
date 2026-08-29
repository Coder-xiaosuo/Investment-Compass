---
name: a-share-support-resistance
description: A股特殊的支撑阻力规则。使用当 Codex 分析A股市场且 detected_patterns 包含 integer_level 或 chip_dense 时。包含：A股整数关口（10/20/50/100元）的支撑阻力层级、筹码密集区识别与交易规则、前高前低在A股的特殊有效性、支撑阻力位可靠性排序。
---

# A股支撑阻力

## 概述

本技能包包含【A股支撑阻力】的完整价格行为交易知识，源自 Al Brooks 价格行为体系。

源文件：`prompts/A股支撑阻力.txt`

## 何时使用

当 Codex 遇到以下场景时，应加载本技能包的 reference 文件：
- 确认市场处于对应形态后需要生成具体交易方案时
- 相关形态的 detected_patterns 被触发后
- 阶段二策略路由决策中需要入场规则时

## 使用方式

1. 当触发条件满足时，加载 `references/` 目录下的完整参考文档
2. 根据参考文档中的规则、条件和约束生成分析结果
3. 遵守文档中的硬禁令和约束条件
4. 分析文件通过 `references/` 子目录引用，不直接读入上下文（渐进披露）

## 参考文件

`references/` 目录包含原始的完整策略文档（Markdown 格式），可直接加载到上下文使用。
