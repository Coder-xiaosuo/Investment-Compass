# Intent Router Agent - 架构设计文档

## 1. 概述

Intent Router Agent 是投资罗盘对话系统的意图识别与路由模块，负责将用户自然语言输入转换为结构化的意图和实体，实现精准路由到对应的子 Agent。

### 1.1 设计理念

- **规则优先，模型兜底**：高频、明确的请求通过规则快速处理，模糊、复杂的请求交给小模型分析
- **自我纠错**：通过历史上下文感知意图变更，实现多轮对话的连贯理解
- **二级分类**：领域分类（一级）+ 动作分类（二级），为后续规划层提供细粒度路由

### 1.2 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户输入 + 历史上下文                          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  预处理层                                                       │
│  • 文本清洗（去空格、表情符号过滤）                               │
│  • 股票代码识别（正则匹配 6位数字 / 股票名称映射）               │
│  • 时间词提取（"最近"、"昨天"、"本周" → timeframe/date_range）   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  规则匹配引擎（RuleEngine）                                      │
│  • 关键词匹配 → 计算初始置信度                                    │
│  • 正则模式匹配 → 命中加分                                       │
│  • 实体提取 → 提取到实体加分                                     │
│  • 动作分类 → 领域下的二级动作识别                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
                    规则置信度 >= 0.85？
                    ├── 是 → 直接返回（规则短路）
                    └── 否 ↓
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  小模型分类器（ModelClassifier）                                 │
│  • 调用 DeepSeek V3 Lite                                        │
│  • 输入：当前输入 + 历史上下文 + 已提取实体                        │
│  • 输出：意图分类 + 实体提取 + 置信度                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  融合决策层（FusionLayer）                                       │
│  • 规则和模型结果一致 → 取更高置信度                              │
│  • 规则和模型结果不一致 → 取置信度高的结果                        │
│  • 实体融合 → 规则提取优先，模型补全                              │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  意图变更检测（ChangeDetector）                                  │
│  • 对比当前意图 vs 历史意图                                      │
│  • 检测意图切换（闲聊 → 投资分析）                                │
│  • 检测实体变更（symbol、timeframe 等）                          │
│  • 实体继承 → 多轮对话中继承未变更的实体                          │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
                        IntentResult
                    路由到子 Agent
```

## 2. 意图分类体系

### 2.1 一级意图（领域分类）

| 意图名称 | 说明 | 触发关键词示例 |
|---------|------|--------------|
| `investment_analysis` | 投资分析 | 分析、走势、行情、技术面、基本面、能买吗 |
| `general_chat` | 通用闲聊 | 你好、什么是、解释一下、闲聊 |
| `watchlist_manage` | 自选股管理 | 自选股、加入自选、移除自选、关注 |

### 2.2 二级意图（动作分类）

#### investment_analysis 领域

| 动作名称 | 说明 | 触发关键词示例 |
|---------|------|--------------|
| `technical_analysis` | 技术面分析 | 技术面、走势、K线、均线、MACD |
| `trade_decision` | 交易决策 | 能买吗、要不要、怎么操作、建仓、止损 |
| `pattern_recognition` | 形态识别 | 金叉、死叉、突破、破位、背离 |

#### general_chat 领域

| 动作名称 | 说明 | 触发关键词示例 |
|---------|------|--------------|
| `concept_qa` | 概念解释 | 什么是、怎么理解、解释一下 |
| `system_guide` | 系统引导 | 怎么用、功能、帮助、操作指南 |
| `chitchat` | 纯闲聊 | 你好、在吗、闲聊、问候 |

#### watchlist_manage 领域

| 动作名称 | 说明 | 触发关键词示例 |
|---------|------|--------------|
| `add_stock` | 加入自选 | 加入自选、添加自选、关注 |
| `remove_stock` | 移除自选 | 移除自选、删除自选、取消关注 |
| `list_watchlist` | 查看自选 | 自选股列表、查看自选、我的自选 |

## 3. 实体提取规则

### 3.1 实体类型

| 实体名称 | 说明 | 提取方式 |
|---------|------|---------|
| `symbol` | 股票代码 | 正则匹配 6位数字 + 股票名称映射 |
| `stock_name` | 股票名称 | 直接提取 + 代码反向映射 |
| `timeframe` | 时间周期 | 关键词映射（日线→1d，周线→1w） |
| `date_range` | 时间范围 | 关键词映射（最近一周→7d） |
| `strategy` | 策略类型 | 关键词匹配（趋势、突破、震荡） |

### 3.2 股票名称到代码映射

股票名称映射通过查询 `stock_metadata` 表实现，支持模糊匹配和别名识别：

- 精确匹配："贵州茅台" → "600519"
- 别名匹配："茅台" → "600519"
- 代码直接匹配："600519" → "600519"

### 3.3 时间周期映射

| 输入词 | 映射值 | 说明 |
|-------|-------|------|
| 日线、日K、日 | `1d` | 日线级别 |
| 周线、周K、周 | `1w` | 周线级别 |
| 月线、月K、月 | `1M` | 月线级别 |
| 默认 | `1d` | 未指定时默认日线 |

## 4. 置信度计算

### 4.1 规则匹配置信度

```
confidence = base_confidence + keyword_bonus + pattern_bonus + entity_bonus

其中：
- base_confidence: 领域基准置信度（investment_analysis: 0.85, general_chat: 0.7）
- keyword_bonus: 关键词命中加分（每命中一个关键词 +0.05，最高 +0.2）
- pattern_bonus: 正则模式命中加分（命中一个模式 +0.1）
- entity_bonus: 实体提取加分（每提取一个实体 +0.05，最高 +0.15）
```

### 4.2 规则短路阈值

当规则匹配置信度 >= 0.85 时，直接返回规则结果，跳过模型调用，实现**规则短路**优化。

### 4.3 融合决策策略

| 场景 | 处理方式 |
|------|---------|
| 规则置信度 >= 0.85 | 直接返回规则结果（规则短路） |
| 规则和模型意图一致 | 取两者更高置信度，合并实体 |
| 规则置信度 > 模型 + 0.2 | 返回规则结果 |
| 模型置信度 > 规则 + 0.2 | 返回模型结果 |
| 两者置信度接近（差值 < 0.2） | 返回模型结果（模型更擅长模糊场景） |

## 5. 意图变更检测

### 5.1 变更类型

| 变更类型 | 说明 | 示例 |
|---------|------|------|
| `intent_switch` | 意图切换 | 闲聊 → 投资分析 |
| `entity_change` | 实体变更 | symbol: 茅台 → 五粮液 |
| `entity_add` | 新实体添加 | 首次提取 symbol |
| `entity_remove` | 实体移除 | timeframe: 1d → null |

### 5.2 检测流程

```
1. 获取当前会话的历史意图状态（存储在 conversation 表或内存中）
2. 对比当前意图与历史意图
3. 对比当前实体与历史实体
4. 生成变更列表
5. 更新会话状态
```

### 5.3 实体继承策略

多轮对话中，未明确变更的实体自动继承：

```
用户1: "分析贵州茅台日线" → {symbol: "600519", timeframe: "1d"}
用户2: "再看看周线" → 继承 symbol="600519", 更新 timeframe="1w"
用户3: "不对，我问的是五粮液" → 更新 symbol="000858", 保留 timeframe="1w"
```

## 6. 数据结构

### 6.1 IntentResult

```python
@dataclass
class IntentResult:
    # 一级：领域
    intent: str                    # investment_analysis / general_chat / watchlist_manage
    
    # 二级：动作
    action: str | None             # technical_analysis / trade_decision / ...
    
    # 实体
    entities: dict                 # {symbol, stock_name, timeframe, date_range, strategy}
    
    # 置信度与来源
    confidence: float              # 0.0 - 1.0
    matched_by: str                # "rules" / "model" / "fused"
    
    # 上下文相关
    intent_changed: bool           # 是否发生意图变更
    entity_changes: list           # 实体变更详情
    needs_clarification: bool      # 是否需要澄清（V2）
    clarification_options: list    # 澄清选项（V2）
    
    # 历史继承
    inherited_entities: dict       # 从上下文继承的实体
```

### 6.2 EntityChange

```python
@dataclass
class EntityChange:
    change_type: str               # "intent_switch" / "entity_change" / "entity_add" / "entity_remove"
    entity: str | None             # 实体名称（intent_switch 时为 None）
    from_value: str | None         # 变更前的值
    to_value: str | None           # 变更后的值
    reason: str | None             # 变更原因（可选）
```

## 7. 配置文件结构

### 7.1 配置文件位置

```
python-service/
└── agents/
    └── intent_router/
        └── config.py
```

### 7.2 配置项说明

```python
# 意图配置
INTENT_PATTERNS = {
    "<intent_name>": {
        "keywords": [...],         # 关键词列表
        "patterns": [...],         # 正则模式列表
        "min_keyword_hits": 1,     # 最小关键词命中数
        "base_confidence": 0.85,   # 基准置信度
    }
}

# 动作配置
ACTION_RULES = {
    "<intent_name>": {
        "<action_name>": {
            "keywords": [...],     # 动作关键词列表
            "patterns": [...],     # 动作正则模式列表
        },
        "_default": "<default_action>"  # 默认动作
    }
}

# 实体提取规则
ENTITY_EXTRACTORS = {
    "symbol": {
        "regex": r"\b(\d{6})\b",   # 股票代码正则
        "name_mapping": {}         # 股票名称映射（从数据库加载）
    },
    "timeframe": {
        "映射表": {...}
    }
}

# 模型配置
MODEL_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": os.getenv("DEEPSEEK_API_KEY"),
    "max_tokens": 512,
    "temperature": 0.1,
    "timeout": 10,
    "context_window_size": 3       # 历史对话窗口大小
}

# 融合策略配置
FUSION_CONFIG = {
    "rule_shortcut_threshold": 0.85,    # 规则短路阈值
    "confidence_threshold": 0.2,        # 置信度差值阈值
}
```

## 8. API 接口

### 8.1 内部调用接口

```python
from agents.intent_router import IntentRouter

router = IntentRouter()

# 单轮调用
result = router.recognize(
    user_input="分析贵州茅台走势",
    conversation_history=[...],  # 历史对话消息列表
    context_state={...}          # 上下文状态（可选）
)

# 返回 IntentResult 对象
print(result.intent)           # "investment_analysis"
print(result.action)           # "technical_analysis"
print(result.entities)         # {"symbol": "600519", ...}
print(result.confidence)       # 0.95
```

### 8.2 上下文状态结构

```python
context_state = {
    "last_intent": "investment_analysis",
    "last_action": "technical_analysis",
    "entities": {
        "symbol": "600519",
        "stock_name": "贵州茅台",
        "timeframe": "1d"
    },
    "updated_at": "2024-01-01 12:00:00"
}
```

## 9. 集成方式

### 9.1 集成到 chat_service

在 `chat_service.py` 的 `send_message` 方法中集成：

```python
def send_message(conv_id: int, content: str):
    # 1. 获取历史对话
    history = get_recent_messages(conv_id, limit=6)  # 最近3轮（每轮2条）
    
    # 2. 获取上下文状态
    context_state = get_conversation_context(conv_id)
    
    # 3. 意图识别
    router = IntentRouter()
    intent_result = router.recognize(content, history, context_state)
    
    # 4. 更新上下文状态
    update_conversation_context(conv_id, {
        "last_intent": intent_result.intent,
        "last_action": intent_result.action,
        "entities": intent_result.entities,
    })
    
    # 5. 路由到子 Agent
    if intent_result.intent == "investment_analysis":
        return investment_agent.analyze(intent_result)
    elif intent_result.intent == "general_chat":
        return chat_agent.chat(intent_result)
    elif intent_result.intent == "watchlist_manage":
        return watchlist_agent.manage(intent_result)
```

## 10. 性能优化策略

### 10.1 规则短路

- 规则置信度 >= 0.85 时直接返回，跳过模型调用
- 预期 70%+ 请求走规则短路路径

### 10.2 输入预处理优化

- 文本截断：历史对话每条消息截断到 100 字符
- 停用词过滤：过滤无意义词汇（的、了、是等）

### 10.3 模型调用优化

- 小模型选择：DeepSeek V3 Lite，成本低、速度快
- 强制 JSON 输出：减少 token 消耗
- 超时降级：模型调用超时（>10s）时返回规则结果

### 10.4 缓存策略（V2）

- 相同输入直接返回缓存结果
- 缓存有效期 5 分钟

## 11. 扩展指南

### 11.1 新增意图

1. 在 `config.py` 的 `INTENT_PATTERNS` 中添加新意图配置
2. 在 `ACTION_RULES` 中添加该意图下的动作规则
3. 如果需要，添加对应的实体提取规则
4. 无需修改代码，只需更新配置文件

### 11.2 新增动作

1. 在 `config.py` 的 `ACTION_RULES` 中添加新动作
2. 定义动作关键词和正则模式
3. 在子 Agent 中实现对应的处理逻辑

### 11.3 更新关键词

直接修改 `config.py` 中的关键词列表，无需重启服务（热加载）。

## 12. 错误处理与降级

### 12.1 模型调用失败

- 超时：返回规则结果
- API Key 无效：记录日志，返回规则结果
- 网络错误：记录日志，返回规则结果

### 12.2 实体提取失败

- 股票名称无法映射：返回意图和动作，entities 中 symbol 为 None
- 后续子 Agent 收到 None 时进行澄清

### 12.3 低置信度处理

- 规则和模型置信度都低于 0.5：返回 `general_chat`（闲聊兜底）
- 记录日志用于后续优化

## 13. 监控与日志

### 13.1 日志记录

```python
# 意图识别日志
logging.info(f"Intent recognition: intent={result.intent}, action={result.action}, "
             f"confidence={result.confidence}, matched_by={result.matched_by}")

# 模型调用日志
logging.info(f"Model call: input={user_input[:50]}, latency={latency}ms, "
             f"tokens_used={tokens_used}")

# 意图变更日志
logging.info(f"Intent changed: {intent_result.entity_changes}")
```

### 13.2 监控指标

| 指标 | 说明 |
|------|------|
| `intent_recognition_latency` | 意图识别总耗时 |
| `rule_engine_latency` | 规则匹配耗时 |
| `model_call_latency` | 模型调用耗时 |
| `rule_shortcut_rate` | 规则短路命中率 |
| `model_call_count` | 模型调用次数 |
| `intent_distribution` | 意图分布统计 |

## 14. 测试策略

### 14.1 单元测试

- 规则匹配引擎：测试各种输入的分类结果
- 实体提取：测试股票代码、时间周期的提取
- 融合决策：测试规则和模型不一致时的处理
- 意图变更检测：测试多轮对话的变更识别

### 14.2 集成测试

- 端到端测试：完整意图识别流程
- 性能测试：规则短路命中率、延迟

### 14.3 Mock 测试

- 小模型调用使用 mock，避免实际 API 调用成本
- 测试降级策略的正确性

## 15. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v1.0 | 2024-07 | 初始版本：规则匹配 + 小模型分类 + 融合决策 + 意图变更检测 |
| v1.1 | 2024-08 | 添加动作分类（二级意图） |
| v2.0 | 2024-09 | 添加澄清式提问、结果缓存 |
| v2.1 | 2024-10 | 添加多轮规划支持 |