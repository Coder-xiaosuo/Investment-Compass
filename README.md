# Investment-Compass

基于 **多 Agent 协作** 的 A 股投研助手：通过「估值评估 → 用户决策（HITL）→ 技术分析」两阶段编排，结合资讯 RAG、六维风格画像与经验自进化闭环，输出**带来源引用**的买卖/观望建议。单股投研从传统人工的约 9.5 小时压缩至 18 分钟（**效率提升约 31 倍**）。

> 数据范围：仅支持 A 股市场。

![License](https://img.shields.io/badge/License-MIT-green) ![Python](https://img.shields.io/badge/Python-3.11-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-blue) ![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.5-green) ![React](https://img.shields.io/badge/React-19-61dafb)

---

## 目录

- [参赛荣誉](#参赛荣誉)
- [界面预览](#界面预览)
- [功能特性](#功能特性)
- [架构总览](#架构总览)
- [核心设计](#核心设计)
- [快速开始](#快速开始)
- [使用说明](#使用说明)
- [配置参考](#配置参考)
- [数据模型](#数据模型)
- [项目结构](#项目结构)
- [合规与安全](#合规与安全)
- [开发指南](#开发指南)
- [贡献指南](#贡献指南)
- [License](#license)

---

## 参赛荣誉

Investment Compass 投资罗盘参赛 **2026 飞书 AI 先锋赛 · 金仕达命题**（命题：一套面向中小 B + 大 C 的智能化金融投研与财富助手），成功**入围并获奖**。

> 奖项名称 / 获奖证书 / 比赛链接（待补充，由维护者更新）

## 界面预览

> 使用效果截图由维护者补充，建议存放至 `docs/images/` 后替换下方占位。可包含：
>
> - 工作台主界面
> - 两阶段分析对话（估值 → HITL 确认 → 技术分析）
> - 决策卡与引用卡片
> - 六维风格画像雷达

```
docs/images/            # 截图与架构图统一存放目录（由维护者添加）
├── screenshot-main.png        # 工作台主界面
├── screenshot-analysis.png    # 两阶段分析对话
├── screenshot-decision.png    # 决策卡 / 引用卡片
├── screenshot-radar.png       # 六维风格画像雷达
└── architecture-7layers.png   # 7 层架构图
```

## 功能特性

### 两阶段决策 + 人在回路（HITL）

- **估值评估**：5 类估值模型（DCF / PB-ROE 回归 / 可比公司 / DDM 高股息旁路 / 安全边际），规则层先算出确定性区间，LLM 只做解释
- **技术分析**：8 类技术指标（趋势 / 震荡 / 波动 / 量能 / 筹码 / 形态 / 大盘相关性 / 行业动量）算法打分，100% 可复现
- **人工确认**：估值展示后由用户 `approve / reject / respond` 拍板，AI 从不替用户下单，关键节点由人类把控

### Agentic RAG 资讯问答

- `plan → retrieve → synthesize` 反思循环，信息不足主动回头重查（最多两轮）
- **四级事件权重**（价格敏感 2 日 / 公告 4 日 / 情绪 7 日 / 战略 60 日）排序 + URL/标题去重
- 回答强制带 `[1][2]` 引用编号，URL 必填，杜绝编造来源

### 六维风格画像（千人千面）

- 30 题问卷冷启动 → 六维雷达（风险偏好 / 时间周期 / 决策依据 / 交易风格 / 仓位集中度 / 情绪偏好）
- HITL 反馈在线微调（±0.2 梯度）+ 月度 KL 散度校准防漂移
- 画像驱动下游全部个性化参数：估值加权系数、均线周期、止盈止损宽度、建议仓位

### 经验自进化闭环

- 决策以 `trace_id` 幂等落库 → 10 日窗口复盘 → 成功/失败案例 promote 进经验库 → 注入后续决策
- 注入预算治理（单条 ≤400 字、总注入 ≤1200 字），避免噪声淹没上下文

### 工程韧性

- **双源熔断**：东财（主）⇄ 新浪（备）完整状态机（closed → open → half_open），主源连续失败 3 次自动切换
- **幂等决策**：`decision_cards` 以 trace_id upsert，重复执行收敛到同一行，决策可回放、可追溯

### 集成

- 多数据源：akshare / 东方财富 / Tushare 可配置切换
- 行情看板 / K 线 / 自选股 / 财务数据，WebSocket 实时行情推送
- 消息通知：飞书 Webhook / PushPlus

## 架构总览

系统按单一职责切分为 **7 层**，层间通过 FastAPI REST / LangGraph State 解耦，便于独立扩展与灰度替换：

| 层级 | 主要模块 | 职责 |
|---|---|---|
| ① 前端交互层 | React + Vite + 系统设置中心 + 右侧来源 Tab | 双模式工作台、API Key 加密配置、资讯原文内嵌 |
| ② API 网关层 | FastAPI + CORS + Settings CRUD API | 鉴权、配置热更新、会话管理、连通性校验 |
| ③ 编排引擎层 | LangGraph StateGraph + MySQL Checkpointer | 两阶段编排：估值 → HITL → 技术，中断现场持久化可恢复 |
| ④ 子 Agent 层 | 估值 / 技术 / 资讯 RAG / 自选股画像 | Pydantic Schema 强约束输出，带反思重试 |
| ⑤ 数据中台层 | Tushare / AkShare + 双源熔断 + 限流缓存 | 行情、财务、公告、资讯统一拉取、去重、归并 |
| ⑥ 持久化层 | MySQL（决策+会话）/ Redis（缓存）/ Chroma（经验向量） | 事实层、偏好层、经验层三级持久化 |
| ⑦ 通知同步层 | 飞书群 Webhook 推送 + 配置同步 | 决策卡主动触达，工作台一次配置双端生效 |

> 架构图（待补充）：建议放置 7 层架构图与核心数据流图。图片存放至 `docs/images/` 后替换下方引用，例如：
>
> `![7 层架构图](docs/images/architecture-7layers.png)`

**一次完整分析请求的调用链**

```
用户提问 → Frontend /api/chat → Python Service
  → 主控 Agent 委派 估值评估 Agent（LLM + 财务数据源）
  → 返回估值建议 + 引用卡片，HITL 征求用户确认
  → 用户批准 → 技术分析 Agent（规则引擎打分 + LLM 解读）
  → 合并输出决策卡（方向 / 目标价 / 止损止盈位 / 支撑理由）
  → 持久化 + 飞书 Webhook 推送 + 前端渲染
```

## 核心设计

### 确定性规则在前，LLM 定性在后（双引擎架构）

系统最底层的设计哲学——**不让 LLM 做它不擅长且容易出错的事**（算指标、读财报数字），只让它做擅长的事（定性判断、跨维度推理）。两个决策引擎都严格遵循此原则：

| 维度 | 规则/算法引擎（前） | LLM 定性引擎（后） |
|---|---|---|
| 输入 | 财报数字、K 线几何特征、估值公式参数 | 规则分数、算法锚点 + 行业上下文 + 用户画像 |
| 输出 | 门控 PASS/REJECT、确定性分数、ATR 通道、客观分档 | 自然语言结论、矛盾风险揭示、理由清单 |
| 可复现性 | **100% 可复现**：同一输入 → 同一分数 | 受温度影响，但锚点固定在事实层 |

- **估值引擎**：4 道硬门控拦截（财务缺失 / ST / ROE<0 / 负债率>90%）→ 五维加权评分（盈利 30% / 成长 25% / 估值 20% / 财务健康 15% / 收益质量 10%）→ LLM 仅解释，不允许调整分数
- **技术引擎**：8 类指标算法打分（±100 分 → 5 档：BUY_STRONG / BUY / HOLD / SELL / SELL_STRONG）→ 止盈止损位由 `ATR × 自适应系数` 直接计算 → LLM 只写三句话解读
- 效果：从根本上解决金融场景最致命的问题——**LLM 幻觉 K 线 / 财务数据**

### 人在回路（HITL）决策护栏

主 Agent 挂载 `confirm_proceed_analysis` 中断工具，被调用时由 HITL 中间件暂停 LangGraph 执行、征求用户决策；中断现场经 MySQL Checkpointer 持久化，进程重启 / 跨会话均可恢复；MySQL 不可用时自动降级为无中断流程，保证主链路可用。

## 快速开始

### 环境要求

- Python 3.11+、Node 18+、JDK 21、Maven 3.9+
- MySQL 8+、Redis

### 1. 初始化数据库

```bash
# 创建数据库 investment_compass 并执行 sql/ 下迁移脚本
python scripts/init_db.py
```

### 2. 启动决策引擎（Python Service）

```bash
cd python-service
pip install -r requirements.txt
cp .env.example .env        # 按需修改数据库连接等
python main.py              # http://localhost:8002，健康检查 GET /health
```

### 3. 启动数据服务（Java Backend）

```bash
cd java-backend
mvn spring-boot:run         # http://localhost:8879/api
```

### 4. 启动前端工作台

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

### 5. 首次配置

打开工作台 → **系统设置**，填入 DeepSeek API Key（可选飞书 Webhook），保存即自动加密落盘。

## 使用说明

- **估值 + 技术分析**：输入股票代码或名称 → 估值评分 → 确认后输出技术方向建议
- **纯技术分析**：明确要求只看技术面时，跳过估值直接进入技术分析
- **资讯问答**：询问"XX 板块怎么看"等，返回带引用编号的可溯源回答
- **自选股管理**：增删查自选列表，行情看板实时跟踪
- **偏好画像**：前端问卷初始化，Agent 持续自进化更新

## 配置参考

环境变量模板见 `python-service/.env.example`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 兼容 fallback；优先使用前端「系统设置」配置的加密 Key |
| `DATABASE_URL` | `mysql+pymysql://root@localhost:3306/investment_compass` | MySQL 连接串 |
| `CONFIG_ENCRYPTION_KEY` | 空 | Fernet 密钥；缺省时自动生成于 `config/.config.key` |
| `DAILY_LOSS_LIMIT` | `5.0` | 日亏损上限（风控参数） |
| `MONTHLY_DRAWDOWN_LIMIT` | `10.0` | 月回撤上限（风控参数） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `HOST` / `PORT` | `0.0.0.0` / `8002` | FastAPI 监听地址 |

系统设置项（加密存储于 `config/settings.json`）：LLM provider / base_url / api_key、飞书 webhook / secret / app_id、Tushare token、PushPlus token、决策参数（confidence 阈值、retry 策略等）。

## 数据模型

核心表（详见 [`sql/`](sql) 迁移脚本，V002~V013 共 12 个）：

| 表 | 职责 |
|---|---|
| `decision_cards` | 决策事实层，`trace_id` 幂等唯一键，重复执行收敛到同一行 |
| `message` | 会话消息，(conversation_id, sequence) 唯一 |
| `agent_threads` | Agent 会话线程 |
| `watchlist` | 自选股 |
| `style_profiles` | 用户六维风格画像 |
| `financial_data` | 财务数据 |
| `news_*` | 资讯数据 |
| `sync_task` / `data_quality_issue` | 数据同步任务与质量稽核 |

## 项目结构

```
Investment-Compass/
├── python-service/    # 决策引擎：Agent 编排、估值/技术分析、RAG、画像、经验闭环、数据同步
│   ├── agents/        #   子 Agent（value_assessment / technical_analysis / advisory ...）
│   ├── services/      #   业务服务（chat / settings / style_profiler / experience_loop ...）
│   ├── shared/        #   公共层（config / 加密 / 数据源抽象 / 限流熔断）
│   └── pa_analyzer/   #   策略库（40+ skills + prompts）
├── java-backend/      # Spring Boot 数据服务：行情、K线、看板、WebSocket
├── frontend/          # React 工作台
├── sql/               # Flyway 风格数据库迁移脚本
├── scripts/           # 初始化 / 回测 / e2e 测试脚本
└── docs/              # 架构与 API 文档（图示见 docs/images/）
```

## 合规与安全

本项目遵循金融业务「合规优先」原则，在设计层面规避荐股、收益承诺、黑箱决策三大风险：

- **HITL 人工拍板**：最终决策 100% 由人类作出，系统仅输出「建议 + 引用 + 风险提示」
- **引用可溯源**：资讯 RAG 强制结构化引用（URL 必填），回答带 `[1][2]` 编号，可点击原文
- **硬门控拦截**：ST 股、连续亏损股、高负债股在规则层直接 REJECT，不进入 LLM 建议环节
- **无收益承诺**：每份决策卡附标准风险声明，前端首次进入弹风险揭示
- **凭据保护**：密钥经 Fernet 加密落盘；`.env`、日志、运行数据均被 `.gitignore` 排除

## 开发指南

```bash
# Python 服务测试
cd python-service && pytest

# 历史回测验证（回测产物见 python-service/out/）
cd python-service && python scripts/backtest.py

# Java 后端编译
cd java-backend && mvn compile

# 前端 lint / 构建
cd frontend && npm run lint && npm run build
```

API 文档见 [`docs/api-document.md`](docs/api-document.md) 与 [`docs/api-full-reference.md`](docs/api-full-reference.md)。

## 贡献指南

欢迎提交 Issue 与 PR。请遵循：

1. Fork 本仓库，从 `main` 新建特性分支
2. 保持 `.gitignore` 覆盖：**禁止提交任何密钥、日志与运行数据**
3. 提交前运行对应模块的测试与 lint
4. 提交信息使用 Conventional Commits 风格

## License

[MIT](./LICENSE) © Coder-xiaosuo
