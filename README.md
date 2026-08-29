# Investment-Compass

A 股投研助手：**估值评估 + 技术分析** 两阶段决策服务。支持估值打分、技术面方向判断、Agentic RAG 资讯问答、自选股管理与消息通知（飞书）。

> 仅支持 A 股市场数据。

## 核心特性

- **两阶段决策管线**：估值评估（value_assessment，0-100 评分）→ 征求用户确认（HITL）→ 技术分析（technical_analysis，买卖/观望方向）
- **Agentic RAG 资讯问答**：资讯检索带引用编号（[1][2]），可溯源
- **多数据源**：akshare / 东方财富 / Tushare 等，可配置切换
- **经验自进化**：基于历史决策沉淀投资风格画像与经验库（向量检索）
- **消息通知**：飞书 / PushPlus
- **敏感配置加密**：LLM / 飞书等凭据经 Fernet 加密后落盘，不提交到仓库

## 技术架构

| 模块 | 技术栈 | 说明 |
|---|---|---|
| `python-service/` | FastAPI · SQLAlchemy · LangGraph · ChromaDB · akshare | 决策引擎 / Agent 编排 / RAG / 数据同步，端口 8002 |
| `java-backend/` | Spring Boot 3 · Java 21 · MyBatis-Flex · WebSocket | 行情 / K 线 / 数据服务，端口 8879 |
| `frontend/` | React 19 · Vite · TypeScript · lightweight-charts | 工作台 UI（对话 / K 线 / 指标看板） |
| `sql/` | MySQL 迁移脚本（Flyway 风格 V00x） | 库表结构 |

基础设施：MySQL（主存储）、Redis（缓存 / 会话）、ChromaDB（经验向量库）。

## 目录结构

```
Investment-Compass/
├── python-service/    # 决策引擎：Agent 编排、估值/技术分析、RAG、数据同步
├── java-backend/      # Spring Boot 数据服务：行情、K 线、WebSocket
├── frontend/          # React 工作台
├── sql/               # 数据库迁移脚本
├── scripts/           # 初始化与工具脚本
└── docs/              # 架构与 API 文档
```

## 快速开始

### 1. 初始化数据库

在 MySQL 中创建数据库（默认 `investment_compass`），执行 `sql/` 下的迁移脚本：

```bash
python scripts/init_db.py
```

### 2. 启动 Python 决策服务

```bash
cd python-service
pip install -r requirements.txt
python main.py          # 默认 http://0.0.0.0:8002
```

### 3. 启动 Java 数据服务

```bash
cd java-backend
mvn spring-boot:run     # 默认 http://localhost:8879/api
```

### 4. 启动前端工作台

```bash
cd frontend
npm install
npm run dev
```

## 配置说明

- **API Key**：通过前端「系统设置」界面配置（DeepSeek / 飞书等），经 Fernet 对称加密后存储在 `config/settings.json`（解密密钥本地生成于 `config/.config.key`，不提交仓库）
- 环境变量模板见 `python-service/.env.example`

## 安全说明

- 密钥、`.env`、日志、运行数据（向量库 / Redis 快照 / 回测产物）均已被 `.gitignore` 排除，**请勿将任何凭据提交到仓库**
- 若曾泄露过密钥，请立即在对应平台控制台吊销并重新生成

## License

[MIT](./LICENSE)
