# Agent 驱动投资工作台 PRD

**版本**：V1.0
**核心定位**：将投资操盘系统从"多页面分散操作"升级为以 AI 对话为中心的单一工作台界面。左侧资产与数据，中央 AI 对话流，右侧动态上下文面板。所有操盘动作通过对话中的可执行卡片完成。
**参考原型**：Trae、Cursor、Codex CLI 的交互范式
**对齐说明**：本文档已根据项目现有实现（Java Spring Boot + Vue 3 + Naive UI + Pinia）调整颗粒度，标注了"已存在"和"待新建"的内容。

---

## 1. 现有架构概述

### 1.1 当前布局（改造基础）

```
┌──────────────────────────────────────────────────────────────┐
│ 顶部导航栏 (TopBar) - 56px                                    │
├────────────┬─────────────────────────────────────────────────┤
│            │                                                 │
│  左侧导航栏  │    内容区 (router-view)                         │
│  (220px,    │                                                │
│   可折叠)   │    /dashboard  /dialogue  /smart-briefing      │
│            │    /review     /knowledge  /agents              │
│            │    /personality /skills    /admin               │
│            │    /weekly     /briefing   ...                  │
│            │                                                 │
├────────────┴─────────────────────────────────────────────────┤
│  ChatPanel 抽屉组件（浮动覆盖，从右滑出）                       │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 现有技术栈（维持不变）
- **前端**：Vue 3 + TypeScript + Vite + Naive UI + Pinia + Vue Router
- **后端**：Java Spring Boot (REST API) + Python FastAPI (AI 服务)
- **对话流**：Java 侧 `prepare` → Python SSE `stream` → Java 侧 `complete` 三步流程
- **行情**：SSE (`/sim/market/subscribe`) 而非 WebSocket

### 1.3 已有页面路由（17 个）

| 路由 | 页面 | 说明 |
|---|---|---|
| `/dashboard` | 驾驶舱 | 已有：KPI 卡片、看板、回测图表 |
| `/briefing` | 简报 | 已有：简单简报视图 |
| `/smart-briefing` | 智能早报 | 已有：含 TopBanner、工作流、指令下发、飞书推送 |
| `/smart-briefing/history` | 早报历史 | 已有 |
| `/smart-briefing/process/:runId` | 工作流详情 | 已有：可视化节点状态 |
| `/dialogue` | 对话 | 已有：会话侧栏 + 消息流 + SSE 流式响应 |
| `/personality` | 人格配置 | 已有：CRUD + 风险参数审批 |
| `/questionnaire` | 投资人格诊断 | 已有：问卷 + AI 生成人格草稿 |
| `/review` | 复盘工作台 | 已有：交易记录录入与列表 |
| `/weekly` | 周报 | 已有 |
| `/knowledge` | 知识库 | 已有：时间线、主题聚类 |
| `/agents` | AI 团队 | 已有：Agent 展示卡片 |
| `/skills` | 策略文档 | 已有：Skill 文档管理 |
| `/admin` | 管理面板 | 已有：系统设置 |
| `/workspaces` | 工作区管理 | 已有 |
| `/workspace-guide` | 创建工作区 | 已有 |
| 错误页 | 403/404/500 | 已有 |

---

## 2. 目标布局规范与组件树

### 2.1 目标布局（三栏式重构）

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 顶部导航栏 (TopBar)                                                          │
├──────────────┬────────────────────────────┬─────────────────────────────────┤
│              │                            │                                 │
│  左侧面板     │    中央主操作区             │    右侧动态面板                  │
│  (280px)     │    AI 对话流               │    (320-480px 可拖拽)            │
│              │                            │                                 │
│  ┌────────┐  │  ┌────────────────────┐   │  默认模式：                      │
│  │资产概览 │  │  │  AI 对话气泡         │   │  ┌────────────────────┐        │
│  │(新建)   │  │  │  + 内嵌数据卡片(新建) │   │  │ 待办任务列表(新建)  │        │
│  └────────┘  │  │  + 动作卡片(新建)     │   │  └────────────────────┘        │
│  ┌────────┐  │  └────────────────────┘   │  ┌────────────────────┐        │
│  │持仓列表 │  │                            │  │ 当前对话上下文(新建) │        │
│  │(新建)   │  │  ┌────────────────────┐   │  └────────────────────┘        │
│  └────────┘  │  │ 快捷操作栏(新建)     │   │                                 │
│  ┌────────┐  │  └────────────────────┘   │  搜索模式（覆盖 DefaultMode）：   │
│  │🔍搜索   │  │  ┌────────────────────┐   │  ┌────────────────────┐        │
│  │(新建)   │  │  │ 输入框(复用现有)    │   │  │ K线图(新建)        │        │
│  └────────┘  │  └────────────────────┘   │  └────────────────────┘        │
│  ┌────────┐  │                            │  ┌────────────────────┐        │
│  │股票详情 │  │                            │  │ 股票数据摘要(新建)  │        │
│  │(新建)   │  │                            │  └────────────────────┘        │
│  └────────┘  │                            │                                 │
├──────────────┴────────────────────────────┴─────────────────────────────────┤
│ 底部状态栏 (BottomBar) - 新建                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

> **标注说明**："新建"表示当前项目不存在、需从零开发；未标注的为已有组件。

### 2.2 组件树（完整明细）

```
App
├── TopBar (已存在: App.vue 内联)
│   ├── WorkspaceSwitcher          // 已存在: components/workspace/WorkspaceSwitcher.vue
│   ├── PersonaSwitcher            // 已存在: App.vue 内联人格切换
│   ├── NotificationBell           // 待新建
│   ├── SystemStatusIndicator      // 待新建
│   └── UserMenu                   // 待新建（当前只有"退出"按钮）
│
├── MainLayout (flex: row) → 待重构：原 220px 导航栏改为 280px 数据面板
│   ├── LeftPanel (280px, 新建)
│   │   ├── AssetOverview          // 待新建：调用 /dashboard/summary
│   │   ├── HoldingList            // 待新建：调用 /sim/agent/{id}/positions
│   │   │   └── HoldingItem * N
│   │   ├── StockSearch            // 待新建：调用 /sim/stock/search?keyword=
│   │   └── StockDataPanel         // 待新建：搜索后展开（条件渲染）
│   │
│   ├── CenterPanel (flex: 1)
│   │   ├── ConversationFlow       // 待新建：整合现有 DialogueView 的消息渲染+VirtualScroll
│   │   │   ├── MessageBubble * N  // 已有: components/dialogue/MessageBubble.vue
│   │   │   ├── DataCard * N       // 待新建：内嵌数据卡片
│   │   │   └── ActionCard * N     // 待新建：可执行动作卡片（见第 4 节）
│   │   ├── QuickActions           // 待新建：快捷操作按钮栏
│   │   └── InputArea              // 待新建：整合现有 DialogueView 的输入区
│   │
│   └── RightPanel (320-480px, 可拖拽, 新建)
│       ├── DefaultMode
│       │   ├── TodoList           // 待新建：待办任务列表
│       │   └── ContextView        // 待新建：当前对话上下文
│       └── SearchMode (覆盖 DefaultMode)
│           ├── KLineChart         // 待新建：全交互K线图（ECharts，已引入）
│           └── StockSummary       // 待新建：股票数据摘要
│
├── ChatPanel → 保留现有抽屉组件，新工作台中融合进中央对话流
│
└── BottomBar (新建)
    ├── WorkflowStatus             // 待新建：调用 /workflow/runs/{runId}
    ├── DataLatency                // 待新建：SSE 行情延迟计算
    ├── AIStatus                   // 待新建：Python 服务健康检查 /api/ai/health
    └── ConnectionTime             // 待新建：会话计时
```

### 2.3 重构策略说明

**渐进式演进，非推翻重来**：
1. 保留现有 App.vue 的 `n-layout` + `n-layout-sider` 框架
2. 左侧 `n-layout-sider` 从纯导航（Menu）改为导航+数据面板的组合模式
3. 新工作台路由 = `/workbench`（新增），与旧页面并存
4. 右侧面板用 `n-drawer` 或自定义 `resizable-panel` 组件实现
5. 底部状态栏在 App.vue 中新增 `n-layout-footer`

---

## 3. 核心交互详述

### 3.1 左侧面板 (LeftPanel) — 新建

#### 资产概览卡片
- **数据来源**：现有 `/dashboard/summary` API（返回 portfolioValue、cashBalance、todayPnL 等）
- **交互**：
  - 总市值：大号数字，与昨日对比涨跌幅颜色条
  - 现金余额：可用资金，占比环形图
  - 今日盈亏：实时更新，绿涨红跌
  - **点击卡片**：在中央对话区自动发送 `/portfolio summary` 指令，AI 回复完整持仓分析

#### 持仓列表
- **数据来源**：现有 `/sim/agent/{agentId}/positions` API
- 每行：标的代码+名称、持仓数量、现价、盈亏%
- **点击某持仓**：在右侧面板（覆盖模式）展示该标的 K 线图 + 数据摘要
- **右键菜单**：加仓、减仓、设止损、深度分析 → 均以对话指令形式触发，在中央区生成对应的动作卡片预览

#### 股票搜索框
- 输入行为：支持代码/拼音/名称模糊搜索，实时下拉建议
- **选中某标的**：
  - 左侧面板下方展开 `StockDataPanel`（当前价、PE、股息率、52周高低、成交量）
  - 右侧面板切换为 SearchMode，展示 K 线图 + 数据摘要
  - 中央对话区插入系统消息，附快捷操作按钮
- **ESC 或清空搜索框**：右侧面板恢复 DefaultMode，StockDataPanel 收起

### 3.2 中央主操作区 (CenterPanel)

#### AI 对话流（整合现有对话能力）
- **消息类型**：
  - **文本/富文本气泡**：复用现有 `MessageBubble.vue`，Markdown 渲染
  - **数据卡片**：新建组件，内嵌表格/ECharts 迷你图表，由 AI 调用数据工具生成
  - **动作卡片**：新建组件，可执行操作预览（详见第 4 节）
- **API 集成**：复用现有三步流程
  - Java: `POST /dialogue/prepare` → 保存消息/构建上下文
  - Python SSE: `POST /api/ai/chat/generate/stream` → 流式渲染
  - Java: `POST /dialogue/complete` → 持久化 + Token 计数 + 压缩触发
- **追问**：任何 AI 消息下的数据点均可点击追问

#### 快捷操作栏（新建）
- 位于对话流与输入框之间：
  - `+ 加观察`：弹出标的搜索 → 生成动作卡片
  - `模拟下单`：弹出下单表单 → 生成下单预览卡片
  - `设止损`：为当前持仓生成止损条件单卡片
  - `深度分析`：触发多 Agent 工作流

#### 输入框（整合现有）
- 复用现有样式和交互模型
- `@` 唤起标的选择器
- `/` 唤起指令菜单
- 附件上传：支持截图、PDF（新建后端上传接口）

### 3.3 右侧动态面板 (RightPanel) — 均待新建

#### 默认模式（DefaultMode）
- **待办任务列表**：
  - 待审批的早报指令、待执行的模拟交易、待完成的复盘
  - 数据来源：需新建 `/api/todos` 后端接口
  - 每项可点击，支持快速操作（"批准"/"忽略"）
- **当前对话上下文**：
  - 引用标的、时间范围、关键数据快照
  - 数据由 `POST /dialogue/prepare` 返回的 `context` + `ragContext` 构建

#### 搜索模式（SearchMode）
- 当左侧搜索框选中标的时触发
- **K 线图**：ECharts 实现（已引入依赖），支持缩放、拖拽、周期切换
- **数据来源**：需新建 `/api/market/kline/{symbol}?period=` 后端接口
- **股票数据摘要**：当前价、PE(TTM)、股息率、市值、52周高低

### 3.4 底部状态栏 (BottomBar) — 新建

- **工作流状态**：轮询 `/workflow/runs/{runId}` 展示进度
- **数据延迟**：SSE 行情心跳延迟计算
- **AI 状态**：轮询 Python `/api/ai/health` 服务状态 + Token 消耗统计
- **连线时长**：会话 `createdAt` 计时

---

## 4. AI 动作卡片系统

所有动作卡片须用户显式确认才能执行，卡片内嵌在对话流中。

### 4.1 卡片类型

| 卡片类型 | 触发场景 | 需新建的后端接口 | 用户操作 |
|---|---|---|---|
| **下单预览** | AI建议买入/卖出 | `POST /api/order/preview`（新建） | [执行]→调 `POST /sim/order/submit` [修改] [忽略] |
| **条件单** | AI建议设止损/止盈 | 需新建条件单接口 | [创建] [修改条件] [忽略] |
| **加入观察** | AI建议关注某标的 | 已有 `POST /sim/watchlist/add` | [加入]→调已有接口 [忽略] |
| **数据查询结果** | AI调用数据工具 | 复用现有查询API | [追问] [导出] |
| **早报审批** | 早报生成完成 | `POST /report/{id}/approve`（新建） | [批准并执行] [修改] [归档] |
| **复盘记录** | AI建议记录交易复盘 | 已有 `POST /reviews/trades` | [保存]→调已有接口 [编辑] [忽略] |
| **工作流触发** | AI建议深度分析 | 已有 `POST /workflow/report/generate` | [启动]→调已有接口 [调整参数] [取消] |

### 4.2 卡片交互规范
- **位置**：独立组件嵌入消息气泡下方，左侧色条区分视觉层级
- **确认弹窗**：资金变动操作须二次确认，展示不可逆提醒
- **反馈**：执行后卡片状态更新为"已执行"/"已创建"
- **撤销**：下单支持 10 秒内撤销，卡片显示倒计时和 [撤销] 按钮

---

## 5. 数据流与后端集成

### 5.1 前端状态管理（Pinia Store）

| Store | 状态 | 现状 |
|---|---|---|
| `authStore` | 用户认证 + 工作区 | 已存在: `stores/auth.ts` |
| `personalityStore` | 当前人格 + 列表 | 已存在: `stores/personality.ts` |
| `chatStore` | 对话消息 + 发送 | 已存在: `stores/chat.ts` |
| `chatPanelStore` | ChatPanel 可见性 | 已存在: `stores/chatPanel.ts` |
| `dialogueStore` | 对话会话列表 + 详情 | 已存在: `stores/dialogue.ts` |
| `conversationStore` | 对话历史 + 流式消息 | 需从现有 stores 抽取整合 |
| `marketStore` | 行情快照（SSE 推送） | 待新建 |
| `portfolioStore` | 持仓与资产数据 | 待新建 |
| `searchStore` | 当前搜索标的 + 面板模式 | 待新建 |
| `todoStore` | 待办任务列表 | 待新建 |
| `workbenchStore` | 工作台布局状态（面板宽度/模式） | 待新建 |

### 5.2 API 依赖（按现状对齐）

| 用途 | PRD 原文接口 | 实际接口 | 现状 |
|---|---|---|---|
| 资产概览 | `/api/portfolio/summary` | `GET /dashboard/summary` | 已有 |
| 持仓列表 | `/api/portfolio/holdings` | `GET /sim/agent/{agentId}/positions` | 已有 |
| 实时行情 | WebSocket | SSE `GET /sim/market/subscribe` | 已有 |
| 股票搜索 | `/api/market/search?q=` | `GET /sim/stock/search?keyword=` | 已有 |
| K线数据 | `/api/market/kline/{symbol}` | **需新建** | 待新建 |
| 对话历史 | `/api/conversation/{id}/messages` | `GET /dialogue/sessions/{id}` | 已有 |
| 对话流式 | `/api/conversation/stream` | Java prepare + Python SSE `/api/ai/chat/generate/stream` + Java complete | 已有 |
| 工作流状态 | `/api/workflow/runs/{id}` | `GET /workflow/runs/{runId}` | 已有 |
| 审批早报 | `/api/report/{id}/approve` | **需新建** | 待新建 |
| 下单预览 | `/api/order/preview` | **需新建** | 待新建 |
| 执行下单 | `/api/order/execute` | `POST /sim/order/submit` | 已有 |
| 待办任务 | `/api/todos` | **需新建** | 待新建 |

### 5.3 数据流变更

- **行情推送**：复用现有 SSE (`/sim/market/subscribe`)，新增 `marketStore` 管理订阅
- **对话流**：维持三步流程不变，对话 Store 进化为 `conversationStore` 支持流式消息增量渲染
- **面板状态**：新增 `searchStore` 管理左侧搜索+右侧面板联动，`workbenchStore` 管理布局

---

## 6. 待新建后端接口清单

以下接口为完成工作台所需、当前项目不存在的后端能力：

| 接口 | 用途 | 优先级 |
|---|---|---|
| `GET /api/market/kline/{symbol}?period=` | K 线历史数据 | P0 |
| `POST /api/order/preview` | 下单预览（风控预检查） | P0 |
| `POST /api/report/{id}/approve` | 审批早报/指令下发 | P1 |
| `GET/POST /api/todos` | 待办任务 CRUD | P1 |
| `GET /api/ai/health` | Python 服务健康状态 | P1 |
| `POST /api/upload` | 附件上传（对话输入） | P2 |
| `POST /api/stop-loss` | 条件止损单 | P2 |

---

## 7. 旧界面废弃计划

### 7.1 保留的页面
- **设置页**（`/settings`）— 需新建，当前无独立设置页
- **历史早报详情**（`/smart-briefing/history`）— 已有
- **AI 可观测性面板**（`/monitor`）— 需新建
- **知识库管理**（`/knowledge`）— 已有

### 7.2 废弃的页面

| 旧页面 | 替代方案 | 计划阶段 |
|---|---|---|
| 驾驶舱 (`/dashboard`) | 新工作台左侧资产概览 + 中央对话流 | 阶段二 |
| 独立对话页 (`/dialogue`) | 新工作台中央对话流 | 阶段二 |
| 智能早报页 (`/smart-briefing`) | 早报在对话中以动作卡片呈现 | 阶段二 |
| 独立复盘工作台 (`/review`) | 复盘卡片嵌入对话流 | 阶段二 |
| AI 团队 (`/agents`) | 移至左侧面板人格切换区 | 阶段三 |
| 策略文档 (`/skills`) | 移至设置/知识库区域 | 阶段三 |

### 7.3 分阶段迁移策略

**阶段一：基础工作台骨架（当前 → 2周）**
- 新建路由 `/workbench`，实现三栏布局骨架
- LeftPanel：资产概览 + 持仓列表（调已有接口）
- RightPanel：DefaultMode 待办/上下文（占位）
- BottomBar：基础状态显示
- 动作卡片：下单预览 + 加入观察（调已有接口）
- 此阶段旧页面全部保留

**阶段二：核心交互完善（2-4周）**
- 中央对话流完整集成（消息气泡 + 数据卡片 + 动作卡片）
- RightPanel SearchMode：K线图 + 股票数据摘要
- 快捷操作栏 + 完整动作卡片系统
- K线接口 + 下单预览接口上线
- `/workbench` 设为默认首页 `/`，旧路由改为 `/classic`

**阶段三：全功能覆盖（4-6周）**
- 完整的待办任务系统
- 早报审批流程图
- 底部状态栏全功能
- 旧页面废弃，URL 重定向
- macOS 客户端开发启动

---

## 8. 验收标准

1. 左侧面板正确展示资产概览与持仓列表，数据来自现有 `/dashboard/summary` 和 `/sim/agent/{id}/positions`
2. 搜索框支持模糊搜索（调 `/sim/stock/search`），选中后左侧展开数据面板、右侧切换 K 线图
3. 中央对话流支持 Markdown 渲染、数据卡片、动作卡片三种消息类型
4. 下单/条件单动作卡片需二次确认才执行，执行后有状态反馈
5. ESC 或清空搜索框时，右侧面板恢复待办+上下文模式
6. 底部状态栏实时反映工作流、数据延迟、AI 连接状态
7. 旧页面可通过 `/classic` 回退访问
8. 整体界面支持最小宽度 1280px，Naive UI 组件主题色跟随当前人格

---

## 9. 现有可复用资产清单

### 前端组件（可直接复用或轻度改造）

| 组件文件 | 用途 | 改造点 |
|---|---|---|
| `components/dialogue/MessageBubble.vue` | 消息气泡渲染 | 支持 DataCard/ActionCard 插槽 |
| `components/dialogue/ChatPanel.vue` | 紧凑对话面板 | 部分逻辑可提取为 composable |
| `components/workspace/WorkspaceSwitcher.vue` | 工作区切换 | 无需改造 |
| `components/sim/WatchlistTable.vue` | 自选列表 | 可复用表格渲染 |
| `components/sim/AccountSummaryCards.vue` | 账户概览 | 可参考设计 LeftPanel 资产卡片 |
| `components/sim/TradeModal.vue` | 下单弹窗 | 动作卡片触发时复用 |
| `components/sim/AgentDecisionLog.vue` | 决策日志 | 右侧面板上下文参考 |
| `components/briefing/BriefingOverview.vue` | 简报概览 | 数据卡片参考 |
| `style.css` | 设计令牌（颜色/间距/阴影） | 维持统一视觉 |

### 后端服务（复用现有 API）

详见第 5.2 节 API 依赖表。核心可复用：对话三步流程、持仓/资产接口、股票搜索、下单执行、工作流状态。

---

*此 PRD 与《智能投资早报 PRD》《模拟操盘系统 PRD》《用户模块 PRD》《AI 可观测性 PRD》共同构成完整产品蓝图。新工作台是整合所有能力的最终交互形态。*