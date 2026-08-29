# Investment Compass API 文档

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          前端 (Vite :5173)                          │
│                     React + Lightweight Charts                      │
└──────┬──────────────────────────┬──────────────────────────────────┘
       │  Vite Proxy             │  Vite Proxy
       │  /api/chat/* → Python   │  /api/stock/* → Java
       │  /api/kline/* → Python  │  /api/market/* → Java
       │  /api/fetch/* → Python  │  /api/watchlist/* → Java
       │  /api/quote/* → Python  │  /api/monitor/* → Java
       ▼                          ▼
┌──────────────────┐    ┌──────────────────────────┐
│ Python Service   │    │   Java Backend            │
│ (FastAPI :8002)  │    │ (Spring Boot :8879)       │
│                  │    │                           │
│ 数据源层          │    │ 缓存层 (Redis)            │
│ AkShare          │    │ 业务逻辑层                │
│ 数据服务层        │    │ 计算引擎 (技术指标)        │
│ Agent 服务       │    │ K线 API (主力数据源)       │
└──────┬───────────┘    └──────────┬────────────────┘
       │ 读写                      │ 读写
       ▼                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          MySQL (investment_compass)                   │
│    market_data | stock_metadata | conversation | message |           │
│    watchlist | data_quality_issue | sync_task                        │
└──────────────────────────────────────────────────────────────────────┘
```

- **Python 服务** (`:8002`)：数据采集层，负责从 AkShare 拉取 A 股行情数据，写入 MySQL；提供 Agent 对话等服务
- **Java 后端** (`:8879`, context-path: `/api`)：业务逻辑层，从 MySQL 读取数据，提供 REST API 和 WebSocket 实时推送；由 Vite 代理的 `/api` 前缀路由到 Python，Java 通过直接 CORS 调用

---

## 一、Python 服务端 API（FastAPI）

**基础信息**
- 服务地址：`http://localhost:8002`
- 框架：FastAPI
- 全局统一响应格式：

```json
{
  "code": 0,        // 0=成功, -1=失败, 404=未找到
  "message": "success",
  "data": { ... }   // 具体业务数据
}
```

### 1.1 健康检查

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 服务存活检查 |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "service": "finagentos-python",
    "status": "ok",
    "version": "0.2.0"
  }
}
```

---

### 1.2 数据同步（行情拉取）

#### POST `/api/fetch/market` — 增量行情同步

触发指定股票的增量行情更新，从 AkShare 拉取最新数据写入 MySQL。

**Request Body:**
```json
{
  "symbols": ["000001", "600519"]
}
```

**Response:**
```json
{
  "code": 0,
  "message": "同步完成",
  "data": { "records_fetched": 245 }
}
```

---

#### GET `/api/fetch/market` — GET 方式增量同步

**Query Parameters:**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `symbols` | string | 是 | 逗号分隔的股票代码，如 `000001,600519` |

适用于 Java 端 `DataSyncJob` 定时任务通过 `curl` 触发。

---

#### POST `/api/fetch/batch` — 批量历史回填

批量拉取历史日线数据，支持断点续传和并发。

**Request Body:**
```json
{
  "symbols": ["000001", "600519"],
  "start_year": 2023,
  "end_year": 2024,
  "concurrency": 2
}
```

**Response:**
```json
{
  "code": 0,
  "message": "批量同步完成: 2/2 成功, 共 480 条记录",
  "data": [
    { "symbol": "000001", "success": true, "records_fetched": 240, "message": "", "task_id": 1 },
    { "symbol": "600519", "success": true, "records_fetched": 240, "message": "", "task_id": 2 }
  ]
}
```

---

#### GET `/api/fetch/batch/status` — 批量回填任务状态

**Query Parameters:**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `symbols` | string | 是 | 逗号分隔的股票代码 |
| `start_year` | int | 是 | 起始年份 |
| `end_year` | int | 是 | 结束年份 |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "id": 1,
      "symbol": "000001",
      "start_year": 2023,
      "end_year": 2024,
      "current_year": 2024,
      "status": "completed",
      "records_fetched": 240,
      "retry_count": 0,
      "error_msg": null,
      "updated_at": "2024-01-15T10:30:00"
    }
  ]
}
```

---

### 1.3 行情数据

#### GET `/api/quote/realtime` — 实时行情

**Query Parameters:**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `symbols` | string | 是 | 逗号分隔的股票代码 |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "symbol": "000001",
      "close": 12.34,
      "change_pct": 2.5,
      "pre_close": 12.04,
      "trade_date": "2024-01-15"
    }
  ]
}
```

---

#### GET `/api/stock/kline` — K 线历史数据（主力接口）

**说明：** 由 Java 后端统一提供，取代 Python 的 `/api/kline/history`。支持不带交易所后缀的股票代码自动补全。

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 股票代码，可带或不带交易所后缀，如 `000001.SZ` 或 `000001` |
| `timeframe` | string | 否 | `1d` | K线周期，支持 `1m/5m/15m/30m/1h/4h/1d/1w/1M` |
| `start_date` | string | 否 | - | 开始日期 `YYYY-MM-DD`，与 end_date 同时提供时忽略 limit |
| `end_date` | string | 否 | - | 结束日期 `YYYY-MM-DD`，与 start_date 同时提供时忽略 limit |
| `limit` | int | 否 | 120 | 返回条数上限，仅无日期范围时生效 |

**Response 数据项：** 在 `bars[]` 中每项新增如下字段：

| 字段 | 类型 | 描述 |
|------|------|------|
| `volume_ratio` | double\|null | 量比 |
| `turnover_rate` | double\|null | 换手率（%） |
| `closed` | int\|null | 1=已收盘, 0=正在形成 |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "symbol": "000001",
    "timeframe": "1d",
    "bars": [
      {
        "symbol": "000001",
        "trade_date": "2024-01-02",
        "timeframe": "1d",
        "ts_open": 1704153600000,
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1000000,
        "amount": 10000000.0,
        "pct_chg": 2.0,
        "closed": 1
      }
    ]
  }
}
```

---

### 1.4 股票元数据

#### GET `/api/stock/search` — 搜索股票

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `keyword` | string | 是 | - | 搜索关键词（股票代码或名称） |
| `limit` | int | 否 | 10 | 返回条数上限 |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": [
    { "symbol": "000001", "stockName": "平安银行" },
    { "symbol": "600519", "stockName": "贵州茅台" }
  ]
}
```

---

#### POST `/api/stock/init-metadata` — 全量初始化品种列表

从 AkShare 全量拉取 A 股品种列表并写入 `stock_metadata` 表。

**Response:**
```json
{
  "code": 0,
  "message": "同步完成: 5000 成功, 0 失败",
  "data": {
    "total_count": 5000,
    "success_count": 5000,
    "failed_count": 0
  }
}
```

---

### 1.5 对话管理（Chat / Agent）

#### POST `/api/chat/conversation` — 创建会话

**Request Body:**
```json
{ "title": "新会话" }
```

**Response:** `{ "code": 0, "message": "success", "data": { "id": 1, "title": "新会话", "status": 1, "created_at": "...", "updated_at": "..." } }`

---

#### GET `/api/chat/conversation/list` — 会话列表

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `status` | int | 否 | 1 | 1-活跃, 2-归档 |

---

#### GET `/api/chat/conversation/{conv_id}` — 会话详情

**Path Parameters:** `conv_id` (int) — 会话 ID

---

#### PUT `/api/chat/conversation/{conv_id}/archive` — 归档会话

归档后 `status` 置为 2。

---

#### DELETE `/api/chat/conversation/{conv_id}` — 删除会话

---

#### GET `/api/chat/conversation/{conv_id}/message` — 获取消息列表

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `page` | int | 否 | 1 | 页码 |
| `pageSize` | int | 否 | 30 | 每页条数，最大 100 |

---

#### POST `/api/chat/conversation/{conv_id}/message` — 发送消息

**Request Body:**
```json
{
  "content": "分析一下贵州茅台的走势",
  "content_type": "text"
}
```

触发 Agent 分析流程：意图识别 → 价值评估 → PA 技术分析 → 组合决策 → SSE 流式响应。

---

#### POST `/api/chat/message` — 一键创建会话并发送消息

**Request Body:**
```json
{
  "content": "分析一下贵州茅台的走势",
  "title": "茅台分析"
}
```

自动创建新会话后立即发送消息。

---

### 1.6 Python 端 API 汇总

| # | 方法 | 路径 | 功能域 | 调用方 |
|---|------|------|--------|--------|
| 1 | GET | `/health` | 健康检查 | 运维 |
| 2 | POST | `/api/fetch/market` | 数据同步 | Java/Python |
| 3 | GET | `/api/fetch/market` | 数据同步 | Java cron |
| 4 | POST | `/api/fetch/batch` | 数据同步 | 运维 |
| 5 | GET | `/api/fetch/batch/status` | 数据同步 | 运维 |
| 6 | GET | `/api/quote/realtime` | 行情数据 | 前端/Java |
| 7 | GET | `/api/kline/history` | 行情数据 | 前端/Java |
| 8 | GET | `/api/stock/search` | 股票元数据 | 前端/Java |
| 9 | POST | `/api/stock/init-metadata` | 股票元数据 | 运维 |
| 10 | POST | `/api/chat/conversation` | 对话管理 | 前端 |
| 11 | GET | `/api/chat/conversation/list` | 对话管理 | 前端 |
| 12 | GET | `/api/chat/conversation/{id}` | 对话管理 | 前端 |
| 13 | PUT | `/api/chat/conversation/{id}/archive` | 对话管理 | 前端 |
| 14 | DELETE | `/api/chat/conversation/{id}` | 对话管理 | 前端 |
| 15 | GET | `/api/chat/conversation/{id}/message` | 对话管理 | 前端 |
| 16 | POST | `/api/chat/conversation/{id}/message` | 对话管理 | 前端 |
| 17 | POST | `/api/chat/message` | 对话管理 | 前端 |

---

## 二、Java 后端 API（Spring Boot）

**基础信息**
- 服务地址：`http://localhost:8879`
- Context Path：`/api`
- 全局统一响应格式：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 2.1 股票数据 `StockController`

#### GET `/api/stock/search` — 搜索股票

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `keyword` | string | 是 | - | 搜索关键词（代码或名称） |
| `limit` | int | 否 | 10 | 返回数量限制 |

**Response:** `BaseResponse<List<StockSearchItem>>`

---

#### GET `/api/stock/quote` — 实时行情

**Query Parameters:**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `symbols` | string | 是 | 逗号分隔，如 `000001.SZ,600519.SH` |

**Response:** `BaseResponse<List<StockQuote>>`

---

#### GET `/api/stock/kline` — K 线数据

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 含交易所后缀，如 `000001.SZ` |
| `timeframe` | string | 否 | `1d` | 支持 `1m/5m/15m/30m/1h/4h/1d/1w/1M` |
| `limit` | int | 否 | 120 | 返回 K 线数量 |

**Response:** `BaseResponse<StockKlineResponse>`

---

#### GET `/api/stock/detail/{symbol}` — 股票详情

**Path Parameters:**

| 参数 | 类型 | 描述 |
|------|------|------|
| `symbol` | string | 股票代码 |

**Response:** `BaseResponse<StockDetail>`

---

#### GET `/api/stock/indicators/{symbol}` — 技术指标

**Path Parameters:**

| 参数 | 类型 | 描述 |
|------|------|------|
| `symbol` | string | 股票代码 |

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `type` | string | 是 | - | 指标类型（MA, EMA, MACD 等） |
| `period` | int | 否 | - | 指标周期 |
| `limit` | int | 否 | 120 | 返回数量 |

**Response:** `BaseResponse<IndicatorResult>`

---

### 2.2 大盘行情看板 `MarketBoardController`

#### GET `/api/market/indices` — 指数行情

获取上证指数、深证成指、创业板指、科创50等主要指数行情。

**Response:** `BaseResponse<List<MarketIndex>>`

---

#### GET `/api/market/ranking` — 涨跌幅排名

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `type` | string | 否 | `top_gainers` | `top_gainers`(涨幅榜) / `top_losers`(跌幅榜) |
| `limit` | int | 否 | 20 | 返回数量 |

**Response:** `BaseResponse<List<StockQuote>>`

---

### 2.3 自选股管理 `WatchlistController`

#### GET `/api/watchlist/list` — 获取自选股列表

按排序字段升序排列。

---

#### POST `/api/watchlist/add` — 添加自选股

**Request Body:**
```json
{ "symbol": "000001.SZ", "groupName": "金融" }
```

---

#### POST `/api/watchlist/remove` — 移除自选股

**Request Body:**
```json
{ "symbol": "000001.SZ", "groupName": "金融" }
```

---

#### POST `/api/watchlist/reorder` — 重新排序

**Request Body:**
```json
{
  "items": [
    { "id": 1, "sort": 0 },
    { "id": 2, "sort": 1 }
  ]
}
```

---

### 2.4 系统监控 `MonitorController`

#### GET `/api/monitor/overview` — 监控概览

**Response:** `BaseResponse<Map<String, Object>>`

---

#### GET `/api/monitor/backfill-progress` — 数据回填进度

**Response:** `BaseResponse<Map<String, Object>>`

---

#### GET `/api/monitor/coverage` — 数据覆盖率

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| `limit` | int | 否 | 50 | 返回数量 |

---

#### GET `/api/monitor/quality-issues` — 数据质量问题

**Query Parameters:**

| 参数 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `status` | string | 否 | 过滤状态 |
| `issueType` | string | 否 | 过滤问题类型 |
| `symbol` | string | 否 | 过滤股票代码 |

---

#### POST `/api/monitor/quality-issues/{id}/status` — 更新问题状态

**Path Parameters:** `id` (Long)

**Request Parameters:** `status` (string, 必填)

---

### 2.5 Java 端 API 汇总

| # | 方法 | 路径 | 功能域 | 备注 |
|---|------|------|--------|------|
| 1 | GET | `/api/stock/search` | 股票数据 | - |
| 2 | GET | `/api/stock/quote` | 股票数据 | - |
| 3 | GET | `/api/stock/kline` | 股票数据 | - |
| 4 | GET | `/api/stock/detail/{symbol}` | 股票数据 | - |
| 5 | GET | `/api/stock/indicators/{symbol}` | 股票数据 | Java 计算技术指标 |
| 6 | GET | `/api/market/indices` | 大盘行情 | - |
| 7 | GET | `/api/market/ranking` | 大盘行情 | - |
| 8 | GET | `/api/watchlist/list` | 自选股 | - |
| 9 | POST | `/api/watchlist/add` | 自选股 | - |
| 10 | POST | `/api/watchlist/remove` | 自选股 | - |
| 11 | POST | `/api/watchlist/reorder` | 自选股 | - |
| 12 | GET | `/api/monitor/overview` | 系统监控 | - |
| 13 | GET | `/api/monitor/backfill-progress` | 系统监控 | - |
| 14 | GET | `/api/monitor/coverage` | 系统监控 | - |
| 15 | GET | `/api/monitor/quality-issues` | 系统监控 | - |
| 16 | POST | `/api/monitor/quality-issues/{id}/status` | 系统监控 | - |

---

### 2.6 WebSocket 端点

| 端点 | 协议 | 处理类 | 描述 |
|------|------|--------|------|
| `/ws/quote` | WebSocket | `QuoteWebSocketHandler` | 实时行情数据推送 |

---

## 三、Java → Python 交互调用

Java 后端通过 HTTP 调用 Python 服务的以下端点：

| 调用场景 | Java 调用方 | Python 端点 | 频率 |
|----------|-------------|-------------|------|
| 定时增量同步 | `DataSyncJob` (cron) | GET `/api/fetch/market?symbols=...` | 定期 |

---

## 四、前端代理说明

| 代理规则 | 目标 | 说明 |
|----------|------|------|
| Vite `/api/stock/*` → | `http://localhost:8879` | Java 后端 K 线、行情、看板等 |
| Vite `/api/market/*` → | `http://localhost:8879` | Java 后端大盘行情 |
| Vite `/api/watchlist/*` → | `http://localhost:8879` | Java 后端自选股 |
| Vite `/api/monitor/*` → | `http://localhost:8879` | Java 后端系统监控 |
| Vite `/api/chat/*` → | `http://localhost:8002` | Python 服务对话管理 |
| Vite `/api/kline/*` → | `http://localhost:8002` | （已废弃，由 Java 端替代） |
| Vite `/api/fetch/*` → | `http://localhost:8002` | Python 服务数据同步 |
| Vite `/api/quote/*` → | `http://localhost:8002` | Python 服务实时行情 |
| Vite 其他 `/api/*` → | `http://localhost:8002` | Python 服务兜底 |

## 五、路径归属说明

Java 和 Python 在 Vite 代理下通过路径前缀区分，不存在冲突：

| 路径 | 归属 | 路由目标 |
|------|------|---------|
| `/api/stock/*` | Java | `:8879`（更具体的规则优先匹配） |
| `/api/market/*` | Java | `:8879` |
| `/api/watchlist/*` | Java | `:8879` |
| `/api/monitor/*` | Java | `:8879` |
| `/api/chat/*` | Python | `:8002` |
| `/api/kline/*` | Python | `:8002` |
| `/api/fetch/*` | Python | `:8002` |
| `/api/quote/*` | Python | `:8002` |

> **注意：** `/api/kline/*` 仍保留在 Python 端，但前端已不再调用。迁移后前端 K 线数据统一从 `/api/stock/kline`（Java 端）获取。
