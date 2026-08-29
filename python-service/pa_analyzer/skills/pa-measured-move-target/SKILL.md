---
name: pa-measured-move-target
description: Al Brooks 测量运动（Measured Move, MM）和结构目标的完整知识。使用当 Codex 需要计算测量运动目标或评估结构目标时。包含：MM的识别与计算、MM上/下目标确定、结构目标的层次（小MM/大MM）、MM在趋势和区间中的应用。
---

# MeasuredMove与结构目标

## 概述

本技能包包含【MeasuredMove与结构目标】的完整价格行为交易知识，源自 Al Brooks 价格行为体系。

源文件：`prompts/文件23-MeasuredMove与结构目标.txt`

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
