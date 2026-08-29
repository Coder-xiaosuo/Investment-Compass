# PA分析Agent（PA Analyzer Agent）

## 职责定位

系统的"投资大脑"。接收数据获取 Agent 提供的结构化行情数据，**先客观算特征、后 AI 做判断**，生成包含操作方向、置信度、理由、止损止盈位的决策卡片。

> 设计来源：参考 PA Agent（开源AI K线分析系统）两阶段分析管线 + 特征预计算 + 结构化JSON Schema + 经验库注入等经实战验证的模式。

---

## 简化架构说明（2026-07-13）

根据最新决策，**不再保留独立的数据获取Agent**。数据获取直接集成在 PA 分析管线中，作为分析流程的第一步：

```
用户请求 → [AkShare 拉取行情] → [特征计算] → [Stage1 诊断] → [Stage2 决策] → 决策卡片
                                           └── 全部在 pa-analyzer 内部完成 ──┘
```

**市场边界**：仅 A 股（AkShare 数据源），不做 TradingView / MT5 / yfinance。
**Agent 架构**：pa-analyzer 是当前唯一的 Python Agent，其他 Agent 骨架保留为后续预留。

### 管线内数据获取流程

```
请求: symbol="600519", timeframe="1d"
  │
  ▼
akshare.stock_zh_a_hist(symbol, period="daily", adjust="qfq")
  │
  ▼
清洗 → 标准化 → Parquet 缓存 → data_hash 指纹
  │
  ▼
特征计算 (market_features + kline_features + TA-Lib)
  │
  ▼
Stage1 诊断 → Stage2 决策 → 决策卡片
```

### 已从 PA Agent 项目复用的代码

| 文件 | 来源 | 用途 |
|------|------|------|
| `agents/shared/base.py` | PA Agent | KlineBar, KlineFrame, DataSource |
| `agents/shared/datetime_ts.py` | PA Agent | 时间戳工具 |
| `agents/shared/ashare_common.py` | PA Agent | A 股标准化 |
| `agents/shared/ashare_limits.py` | PA Agent | A 股交易规则 |
| `agents/shared/kline_adjust.py` | PA Agent | 复权 |
| `agents/shared/atr.py` | PA Agent | ATR 指标 |
| `agents/shared/ema.py` | PA Agent | EMA 指标 |
| `agents/pa-analyzer/ai/market_features.py` | PA Agent | 市场特征 400行 |
| `agents/pa-analyzer/ai/kline_features.py` | PA Agent | K线特征 300行 |
| `agents/pa-analyzer/ai/prompts/schemas.py` | PA Agent | JSON Schema |
| `agents/pa-analyzer/ai/decision_stance.py` | PA Agent | 决策立场 |
| `agents/pa-analyzer/ai/token_counter.py` | PA Agent | Token计数 |
| `agents/pa-analyzer/orchestrator/two_stage.py` | PA Agent | 两阶段管线 1200行 |


## 架构：两阶段管线

不依赖 AI 一次性输出"诊断+决策"。而是强制分两步，中间插入策略逻辑判断：

```
数据获取Agent
       |
       v  DataFrame + data_hash
+---------------------------+
| Step 0: 特征预处理层         |
| (纯计算，不调用AI)          |
| market_features.py          |
|   - 摆动点识别              |
|   - 突破事件检测            |
|   - 支撑/阻力结构位         |
| kline_features.py           |
|   - 单K线几何特征           |
|   - 多K线关系（孕线/包含）   |
| indicators/ (TA-Lib)       |
|   - MA / MACD / RSI        |
|   - 布林带 / KDJ / ATR     |
| 输出: features dict         |
+----------------------------+
       |
       v  特征向量
+----------------------------+
| Step 1: 市场诊断 (Stage1)   |
| (调用LLM，返回结构化JSON)   |
| Prompt: 特征 + 趋势判断指令  |
| 输出: diagnosis JSON        |
+----------------------------+
       |
       v  诊断JSON
+----------------------------+
| Step 1.5: 策略路由          |
| 趋势跟踪策略 -> 趋势分析     |
| 震荡交易策略 -> 区间分析     |
| 经验库匹配 -> 注入历史案例   |
+----------------------------+
       |
       v  策略文件 + 经验案例
+----------------------------+
| Step 2: 交易决策 (Stage2)   |
| (调用LLM，输出决策卡片)     |
| 输出: decision_card JSON    |
+----------------------------+
       |
       v  决策卡片
+----------------------------+
| Step 3: 验证 + 持久化       |
| JsonValidator - Schema校验  |
| CoherenceCheck - 逻辑一致性 |
| AuditChain - 写入审计链     |
+----------------------------+
```

### 为什么必须两阶段

| 模式 | 问题 | 两阶段如何解决 |
|------|------|-------------|
| 一次性输出 | AI 常跳过诊断直接写结论 | 两阶段强制先诊断后决策，独立的 Prompt |
| 诊断质量差 | AI 偷懒，趋势判断模糊 | Stage1 有独立 Schema 约束输出结构 |
| 决策不可追溯 | 不知道为什么得出这个结论 | 决策卡片含完整推理链 |
| 策略混用 | 震荡市用趋势策略 | 诊断后再路由策略，量体裁衣 |

---

## 核心能力

### 1. 特征预处理（纯计算，不调用AI）

接收 DataFrame 后，先**客观计算**以下特征，再送入 AI：

| 模块 | 计算内容 | 参考实现 |
|------|---------|---------|
| market_features | 摆动点(SwingPivot)、突破事件(BreakoutEvent)、结构位(MM)、HL计数 | PA Agent 400行，可直接复用 |
| kline_features | 单K线几何特征（影线/实体/位置）、多K线关系（孕线/包含/接力） | PA Agent 300行，可直接复用 |
| trend_context | 趋势结构分析、通道/震荡识别 | 参考 PA Agent 实现 |
| structure_levels | 支撑/阻力自动识别 | 参考 PA Agent 实现 |
| indicators | MA, MACD, RSI, 布林带, KDJ, ATR (TA-Lib) | 标准 TA-Lib，自行实现 |

### 2. 结构化决策卡片生成

两阶段输出均用 JSON Schema 约束。

**Stage1 诊断输出：**

```json
{
    "market_regime": "trending",
    "trend_direction": "bullish",
    "structure": { "type": "impulsive", "wave_count": 3 },
    "key_levels": [{"price": 1850, "type": "resistance"}],
    "pattern": "bull_flag",
    "confidence": 0.75
}
```

**Stage2 决策输出（决策卡片）：**

```json
{
    "action": "BUY",
    "price": 1856.00,
    "stop_loss": 1810.00,
    "take_profit": 1950.00,
    "confidence": 0.78,
    "position_size_pct": 5,
    "reasons": [
        "MACD金叉确认，红柱持续放大",
        "MA20上穿MA60，均线多头排列",
        "成交量较前5日均值放大15%"
    ],
    "summary": "均线多头排列，短期动能强劲，建议逢回调加仓"
}
```

### 3. 决策链推理（二元决策树）

分析逻辑通过**决策树文本文件**定义，而非硬编码。AI 逐级回答「是/否/中性」，路由到不同子节点，最终到达终端（交易/等待/拒绝）。分析逻辑外置到文件，修改无需改代码。

### 4. 验证体系（多层）

| 验证层 | 拦截问题 | 处理方式 |
|--------|---------|---------|
| JSON 语法 | 输出不是合法 JSON | 尝试修复，失败则重试 |
| Schema 校验 | 缺字段 / 枚举值不合法 | 带反馈重试（最多3次） |
| 一致性检查 | BUY 但置信度<0.3 | 拒绝，要求重新推理 |
| 语义检查 | 上升趋势但均线空头排列 | 拒绝，重新生成 |
| 网络错误检测 | API 超时/断连 | 自动重试 + 供应商回退 |

### 5. 经验库注入（可选增强）

每次分析时自动匹配历史经验。按市场状态分类（trending_bull / trending_bear / ranging / volatile），Stage2 构建 Prompt 时加载最相似的前 N 个案例作为 few-shot 示例。

---

## 输入/输出

### 输入

```json
{
    "symbol": "600519",
    "data": "DataFrame",
    "data_hash": "sha256...",
    "options": {
        "decision_stance": "conservative",
        "enable_experience": true
    },
    "trace_id": "TXN-20260713-001"
}
```

### 输出

```json
{
    "trace_id": "TXN-20260713-001",
    "card": {
        "action": "BUY",
        "price": 1856.00,
        "stop_loss": 1810.00,
        "take_profit": 1950.00,
        "confidence": 0.78,
        "position_size_pct": 5,
        "reasons": [
            "MACD金叉确认，红柱持续放大",
            "MA20上穿MA60，均线多头排列",
            "成交量较前5日均值放大15%"
        ],
        "summary": "均线多头排列，短期动能强劲"
    },
    "features": {
        "ma20": 1830,
        "ma60": 1790,
        "atr14": 25.5,
        "volume_ratio": 1.15
    },
    "diagnosis": {
        "market_regime": "trending",
        "trend_direction": "bullish",
        "confidence": 0.75
    },
    "usage": {
        "prompt_tokens": 4520,
        "completion_tokens": 680,
        "total_tokens": 5200
    },
    "audit_hash": "sha256..."
}
```

---

## 边界约束

| 约束 | 说明 |
|------|------|
| 不直接访问数据源 | 必须通过数据获取 Agent 获取行情 |
| 不直接修改数据库 | 决策持久化由 audit-harness (Java) 处理，通过 REST API 调用 |
| 不执行交易 | 决策卡片提交给 quant-executor Agent，人点击确认后才执行 |
| 输出必含 confidence + reasons | 不能只给结论，必须附推理过程 |
| 诊断和决策必须分离 | 不允许一个 Prompt 输出全部，必须先诊断后决策 |
| 所有输出都有审计链 | trace_id 贯穿全流程 |

---

## 实现路径

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| P0 | 特征预处理层 | market_features.py + kline_features.py（复制PA Agent代码微调） |
| P0 | 两阶段 Prompt 模板 | prompts/stage1_diagnosis.txt + prompts/stage2_decision.txt |
| P1 | JSON Schema + 验证器 | schemas/ + validator.py |
| P1 | LLM 客户端 + 流式 | deepseek_client.py（参考PA Agent） |
| P2 | 决策树路由 | decision_tree/ + router.py |
| P2 | 经验库 | experience/ + reader.py |
