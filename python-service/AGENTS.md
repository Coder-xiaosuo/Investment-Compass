<!-- AGENTS.md — 项目环境记忆文件，由 MemoryMiddleware 注入 system prompt。
     定位：本文件承载「项目特定」的持久上下文；System Prompt 承载「跨项目不变」
     的身份与行为准则。二者分工：
       SYSTEM_PROMPT = 我是谁（身份 / 行为准则 / 领域约束 / 记忆维护）
       AGENTS.md     = 我在哪个项目工作（子 Agent 清单 / 编排 / 文件系统 / 数据规范）
     维护规则：改子 Agent / 项目结构 → 改本文件；改身份 / 准则 → 改 SYSTEM_PROMPT
     （agents/main_agent.py 的 SYSTEM_PROMPT 常量）。 -->

# Investment Compass — 项目环境

## 项目定位
A 股投研助手：估值 + 技术分析两阶段决策服务。

## 子 Agent 清单（经 task 工具委派）

- **value_assessment** — A 股估值评估。输入：股票代码或名称。输出：score(0-100) / final_level(good/fair/average/poor) / summary / recommend / reason。
- **technical_analysis** — A 股技术分析。输入：JSON 字符串 `{"stock_identifier": "...", "va_summary": {...}}`。输出：direction(buy/sell/neutral) / confidence / patterns / support / resistance。
- **watchlist_manage** — 自选股管理。输入：add / remove / list + 股票代码或名称。输出：操作结果。
- **advisory** — 资讯问答（Agentic RAG）。输入：用户原始问题。输出：answer(含 [1][2] 引用编号) / citations / confidence。不处理行情/K线/买卖判断。

## 投资分析编排（两阶段）

1. **估值评估**：委派 value_assessment。
2. **征求用户决策（HITL）**：向用户展示估值结果（分数、等级、摘要）后，必须调用 `confirm_proceed_analysis` 中断征求决策：
   - approve → 进入技术分析
   - reject → 收尾回复（说明估值结论，不做技术面）
   - respond → 按用户回复内容调整处理
3. **技术分析**：委派 technical_analysis，JSON 传入 `{"stock_identifier": "...", "va_summary": {...}}`，va_summary 直接复用估值阶段返回字段。
4. **汇总输出**：最终建议由技术方向决定（buy→买入 / sell→卖出 / neutral→观望），估值作为背景，两者矛盾时提示风险。

## 分支处理
- 纯技术分析：用户只要求技术面 → 直接委派 technical_analysis（va_summary 可省略）。
- 自选股管理 → 委派 watchlist_manage。
- 资讯问答 / 概念解释 → 委派 advisory。
- 闲聊 → 直接回答，不委派。

## 文件系统地图
- `/memories/preferences.md` — 用户偏好记忆（可写；Agent 用 edit_file 维护，写入前先 read_file 保持结构）。仅承载跨会话有价值的信息：身份（称呼/职业）、投资偏好（风险偏好/决策风格/关注标的/分析深度/仓位习惯）、长期事实（持仓/常用周期）、反馈修正。不记录：一次性问题、临时请求、寒暄闲聊、时效性信息、敏感信息（API Key/密码/账号）。新用户偏好由前端问卷经 `POST /api/preferences` 初始化，写前自动备份 `.bak`。
- `/reports/{symbol}/{trace_id}.md/.json` — 分析报告归档（只读；trace_id 为决策幂等键）。
- 策略文件 `pa_analyzer/prompts/*.txt` — technical_analysis 内部加载，不直接读写。
- `data/workspace/` — 大结果卸载 / 对话历史归档（只读）。

## 数据规范
- decision_cards 表：决策事实层；trace_id 唯一幂等键，落库为 upsert（同 trace_id 重复执行收敛到同一行）。
- message 表：(conversation_id, sequence) 唯一，消息事实源。
