# Investment Compass 后端 API 全量参考文档

> 本文档基于代码实际核查，覆盖 **Java（:8879）+ Python（:8002）** 两个后端的全部 REST 接口、WebSocket 行情通道与 SSE 流式协议，用于前端联调与后端维护。
>
> 统计：REST **44** 个（Java 17 / Python 27）+ WebSocket **1** 个 + SSE 事件协议 **1** 套。

---

## 0. 总体架构与路由

### 0.1 双后端拓扑

```
前端 (Vite :5173)
   │  Vite Proxy 按路径前缀分流
   ├── /api/stock/*  /api/market/*  /api/watchlist/*  /api/monitor/*   → Java  (Spring Boot :8879, context-path=/api)
   └── /api/* (其余)                                                    → Python (FastAPI :8002)
   └── /ws/quote (WebSocket，不走 proxy 时直连 Java :8879)
```

### 0.2 通用响应格式

两个后端统一 `{code, message, data}` 包装（Java `BaseResponse` / Python `BaseResponse`）：

```json
{ "code": 0, "message": "success", "data": { } }
```

| code | 含义 |
|---|---|
| `0` | 成功 |
| `-1` | 业务/参数错误（message 携带原因） |
| `404` | 资源不存在（仅 Python 会话类接口使用） |
| HTTP 500 | 未捕获异常（Python 全局 handler 返回 `code=-1`） |

### 0.3 ⚠️ 端口一致性（联调前置）

| 位置 | 端口 |
|---|---|
| `python-service/main.py` 底部硬编码 | **8002** |
| `frontend/vite.config.ts` proxy | **8002** |
| `python-service/start.sh` 默认 `PORT` | **8000**（`PORT` 环境变量可覆盖） |
| `python-service/.env` | `PORT=8000` |

> **结论**：仅当 `python main.py` 或 `PORT=8002 ./start.sh` 启动时前端可连通；按 `start.sh` 默认启动（8000）则前端 proxy（8002）连不上。**统一端口是联调第一前置项。**

---

## 1. Java 后端（Spring Boot，:8879，context-path=`/api`）

### 1.1 股票数据 `/stock/*`（[StockController](../java-backend/src/main/java/com/xiaosuo/investmentcompass/controller/StockController.java)）

#### GET `/api/stock/search` — 股票搜索
| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `keyword` | string | ✅ | - | 代码或名称 |
| `limit` | int | - | 10 | 返回条数上限 |

`data`：`[{symbol, stockName}]`

#### GET `/api/stock/quote` — 实时行情（快照）
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `symbols` | string | ✅ | 逗号分隔，如 `000001.SZ,600519.SH` |

`data`：`[{symbol, tradeDate, close, changePct, preClose}]`

#### GET `/api/stock/kline` — K 线历史（主力数据源）
| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `symbol` | string | ✅ | - | 可带/不带交易所后缀（自动补全） |
| `timeframe` | string | - | `1d` | `1m/5m/15m/30m/1h/4h/1d` |
| `startDate` | string | - | - | `YYYY-MM-DD`；与 endDate 同时给则忽略 limit |
| `endDate` | string | - | - | 同上 |
| `limit` | int | - | 120 | 返回条数 |

`data`：`{symbol, timeframe, bars:[{trade_date, ts_open, open, high, low, close, volume, amount, pct_chg}]}`

#### GET `/api/stock/detail/{symbol}` — 个股详情聚合
聚合 `stock_metadata` + `market_data` 最新 1d。
`data`：`{symbol, stockName, industry, listDate, latestClose/Open/High/Low/Volume/Amount/PctChg, latestTradeDate, change, changePercent}`

#### GET `/api/stock/indicators/{symbol}` — 技术指标
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | ✅ | `ma` / `ema` / `macd` |
| `period` | int | - | 指标周期（ma/ema） |
| `limit` | int | - | 默认 120 |

`data`：`{symbol, type, tradeDates[], values[]（ma/ema）, dif[]/dea[]/macd[]（macd）}`

### 1.2 自选股 `/watchlist/*`（[WatchlistController](../java-backend/src/main/java/com/xiaosuo/investmentcompass/controller/WatchlistController.java)）

| 接口 | 方法 | 请求体/参数 | 返回 data |
|---|---|---|---|
| `/api/watchlist/list` | GET | - | `[{id, symbol, groupName, sortOrder, note, createdAt, updatedAt}]` |
| `/api/watchlist/add` | POST | `{symbol, groupName}` | 新增记录 |
| `/api/watchlist/remove` | POST | `{symbol, groupName}` | `true` |
| `/api/watchlist/reorder` | POST | `{items: [{id, sortOrder}]}` | `null` |

### 1.3 大盘行情 `/market/*`（[MarketBoardController](../java-backend/src/main/java/com/xiaosuo/investmentcompass/controller/MarketBoardController.java)）

#### GET `/api/market/indices` — 主要指数行情
`data`：`[{symbol, stockName, close, changePct, tradeDate}]`（上证/深成/创业板/科创50）

#### GET `/api/market/ranking` — 涨跌幅排名
| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `type` | string | - | `top_gainers` | `top_gainers` 涨幅榜 / `top_losers` 跌幅榜 |
| `limit` | int | - | 20 | 条数 |

`data`：`[{symbol, tradeDate, close, changePct, preClose}]`

### 1.4 数据监控 `/monitor/*`（[MonitorController](../java-backend/src/main/java/com/xiaosuo/investmentcompass/controller/MonitorController.java)）

| 接口 | 方法 | 参数 | 返回 data |
|---|---|---|---|
| `/api/monitor/overview` | GET | - | `Map`（总览统计） |
| `/api/monitor/backfill-progress` | GET | - | `Map`（回填进度） |
| `/api/monitor/coverage` | GET | `limit=50` | `Map`（覆盖度） |
| `/api/monitor/quality-issues` | GET | `status?` `issueType?` `symbol?` | `[{id, symbol, issueType, status, ...}]` |
| `/api/monitor/quality-issues/{id}/status` | POST | path `id` + query `status` | `true` |

### 1.5 WebSocket `/ws/quote` — 实时行情推送

连接：`ws://localhost:8879/ws/quote`（允许任意来源）。

**客户端 → 服务端消息**：
```json
{ "type": "subscribe",   "symbols": ["600519", "000001.SZ"] }
{ "type": "unsubscribe", "symbols": ["600519"] }
{ "type": "ping" }
```

**服务端响应**：`ping` → `{"type":"pong"}`；订阅的股票有行情更新时推送（`RealtimeQuoteMessage`）。

---

## 2. Python 后端（FastAPI，:8002）

### 2.1 健康检查

#### GET `/health`
`data`：`{service: "finagentos-python", status: "ok", version: "0.2.0"}`

### 2.2 偏好记忆 `/api/preferences`（前端问卷初始化）

#### GET `/api/preferences` — 读取偏好
`data`：`{initialized: bool, sections: {风险偏好: "...", 决策风格: "...", 关注板块与标的: "...", 分析深度偏好: "..."}}`
> `initialized=false`（文件缺失或仍为"待确认"占位）→ 前端弹问卷。

#### POST `/api/preferences` — 问卷初始化（覆盖式，自动备份 .bak）
请求体：
```json
{
  "risk_preference": "稳健偏平衡，单笔最大可接受回撤 5-10%",
  "decision_style": "右侧确认入场，低频中长线",
  "watch_sectors": "科技、消费、医药",
  "watch_stocks": "600519",
  "analysis_depth": "结论 + 关键支撑/阻力"
}
```
`data`：`{path: "memories/preferences.md", content: "写入内容"}`；失败 `code=1`。

### 2.3 数据同步 `/api/fetch/*`

| 接口 | 方法 | 参数/请求体 | 返回 data |
|---|---|---|---|
| `/api/fetch/market` | POST | `{symbols: ["000001", "600519"]}` | `{records_fetched}` |
| `/api/fetch/market` | GET | `symbols`（逗号分隔，必填） | 同上（Java cron 触发友好） |
| `/api/fetch/batch` | POST | `{symbols, start_year, end_year, concurrency=2}` | `[{symbol, success, records_fetched, message, task_id}]` |
| `/api/fetch/batch/status` | GET | `symbols`、`start_year`、`end_year`（均必填） | `[{id, symbol, start_year, end_year, current_year, status, records_fetched, retry_count, error_msg, updated_at}]` |
| `/api/fetch/sync` | POST | `{symbol}` | 异步触发单只同步，`{message}` |

### 2.4 行情与 K 线（⚠️ 死接口标注见 §5）

#### GET `/api/quote/realtime`
参数：`symbols`（逗号分隔，必填）。`data`：`[{symbol, close, change_pct, pre_close, trade_date}]`
> ⚠️ 被 Vite proxy `/api/stock` 规则外的 `/api/*` 走 Python，但 Java 亦有 `/api/stock/quote`；前端实际走 Java。

#### GET `/api/kline/history`
参数：`symbol`、`timeframe=1d`（`1d/D/daily`）、`start_date`、`end_date`、`limit=120`（1-1000）。
`data`：`{symbol, timeframe, bars:[{...}]}`（按日期升序）
> ⚠️ 前端 K 线实际走 Java `/api/stock/kline`，本接口被 proxy 规则屏蔽。

### 2.5 股票元数据 `/api/stock/*`

| 接口 | 方法 | 参数 | 返回 data |
|---|---|---|---|
| `/api/stock/search` | GET | `keyword`、`limit=10` | `[{symbol, stockName}]` ⚠️ 死接口 |
| `/api/stock/init-metadata` | POST | - | 全量同步 A 股品种到 `stock_metadata`，`{total_count, success_count, failed_count}` |

### 2.6 对话管理 `/api/chat/*`

#### 会话 CRUD
| 接口 | 方法 | 参数/请求体 | 返回 data |
|---|---|---|---|
| `/api/chat/conversation` | POST | `{title}` | 新建会话对象 |
| `/api/chat/conversation/list` | GET | `status=1`（1 活跃 / 2 归档） | 会话列表 |
| `/api/chat/conversation/{conv_id}` | GET | path | 会话详情（`404`=不存在） |
| `/api/chat/conversation/{conv_id}/archive` | PUT | path | `{id, status: 2}` |
| `/api/chat/conversation/{conv_id}` | DELETE | path | `{id, deleted: true}` |

会话对象：`{id, title, user_id, status, summary, token_count, message_count, created_at, updated_at}`

#### 消息
| 接口 | 方法 | 参数/请求体 | 返回 data |
|---|---|---|---|
| `/api/chat/conversation/{conv_id}/message` | GET | `page=1`、`pageSize=30`（≤100） | `{items, page, page_size, total}`；消息含 `card_data`（JSON） |
| `/api/chat/conversation/{conv_id}/message` | POST | `{content, content_type="text"}` | `{user_message, assistant_message}`（非流式） |
| `/api/chat/conversation/{conv_id}/message/stream` | POST | 同上 | **SSE** 流式（协议见 §3） |
| `/api/chat/{conversation_id}/resume` | POST | `{decisions: [{type: "approve"\|"reject"\|"respond", message?}]}` | **SSE** 续流（HITL） |
| `/api/chat/message` | POST | `{content, title?}` | 创建会话并发送 |

消息字段：`{id, conversation_id, role, content, content_type, card_data, token_count, sequence, parent_id, tool_name, tool_result, created_at}`

### 2.7 资讯与研报

#### GET `/api/news/list`
参数：`symbol?`（600519）、`source?`（`em_news`/`cls_telegraph`/`em_global`）、`days=7`、`limit=100`（≤500）。
`data`：`{total, items:[{...}]}`；DB 不足时自动 AkShare 拉取入库。

#### GET `/api/research/list`
参数：`symbol?`、`institute?`（模糊，如"中信"）、`rating?`（买入/增持/中性/减持/卖出）、`days=90`（≤730）、`limit=200`（≤1000）。
`data`：`{total, items:[{...}]}`

#### POST `/api/news/sync`
请求体：`{symbols: ["600519"]}`（可空）。触发全量资讯同步（财联社/东财/研报/个股新闻）。`data`：`{source: count, ...}`

### 2.8 演示级数据源 `/api/demo/*`（DEMO 标注）

> 本组接口为**演示级实现**（代码注释标注 DEMO），供前端技术面数据看板开发联调；生产环境需替换/校验数据源（[services/demo_flow_service.py](../python-service/services/demo_flow_service.py)）。

#### GET `/api/demo/fundflow` — 个股资金流向（DEMO）
参数：`symbol`（必填）、`days=10`（1-30）。
- 主源东财逐日序列 → `mode:"daily"`，`daily:[{date, main_net, super_net, large_net, medium_net, small_net, main_net_pct}]` + `summary:{3d, 5d, 10d}`
- 失败回退同花顺当日快照 → `mode:"snapshot"`，`snapshot:{name, price, change_pct, turnover, inflow, outflow, net, amount}`
- 双源失败 → `data.error=true`

#### GET `/api/demo/shareholders` — 股东户数历史（DEMO）
参数：`symbol`（必填）。
`data`：`{symbol, rows:[{date, count, change, change_pct}]}`（最近 20 期）

---

## 3. SSE 流式对话协议（Python `/api/chat/.../message/stream`、`/resume`）

响应 `Content-Type: text/event-stream`，`data: {json}\n\n`。事件类型：

| 事件 | 字段 | 说明 |
|---|---|---|
| `chunk` | `chunk` | 主 Agent 回复文本增量 |
| `subagent_started` | `subagent`、`task_id` | 子 Agent 启动 |
| `subagent_completed` | `subagent`、`task_id` | 子 Agent 完成 |
| `subagent_result` | `subagent`、`task_id`、`result` | 结构化结果（含 `trace_id`） |
| `stage` | `subagent`、`stage`、`status`、`score?`、`direction?`、`stock_code?`、`stock_name?` | 子 Agent 内部阶段（diagnosis/technical 等） |
| `interrupt` | `data`（HITLRequest）、`thread_id?` | 估值完成征求决策；`data.action_requests` + `data.review_configs` |
| `done` | `interrupted: bool` | 流结束 |

**HITL 交互流程**：`interrupt` → 前端展示确认卡片 → `POST /resume`（body 携带用户决策）→ 续流 → 结束。

前端实现参考：[useChatStream.ts](../frontend/src/hooks/useChatStream.ts)。

---

## 4. 前端可达性对照（Vite Proxy 实际分流）

| 前端请求路径 | 实际后端 | 状态 |
|---|---|---|
| `/api/chat/*` `/api/preferences` `/api/news/*` `/api/research/*` `/api/fetch/*` | Python :8002 | ✅ 可达 |
| `/api/stock/*` `/api/market/*` `/api/watchlist/*` `/api/monitor/*` | Java :8879 | ✅ 可达 |
| `/api/quote/realtime` | Python（未被 /api/stock 截走） | ✅ 可达（但前端行情可走 Java） |
| `/api/kline/history` `/api/stock/search` | ⚠️ 匹配 Java 前缀规则 → **到不了 Python** | ❌ 死接口 |
| `/ws/quote` | Java 直连（不经 proxy） | ✅ |

**死接口**：Python 的 `/api/stock/search`、`/api/kline/history`（`/api/quote/realtime` 不受影响）被 Vite `/api/stock` 规则屏蔽。功能由 Java 同名接口覆盖，不影响使用；仅造成归属混淆，建议后续统一或标注。

---

## 5. 未接入前端的功能清单（联调待办）

| 功能 | 接口 | 前端现状 |
|---|---|---|
| 偏好问卷 | Python `/api/preferences` GET/POST | 后端已备，前端未接（首次进入触发，可跳过） |
| 实时行情 | Java `/api/stock/quote` / WS `/ws/quote` | 未接（TradingView 目前仅 K 线） |
| 自选股 | Java `/api/watchlist/*` | 未接 |
| 大盘看板 | Java `/api/market/*` | 未接 |
| 新闻/研报 | Python `/api/news/list`、`/api/research/list` | 未接 |
| 数据监控 | Java `/api/monitor/*` | 未接 |
| 技术面看板数据源（DEMO） | Python `/api/demo/fundflow`、`/api/demo/shareholders` | **后端已备（demo）**，前端 5 卡看板待实现 |
