# 工作台后端 API — 分层架构图

> 风格参考：金融多Agent系统分层架构（上层接入 / 中层调度 / 下层执行）

```mermaid
graph TD
    subgraph 上层_接入层["上层 — 接入层 Controller"]
        style 上层_接入层 fill:#E3F2FD,stroke:#1976D2,stroke-width:2px

        C1["«controller»<br/>MarketDataController<br/><small>K线 REST API</small>"]
        C2["«controller»<br/>SimController<br/><small>下单预览 API</small>"]
        C3["«controller»<br/>TodoController<br/><small>待办任务 API</small>"]
        C4["«controller»<br/>StopLossController<br/><small>条件止损 API</small>"]
        C5["«controller»<br/>FileUploadController<br/><small>文件上传 API</small>"]
        C6["«controller»<br/>BriefingInstructionController<br/><small>早报审批 API</small>"]
        C7["«controller»<br/>SystemController<br/><small>聚合健康检查</small>"]
    end

    subgraph 中层_调度层["中层 — 调度层 Service"]
        style 中层_调度层 fill:#E8F5E9,stroke:#388E3C,stroke-width:2px

        S1["«service»<br/>TodoService<br/><small>待办 CRUD + 状态流转</small>"]
        S2["«service»<br/>StopLossService<br/><small>止损单管理 + 触发检查</small>"]
        S3["«service»<br/>RiskControlService<br/><small>风控预检查（复用）</small>"]
        S4["«service»<br/>BriefingInstructionService<br/><small>指令下发（复用）</small>"]
        S5["«service»<br/>OrderService<br/><small>订单提交（复用）</small>"]
        S6["«service»<br/>DayBriefingGenerator<br/><small>早报生成 + 自动创建待办</small>"]
        S7["«service»<br/>ReviewServiceImpl<br/><small>复盘记录 + 自动创建待办</small>"]
    end

    subgraph 下层_执行层["下层 — 执行层 Data + External"]
        style 下层_执行层 fill:#FFFDE7,stroke:#FBC02D,stroke-width:2px

        M1["«mapper»<br/>UserTodoMapper<br/><small>user_todo 表</small>"]
        M2["«mapper»<br/>StopLossOrderMapper<br/><small>stop_loss_order 表</small>"]
        M3["«mapper»<br/>MarketDataMapper<br/><small>market_data 表</small>"]
        M4["«mapper»<br/>DailyBriefingMapper<br/><small>daily_briefing 表</small>"]
        M5["«mapper»<br/>TradeRecordMapper<br/><small>review 表</small>"]

        E1["«external»<br/>Python AI Service<br/><small>FastAPI /api/ai/health</small>"]
        E2["«external»<br/>WebClient<br/><small>Reactive HTTP 调用 Python</small>"]
    end

    subgraph 数据持久化["数据持久化"]
        style 数据持久化 fill:#FFF3E0,stroke:#E65100,stroke-width:2px
        DB[("MySQL<br/>投资罗盘主库")]
    end

    %% 上层 → 中层
    C1 -->|"GET /api/market/kline/{symbol}"| S3
    C2 -->|"POST /sim/order/preview"| S3
    C3 -->|"GET/POST /api/todos"| S1
    C4 -->|"POST/PUT /api/stoploss"| S2
    C5 -->|"POST /api/upload"| S7
    C6 -->|"POST /briefing/.../approve"| S4
    C7 -->|"GET /api/health/aggregate"| E2

    %% 中层 → 下层 Mapper
    S1 -->|"selectListByQuery"| M1
    S2 -->|"selectListByQuery"| M2
    S3 -->|"复用风控检查"| S5
    S4 -->|"dispatch()"| S5
    S6 -->|"简报持久化"| M4
    S6 -->|"生成后自动创建"| S1
    S7 -->|"复盘后自动创建"| S1
    C1 -->|"selectListByQuery"| M3

    %% 中层 → 外部
    S2 -->|"触发后下单"| S5
    S5 -->