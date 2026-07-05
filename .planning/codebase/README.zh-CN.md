# deepresearch 中文接手总览

**生成日期：** 2026-06-20  
**读者：** 当前接手项目、需要重新理解和优化 Agent 的开发者  
**依据：** `.planning/codebase/STACK.md`、`INTEGRATIONS.md`、`ARCHITECTURE.md`、`STRUCTURE.md`

## 一句话结论

这是一个前后端分离的 Deep Research 小应用：前端用 Vue/Vite 提供研究主题输入和流式进度展示，后端用 FastAPI 包装一个基于 HelloAgents、LangGraph、搜索工具和本地笔记工具的研究 Agent。当前项目更像教程实验后的工作副本，能看出完整流程，但还缺少工程化基线、测试、部署、安全边界和清晰的接手文档。

## 项目当前形态

核心目录只有两块：

- `backend/`：Python 后端，负责 API、Agent 编排、搜索、总结、报告生成、本地 notes 持久化。
- `frontend/`：Vue 前端，负责表单、SSE 流式事件解析、任务进度、来源、工具调用和最终报告展示。

生成物和本地状态也比较多：

- `backend/notes/`：HelloAgents `NoteTool` 运行后留下的 Markdown 笔记和索引。
- `backend/.venv/`：本地 Python 虚拟环境，不应当当成源码维护。
- `frontend/node_modules/`、`frontend/dist/`：前端依赖和构建输出，不应当当成源码维护。
- `.planning/codebase/`：GSD 生成的代码库地图，给后续规划和接手使用。

## 技术栈

后端：

- Python `>=3.10`
- FastAPI：HTTP API 和 SSE 流式接口，入口在 `backend/src/main.py`
- Uvicorn：本地启动 ASGI 服务
- HelloAgents `0.2.9`：LLM 包装、ToolAwareSimpleAgent、SearchTool、NoteTool
- LangGraph：最终报告的 writer/reviewer 流程
- Pydantic：配置模型和请求响应模型
- `uv.lock`：后端依赖锁文件

前端：

- Vue 3
- TypeScript
- Vite
- `vue-tsc`：前端 build 时做类型检查
- `fetch` + `ReadableStream`：解析后端 `text/event-stream`

外部依赖：

- LLM：默认按 Ollama 路线设计，也支持 LM Studio 和自定义 OpenAI-compatible provider
- 搜索：通过 HelloAgents `SearchTool`，可选 DuckDuckGo、Tavily、Perplexity、SearXNG、advanced
- 存储：没有数据库，只有本地文件 notes

## 关键文件速查

后端入口和编排：

- `backend/src/main.py`：FastAPI app、`/healthz`、`/research`、`/research/stream`
- `backend/src/agent.py`：`DeepResearchAgent`，整个研究流程的总协调器
- `backend/src/config.py`：`Configuration` 和 `SearchAPI`，读取环境变量
- `backend/src/models.py`：`TodoItem`、`SummaryState` 等工作流状态
- `backend/src/prompts.py`：规划、总结、报告写作提示词

后端服务模块：

- `backend/src/services/planner.py`：把研究主题拆成任务
- `backend/src/services/search.py`：调用搜索后端并整理来源上下文
- `backend/src/services/summarizer.py`：对单个任务生成或流式生成总结
- `backend/src/services/reporter.py`：生成最终报告
- `backend/src/services/tool_events.py`：记录工具调用，并把 note 信息同步到任务事件里
- `backend/src/services/notes.py`：构造 NoteTool 使用提示
- `backend/src/services/text_processing.py`：清理 `[TOOL_CALL:...]`

前端：

- `frontend/src/App.vue`：主界面、状态管理、事件 reducer、样式主体
- `frontend/src/services/api.ts`：`POST /research/stream` 的 SSE 客户端
- `frontend/src/main.ts`：Vue mount 入口
- `frontend/vite.config.ts`：Vite 配置，开发端口为 `5174`

## 主流程怎么跑

### 流式研究流程

1. 用户在 `frontend/src/App.vue` 输入研究主题，选择搜索后端。
2. 前端调用 `frontend/src/services/api.ts` 的 `runResearchStream(...)`。
3. 浏览器向后端发送 `POST /research/stream`。
4. `backend/src/main.py` 根据请求和环境变量构造 `Configuration`。
5. `main.py` 创建一个新的 `DeepResearchAgent`。
6. `DeepResearchAgent.run_stream(...)` 开始执行研究流程。
7. `PlanningService` 调用规划 Agent，把主题拆成多个 `TodoItem`。
8. 每个任务依次进入 `_execute_task(...)`。
9. `dispatch_search(...)` 调用 HelloAgents `SearchTool` 获取搜索结果。
10. `prepare_research_context(...)` 整理来源摘要和上下文。
11. `SummarizationService` 对每个任务生成总结，并可流式返回 chunk。
12. `ToolCallTracker` 捕获 NoteTool 等工具调用，转换成前端可显示的事件。
13. LangGraph 执行报告 `writer` 和 `reviewer` 节点。
14. `_persist_final_report(...)` 用 NoteTool 保存最终报告。
15. 后端不断返回 SSE 事件，前端更新任务状态、来源、工具调用和最终报告。

### 同步研究流程

`POST /research` 也存在，但它不走增量事件展示，而是一次性返回最终报告和任务列表。它适合 API 调用或调试，不适合作为主要用户体验。

## Agent 架构重点

这个项目里的 Agent 不是 Codex skill/MCP 插件，而是 HelloAgents 应用：

- `HelloAgentsLLM` 负责连接 Ollama、LM Studio 或 OpenAI-compatible provider。
- `ToolAwareSimpleAgent` 包装不同角色的 Agent。
- `ToolRegistry` 注册工具，目前主要是 `NoteTool`。
- `SearchTool` 在 `backend/src/services/search.py` 里作为全局对象 `_GLOBAL_SEARCH_TOOL` 使用。
- LangGraph 只用于最终报告写作和评审重写，不负责整个任务链路。

角色大致是：

- 规划 Agent：根据主题生成 TODO 任务。
- 总结 Agent：针对每个搜索任务写任务总结。
- 报告 Agent：把任务总结整合成 Markdown 报告。
- 评审 Agent：给报告打分并给出修改意见，低分时触发重写。

## 配置与环境变量

后端配置集中在 `backend/src/config.py`。常见变量：

- `LLM_PROVIDER`：`ollama`、`lmstudio` 或 custom provider
- `LOCAL_LLM`：本地模型名
- `LLM_MODEL_ID`：自定义模型名
- `LLM_API_KEY`：需要密钥的 provider 使用
- `LLM_BASE_URL`：自定义 OpenAI-compatible 地址
- `OLLAMA_BASE_URL`：Ollama 地址，默认 `http://localhost:11434`
- `LMSTUDIO_BASE_URL`：LM Studio 地址，默认 `http://localhost:1234/v1`
- `SEARCH_API`：`duckduckgo`、`tavily`、`perplexity`、`searxng`、`advanced`
- `MAX_WEB_RESEARCH_LOOPS`：研究轮数预算
- `FETCH_FULL_PAGE`：是否拉取完整页面内容
- `STRIP_THINKING_TOKENS`：是否清理 `<think>` 内容
- `USE_TOOL_CALLING`：是否使用工具调用模式
- `ENABLE_NOTES`：是否启用本地笔记
- `NOTES_WORKSPACE`：NoteTool 写入目录

前端配置：

- `VITE_API_BASE_URL`：后端 API 地址，默认 `http://localhost:8000`

## 当前风险与技术债

优先级较高：

- 当前目录不是 git 仓库，缺少历史、diff、回滚和提交基线。
- 后端虚拟环境可能已经失效；此前检查到 `.venv` 指向旧 Python 路径。
- 没有测试体系：未发现后端 `tests/`、前端 Vitest/Jest/Playwright 配置。
- 没有部署配置：未发现 Dockerfile、CI workflow、平台部署 manifest。
- `backend/src/prompts.py`、部分中文注释和历史 notes 在当前环境里出现乱码风险；如果提示词真实乱码，会直接伤害 Agent 质量。
- `backend/src/main.py` CORS 允许所有来源，不适合直接暴露到生产环境。
- 没有认证鉴权，任何能访问后端的人都可以发起研究请求。

中等优先级：

- `frontend/src/App.vue` 很大，UI、状态 reducer、样式都集中在一个文件里，后续维护成本高。
- `backend/src/agent.py` 也很大，承担 LLM 初始化、工具注册、任务执行、流式事件、报告评审、notes 持久化等多重职责。
- `backend/src/services/search.py` 使用模块级 `_GLOBAL_SEARCH_TOOL`，如果未来要并发、切换后端或做隔离，需要重新评估。
- notes 同时出现在 `backend/notes/` 和 `backend/src/notes/`，需要明确哪个是正式工作区。
- 前端声明了 `axios` 依赖，但当前 API 客户端实际使用 `fetch`。
- 后端模块使用直接 sibling imports，例如 `from config import Configuration`，运行时需要保证 `backend/src` 在 import path 上。

## 接手后的推荐顺序

### 1. 先恢复工程基线

目标：能安全修改、能跑、能回退。

- 初始化 git，并添加 `.gitignore`
- 排除 `.venv/`、`node_modules/`、`dist/`、`__pycache__/`、`*.egg-info/`
- 明确 notes 是否要纳入版本管理
- 重建后端虚拟环境，优先使用 Python 3.11 或项目兼容版本
- 确认 `backend/uv.lock` 是否仍可用
- 记录本地启动命令

### 2. 跑通最小端到端

目标：不要在没验证的状态下优化 Agent。

- 启动后端 `backend/src/main.py`
- 启动前端 Vite
- 输入一个简单研究主题
- 确认 `todo_list`、`sources`、`task_summary_chunk`、`final_report` 都能返回
- 确认 notes 是否成功写入预期目录
- 确认前端取消请求、错误展示、搜索后端切换是否正常

### 3. 修复提示词和文本编码

目标：保证 Agent 能读懂自己的系统提示。

- 检查 `backend/src/prompts.py` 是否真实乱码
- 检查 `backend/src/agent.py` 里的中文 Agent 名称、fallback 文案是否真实乱码
- 如果文件真实乱码，优先恢复为 UTF-8 中文
- 把提示词从代码里拆成更易维护的结构，可考虑 `backend/src/prompts/`

### 4. 建立最小测试

目标：后续优化有回归保护。

- 给 `Configuration.from_env()` 加配置解析测试
- 给 `PlanningService._extract_tasks()` 加 JSON 解析测试
- 给 `strip_tool_calls()`、`strip_thinking_tokens()` 加文本清理测试
- 给 SSE 事件解析逻辑加前端单元测试，或至少给 `runResearchStream(...)` 做 mock 流测试

### 5. 再优化 Agent 质量

可以从这些方向入手：

- 规划阶段：限制任务数、要求互斥覆盖、要求输出稳定 JSON
- 检索阶段：增加来源质量筛选、去重、失败降级和来源引用保真
- 总结阶段：要求结论绑定来源，减少空泛概括
- 报告阶段：结构固定化，增加“结论-证据-不确定性”格式
- 评审阶段：把评分标准显式化，避免模型随意打分
- 事件阶段：让每一步有更明确的 `type`、`step`、`task_id`、`error_code`

## 如果只选一个马上做的事

先做“工程基线恢复”：初始化 git、补 `.gitignore`、重建后端环境、写启动说明。这个项目现在最大的问题不是 Agent 不够聪明，而是还没有一个能放心演进的工作面。等能稳定跑通之后，再改提示词和 Agent 流程，收益会更扎实。

## 后续可用命令建议

继续补全 GSD 地图：

```text
$gsd-map-codebase --fast --focus quality
$gsd-map-codebase --fast --focus concerns
```

然后进入优化规划：

```text
请基于 .planning/codebase 和 README.zh-CN.md，帮我规划第一阶段：恢复工程基线并跑通最小端到端，不要先改 Agent 逻辑。
```
