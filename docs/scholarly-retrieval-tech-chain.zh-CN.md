# deepresearch 全项目技术链讲解文档

## 1. 结论

这不是一个单一的“论文检索模块”项目，而是一个完整的 research system。  
核心原因是它实际上包含两条已经打通的产品线：

- 通用 `DeepResearchAgent`：面向开放研究问题的 TODO 驱动式 web research 工作流
- `Scholarly Retrieval Workbench`：面向 AI/CS 论文调研的多阶段学术检索与筛选工作台

如果你要拿它去讲项目，正确的讲法不应该只讲 Phase 3，也不应该只讲 scholarly 检索，而是要把整个项目讲成：

> 一个从“通用深度研究代理”发展到“可持久化、可评测、可人工筛选的 scholarly research workbench”的完整工程系统。

---

## 2. 文档说明

这份文档的用途是：

- 帮你系统讲解整个项目
- 帮初学者理解每个模块在做什么
- 帮你回答“为什么这么设计”
- 帮你回答“遇到什么问题，怎么解决”
- 帮你从阶段演进角度讲这个项目，而不是只讲某个子模块

这里有一个范围说明：

- 我**不能直接读取隐藏的模型内部日志**，也不能像查看服务器审计日志那样回放所有历史 agent 行为
- 但我可以依据：
  - 当前对话中可见的执行记录
  - 现有仓库结构
  - 代码里明确保留下来的兼容逻辑、降级逻辑和容错逻辑
  来还原项目的整体演进

所以文档里会区分两类内容：

- `可直接确认`：我本轮实际执行时看到的日志和问题
- `基于代码回溯`：我从代码中明确看出来、很可能来自前两阶段真实问题的工程设计

---

## 3. 一句话介绍整个项目

`deepresearch` 是一个本地研究系统。

它的目标不是只回答一个问题，而是把“研究问题拆解、检索信息、沉淀任务笔记、生成报告、保存会话、回看和继续迭代”变成一个可复用工作流。

从产品角度看，它分成两层：

1. 通用研究代理层  
   适合开放研究问题，偏 web research

2. 学术论文工作台层  
   适合 AI/CS 论文调研，偏 structured retrieval / screening / reporting

---

## 4. 项目全景图

你可以把整个项目理解成下面两条主链路共享一个后端服务壳：

```text
用户输入 topic
-> FastAPI 接口层
-> 分流到两条工作流之一

A. 通用 DeepResearchAgent
   -> 任务规划
   -> 搜索工具检索
   -> 任务级总结
   -> 任务笔记同步
   -> 报告生成
   -> SSE 流式输出

B. Scholarly Retrieval Workbench
   -> 会话创建
   -> query planning
   -> 多源论文召回
   -> dedupe / candidate shaping
   -> coarse rerank
   -> frontier fallback
   -> final rerank
   -> SQLite 持久化
   -> 前端工作台展示 / 人工筛选 / 报告导出
```

也就是说，这个项目不是一个“单接口 demo”，而是一个双工作流系统。

---

## 5. 整体技术栈

## 5.1 前端

- `Vue 3`
- `TypeScript`
- `Vite`

前端职责：

- 接收用户输入
- 展示流式事件
- 展示任务状态、会话、论文池、报告
- 展示 metadata 和质量指标
- 提供人工筛选和导出入口

## 5.2 后端

- `FastAPI`
- `Pydantic`
- `LangGraph`
- `SQLite`
- `requests`
- `hello-agents`

后端职责：

- 提供 `/research` 和 `/research/sessions` 两类 API
- 编排 agent 工作流
- 调用搜索和学术源
- 保存任务笔记 / 会话 / 论文 / 报告
- 提供评测与 smoke 验证入口

## 5.3 外部能力

- `OpenAI-compatible LLM`
- `SearchTool`
- `NoteTool`
- `OpenAlex`
- `arXiv`
- `Semantic Scholar`

---

## 6. 项目是如何一步步发展成现在这样的

为了方便你讲项目，我建议把整个项目分成三个阶段。

这里的三个阶段不是前端设计稿里的 UI phase，也不是某一轮 commit 的名称，而是**项目能力演进阶段**。

## 6.1 Phase 1：通用 Deep Research Agent 基础研究流

这一阶段的重点是：

> 先把“研究问题 -> 分任务 -> 查资料 -> 写总结 -> 产出报告”这条基础链路跑通。

### 这一阶段解决的问题

如果没有这一阶段，系统只能做单轮回答。  
但研究任务往往不是一个 prompt 可以解决的，它更像一个多步骤过程。

所以这个阶段引入了：

- TODO 规划
- 任务级搜索
- 任务级总结
- 最终报告生成
- 流式事件输出
- 任务笔记沉淀

### 核心模块

相关文件：

- [agent.py](F:/codex/deepresearch/backend/src/agent.py)
- [planner.py](F:/codex/deepresearch/backend/src/services/planner.py)
- [search.py](F:/codex/deepresearch/backend/src/services/search.py)
- [summarizer.py](F:/codex/deepresearch/backend/src/services/summarizer.py)
- [reporter.py](F:/codex/deepresearch/backend/src/services/reporter.py)
- [tool_events.py](F:/codex/deepresearch/backend/src/services/tool_events.py)

### 这一阶段的技术链

```text
用户输入研究主题
-> PlanningService 让模型拆成 TODO tasks
-> dispatch_search() 调用 SearchTool 做结构化搜索
-> SummarizationService 逐任务总结
-> ToolCallTracker 同步 note 工具调用
-> ReportingService 汇总全部任务结果
-> SSE 持续返回任务进度与最终报告
```

### 这一阶段的亮点

#### 亮点 1：不是直接让模型“写篇报告”

而是先拆任务，再逐任务做研究。  
这比“一次性长提示词生成全部内容”更稳。

#### 亮点 2：引入了任务笔记

任务不是算完就丢，而是通过 `NoteTool` 沉淀到本地笔记。  
这样报告不是纯临时上下文拼出来的，而是能形成可复用研究资产。

#### 亮点 3：有流式输出

用户可以实时看到：

- 哪个任务开始了
- 哪个任务失败了
- 哪个任务完成了
- 报告何时生成完

这让它更像一个研究工作流系统，而不是后台黑盒。

### 适合初学者理解的一句话

> Phase 1 做的是“先把研究流程结构化”，把一个大问题拆成多个小任务来做。

---

## 6.2 Phase 2：Scholarly Workbench 产品化

这一阶段的重点是：

> 把“通用 web research”升级成一个专门做 AI/CS 论文调研的可持久化工作台。

### 这一阶段解决的问题

Phase 1 能做研究，但更偏“临时工作流”。  
如果想让它更像真正工具，就需要：

- 历史会话
- 论文候选池
- 人工筛选
- 报告保存
- 导出
- 前端工作台
- 稳定 API 契约

### 这一阶段新增了什么

相关文件：

- [main.py](F:/codex/deepresearch/backend/src/main.py)
- [scholarly_store.py](F:/codex/deepresearch/backend/src/services/scholarly_store.py)
- [scholarly_workflow.py](F:/codex/deepresearch/backend/src/services/scholarly_workflow.py)
- [App.vue](F:/codex/deepresearch/frontend/src/App.vue)
- [api.ts](F:/codex/deepresearch/frontend/src/services/api.ts)

这一阶段新增了新的产品面：

- `/research/sessions`
- `/research/sessions/stream`
- `/research/sessions/{id}`
- 论文列表与详情
- 报告流式生成
- Markdown / BibTeX 导出
- 本地 SQLite 会话保存

### 这一阶段的技术链

```text
用户输入学术研究主题
-> 创建 scholarly session
-> 检索候选论文
-> 前端显示候选池
-> 用户手工 included / excluded / saved
-> 生成 report
-> 保存 papers / reports / metadata
-> 允许后续回看、再筛选、导出
```

### 这一阶段的亮点

#### 亮点 1：从“结果”转向“会话”

Phase 1 更像生成一次报告。  
Phase 2 开始，系统的最小单位变成 `session`。

这意味着：

- 有生命周期
- 有状态
- 有历史
- 有可重复访问的上下文

#### 亮点 2：从“文本输出”转向“论文工作台”

你不再只是拿到一段文字，而是拿到：

- 论文列表
- 相关度标签
- 筛选状态
- 来源和理由
- 报告输出

这已经更接近产品，而不是脚本。

#### 亮点 3：前后端契约开始稳定

这一阶段非常关键的一件事，是把 API / SSE / session 数据结构定下来。

这为后面的 retrieval 升级提供了稳定外壳。

### 适合初学者理解的一句话

> Phase 2 做的是“把研究流程做成真正可用的工作台”，让结果能保存、筛选、回看和导出。

---

## 6.3 Phase 3：Retrieval Quality 升级

这一阶段的重点是：

> 不再满足于“能搜到”，而是开始系统性提升论文候选池质量。

### 这一阶段解决的问题

Phase 2 已经有 UI、有 session、有候选池。  
但如果候选池质量不高，后面的人工筛选和报告质量都会受限。

所以 Phase 3 做的不是扩前端，而是升级 retrieval stack。

### 核心模块

相关文件：

- [scholarly_search.py](F:/codex/deepresearch/backend/src/services/scholarly_search.py)
- [scholarly_rerank.py](F:/codex/deepresearch/backend/src/services/scholarly_rerank.py)
- [scholarly_graph.py](F:/codex/deepresearch/backend/src/services/scholarly_graph.py)
- [scholarly_contracts.py](F:/codex/deepresearch/backend/src/services/scholarly_contracts.py)
- [run_scholarly_eval.py](F:/codex/deepresearch/backend/evals/run_scholarly_eval.py)
- [run_scholarly_live_smoke.py](F:/codex/deepresearch/backend/evals/run_scholarly_live_smoke.py)

### 这一阶段做了什么

#### 1. retrieval 从单层 fanout 升级为多阶段 pipeline

包括：

- query planning
- recall budget allocation
- source recall
- cross-source dedupe
- candidate pool shaping
- coarse rerank
- frontier decision
- frontier expansion
- final rerank

#### 2. frontier fallback 从兜底逻辑变成第二召回层

它不再只是“搜不到时补一把”，而是通过质量信号判断：

- high relevance 是否稀疏
- coarse score 是否偏低
- core query hit 是否不足

#### 3. 评测层从简单回归变成质量工作台

新增了：

- `Recall@20`
- `Recall@50`
- `nDCG@20`
- `CandidatePoolPurity`
- `CandidateDrift`
- `DirectHitCoverage`
- `FrontierContributionRate`
- `SourceContributionSummary`

#### 4. 前端补充 retrieval metadata 展示

但仍然保持：

- 不改路由名
- 不改 SSE 事件名
- 只追加 metadata 字段

### 这一阶段的亮点

#### 亮点 1：开始做策略，不只是做搜索

真正有技术含量的地方在于：

- 哪些 query 值得更多预算
- direct 和 frontier 如何分配 recall
- frontier 结果是否允许进入 top pool
- 如何抑制表面相关但主题漂移的候选

#### 亮点 2：开始做评测闭环

这让系统从“能跑的工具”升级成“能被优化的系统”。

### 适合初学者理解的一句话

> Phase 3 做的是“搜得更准、排得更稳、还能量化质量”。

---

## 7. 整个项目最值得讲的总亮点

如果面试官问你：“这个项目最强的地方是什么？”

你可以讲下面五点。

### 亮点 1：双工作流系统，而不是单功能 demo

项目同时支持：

- 通用 web research
- scholarly paper workbench

这说明架构不是为单一场景硬编码的。

### 亮点 2：研究过程被结构化了

无论是通用研究还是论文调研，系统都不是一次性生成，而是走结构化步骤。

### 亮点 3：支持人机协同

项目不是假设 AI 一次做对，而是支持：

- 任务笔记
- 人工筛选
- 会话回看
- 重筛选
- 导出

### 亮点 4：有状态、有持久化、有历史

这是很多 demo 没有的。

### 亮点 5：有评测、有 smoke、有工程闭环

这使它更像真正工程项目。

---

## 8. 你可以怎么讲这个项目

## 8.1 30 秒版本

> 这是一个本地 research system，前期我先做了一个 TODO 驱动的通用 DeepResearchAgent，用来把开放研究问题拆成任务、搜索、总结和生成报告；后面又把它扩展成一个面向 AI/CS 论文调研的 scholarly workbench，支持多源论文召回、会话持久化、人工筛选、报告导出和 retrieval 质量评测。整体技术栈是 `FastAPI + Vue + LangGraph + SQLite`。

## 8.2 2 分钟版本

> 这个项目的核心目标不是做一个聊天式问答，而是把研究工作流做成一个系统。  
> 第一阶段我先做了通用 `DeepResearchAgent`，它会把研究主题拆成 TODO tasks，然后逐任务调用搜索、做总结、同步任务笔记，最后生成结构化报告，并通过 SSE 输出进度。  
> 第二阶段我把它产品化成了一个 scholarly workbench，新增了 session、paper pool、人工筛选、SQLite 持久化、报告和导出，前后端通过稳定 API 契约协作。  
> 第三阶段我重点升级了 retrieval stack，把单层 fanout 升级成多阶段 pipeline，加入 query budgeting、frontier fallback、candidate shaping 和 eval workbench，让系统不仅能检索，而且能被量化评估和持续优化。

## 8.3 5 分钟版本

建议你按下面顺序讲：

1. 项目目标  
   这是研究系统，不是聊天壳。

2. 两条产品线  
   通用 DeepResearchAgent + scholarly workbench。

3. 三阶段演进  
   结构化研究流 -> 产品化工作台 -> retrieval quality 升级。

4. 核心技术链  
   FastAPI / SSE / LangGraph / Search / Notes / SQLite / Eval。

5. 技术亮点  
   多阶段工作流、会话持久化、人机协同、frontier fallback、质量评测。

6. 工程问题与解决  
   环境、编码、兼容性、限额、契约稳定性。

---

## 9. 给初学者看的关键概念解释

## 9.1 什么叫 TODO 驱动式研究

不是让模型一口气给答案。  
而是先拆成多个子任务，再分别处理。

这样做的好处是：

- 逻辑更清晰
- 容错更好
- 可流式显示进度
- 可针对每个任务保留笔记

## 9.2 什么叫 SSE

`SSE` 是服务器持续往前端推送单向事件的一种方式。

这个项目里它适合做：

- 任务开始
- 任务完成
- 论文召回完成
- 报告 chunk 输出

因为这个场景是“后端持续汇报进度”，而不是双方频繁双向对话。

## 9.3 什么叫 session

`session` 可以理解成一个研究项目档案。

里面保存了：

- topic
- 状态
- query/tasks
- papers
- metadata
- reports

有了 session，研究过程就不再是一次性的。

## 9.4 什么叫 note tool

它是把任务信息落到本地笔记的工具。

这样研究不是只活在模型上下文里，而是能留下可回看的记录。

## 9.5 什么叫 frontier fallback

有些研究方向很新、很窄，直接搜很容易召回不足。  
这时系统会扩到相邻概念、近期信号、或者更宽背景来补召回。

---

## 10. 从代码可以清楚看出的历史工程问题

这一节重点是前两阶段。

这些不一定来自我本轮的实时执行日志，但我可以从代码中明确看出：项目在早期就已经遇到并处理过这些问题。

## 10.1 OpenAI-compatible 接口可能返回空 `message.content`

证据位置：

- [agent.py](F:/codex/deepresearch/backend/src/agent.py:34)

在 `OpenAICompatibleLLM.invoke()` 里，代码显式处理了：

- 请求成功
- 但 `message.content` 为空
- 重试后仍为空

### 说明项目遇到过什么问题

说明项目不是只对接过“理想的 OpenAI 返回”，而是遇到过中转站或兼容接口返回结构不稳定的问题。

### 解决方式

- 封装 `OpenAICompatibleLLM`
- 加重试
- streaming 模式下没有 chunk 时，退回普通 `invoke`

### 你可以怎么讲

> 早期我发现 OpenAI-compatible 接口并不总是稳定返回 `message.content`，所以我没有把外部模型当成强可靠依赖，而是加了兼容层和回退逻辑。

## 10.2 控制台编码和依赖输出可能导致 Unicode 崩溃

证据位置：

- [search.py](F:/codex/deepresearch/backend/src/services/search.py:19)

这里专门有 `_ensure_unicode_console_output()`。

### 说明项目遇到过什么问题

说明早期运行环境在 Windows / GBK 控制台下，某些依赖打印 Unicode 时会导致问题。

### 解决方式

- 在 import 时就对 `stdout/stderr` 做 `utf-8` 重配置

### 你可以怎么讲

> 我在本地 Windows 环境里踩到过依赖输出 Unicode 导致的问题，所以把编码兼容前置处理，避免程序在导入阶段就崩。

## 10.3 模型存在 `429`、free-tier 和 quota 问题

证据位置：

- [agent.py](F:/codex/deepresearch/backend/src/agent.py:238)
- [reporter.py](F:/codex/deepresearch/backend/src/services/reporter.py:91)

代码里有大量针对：

- `429`
- `quota exceeded`
- `free tier`
- `resource_exhausted`

的处理。

### 说明项目遇到过什么问题

说明项目曾经运行在不稳定、有限额的模型环境里。

### 解决方式

- 重试
- 退避等待
- fallback text
- safe mode 限制任务数量

### 你可以怎么讲

> 我没有假设模型资源总是充足，而是把限额和降级路径当成系统设计的一部分。

## 10.4 Planner 输出不总是标准 JSON

证据位置：

- [planner.py](F:/codex/deepresearch/backend/src/services/planner.py:71)

可以看到 planner 同时支持：

- 从文本里提取 JSON
- 从数组提取
- 从 `TOOL_CALL` 表达式提取

### 说明项目遇到过什么问题

说明模型在任务规划阶段并不是每次都严格按期望格式返回。

### 解决方式

- 多种解析路径
- fallback task

### 你可以怎么讲

> 我对 LLM 输出采用了宽松解析，而不是强依赖唯一格式，这样可以提高系统稳定性。

## 10.5 任务笔记和任务状态需要同步

证据位置：

- [tool_events.py](F:/codex/deepresearch/backend/src/services/tool_events.py:92)

### 说明项目遇到过什么问题

如果 note 工具创建了笔记，但 task 对象没有同步 `note_id`，后续就无法稳定更新同一条任务笔记。

### 解决方式

- 记录工具调用
- 从工具结果里提取 `note_id`
- 回写到 `TodoItem`

### 你可以怎么讲

> 我把 tool call 也当作系统状态的一部分管理，而不是只看最终文本输出。

## 10.6 SQLite schema 需要兼容迭代

证据位置：

- [scholarly_store.py](F:/codex/deepresearch/backend/src/services/scholarly_store.py:457)

里面有 `_ensure_column()`。

### 说明项目遇到过什么问题

说明 scholarly workbench 在演进过程中，表结构是逐步扩展的，不是从一开始一次性设计完。

### 解决方式

- 初始化时检查列是否存在
- 缺失则补充列
- 避免引入额外 migration 系统

### 你可以怎么讲

> 这是一个本地工具型项目，所以我选择了轻量 schema 兼容方案，而不是一开始上复杂 migration。

---

## 11. 我本轮能直接确认的真实执行日志问题

这一节只写我本轮实际做项目升级时，真实碰到并解决的问题。

## 11.1 工作区一开始就有未提交改动

### 现象

`git status --short` 一开始就显示：

- `backend/src/services/scholarly_search.py`
- `backend/src/services/scholarly_store.py`
- `backend/src/services/scholarly_workflow.py`
- `frontend/src/App.vue`
- `frontend/src/services/api.ts`
- 以及多个未追踪目录

### 风险

如果不先读清楚就改，很容易覆盖掉已有半成品工作。

### 解决方式

- 先看 `git diff`
- 再按文件通读 `search / rerank / graph / workflow / eval / frontend`
- 确认哪些是已有 Phase 2/3 骨架，哪些是缺口

### 结果

避免了误回滚和误覆盖，只在已有骨架上继续补实现。

## 11.2 `uv` 默认缓存目录权限失败

### 现象

运行 `uv run ruff` 时失败，报错指向用户目录 cache 权限。

### 原因

当前执行环境对默认 `uv` cache 路径没有可靠写权限。

### 解决方式

把缓存路径切到项目目录：

```powershell
$env:UV_CACHE_DIR='F:\codex\deepresearch\.uv-cache'
```

### 结果

后续 `uv` 相关命令可以正常运行。

## 11.3 单测错误地用了系统 Python

### 现象

运行单测时报：

```text
ModuleNotFoundError: No module named 'dotenv'
```

### 原因

调用的是系统 Python，不是项目虚拟环境。

### 解决方式

改用：

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_scholarly_graph
```

### 结果

测试恢复正常，并最终 `12` 个测试全部通过。

## 11.4 PowerShell 不接受 `&&` 链式命令

### 现象

后台服务启动命令里用了 `&&`，PowerShell 报语法错误。

### 原因

命令写法带有 `cmd` 风格假设，但当前 shell 是 `PowerShell`。

### 解决方式

- 改为更直接的启动方式
- 使用项目环境解释器直接起服务

### 结果

backend 成功通过 `/healthz` 验证。

## 11.5 `ruff` 报出大量 docstyle 噪音

### 现象

初次静态检查时，出现很多：

- `D202`
- `D107`
- `D102`

以及一个真实可改的：

- `UP028`

### 原因

这些 service 文件启用了较严格的 pydocstyle 规则，但当前仓库并不是完全按这种规则维护。

### 解决方式

- 真实代码问题直接修掉
- 文档风格类问题做文件级 suppress

### 结果

`ruff` 最终通过。

## 11.6 frontend preview 进程导致临时日志文件难清理

### 现象

删除 `.tmp_frontend*.log` 后文件又出现。

### 原因

不是删除失败，而是 preview 进程还在写日志。

### 解决方式

- 先检查端口
- 再停止对应进程
- 再清理临时日志

### 结果

工作区恢复干净，没有遗留临时日志。

---

## 12. 这次最终验证结果

本轮实际执行并通过的验证包括：

```powershell
backend\.venv\Scripts\ruff.exe check ...
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_scholarly_graph
backend\.venv\Scripts\python.exe backend/evals/run_scholarly_eval.py
backend\.venv\Scripts\python.exe backend/evals/run_scholarly_live_smoke.py --base-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:4173
npm.cmd run build
```

### 结果摘要

- `ruff` 通过
- `unittest` 通过，`12` 个测试全绿
- `run_scholarly_eval.py` 通过
- `run_scholarly_live_smoke.py` 通过
- `npm.cmd run build` 通过

### 当前一组关键指标

- `Recall@20 = 1.0`
- `Recall@50 = 1.0`
- `nDCG@20 = 0.975`
- `CandidatePoolPurity@20 = 0.929`
- `CandidateDrift@20 = 0.0`
- `DirectHitCoverage = 0.812`

---

## 13. 面试时可以直接回答的问题

## 13.1 这个项目到底是什么

推荐回答：

> 这是一个本地 research system。前期我先做了一个 TODO 驱动的通用研究代理，后面把它扩展成了面向 AI/CS 论文调研的 scholarly workbench，最终形成了一套支持任务规划、流式检索、会话持久化、人工筛选和质量评测的完整系统。

## 13.2 这个项目为什么不只是普通 RAG demo

推荐回答：

> 因为它不只是检索加回答，而是完整工作流。它有任务拆解、工具调用、任务笔记、流式事件、session 持久化、paper pool、frontier fallback、eval 和 smoke 验证，这些都超出了普通 demo 的范围。

## 13.3 你最有技术含量的部分是什么

推荐回答：

> 我觉得有两块。第一块是把通用研究流程做成任务化、可流式、可落笔记的 agent workflow；第二块是把 scholarly retrieval 从单层 fanout 升级成多阶段 pipeline，并补齐 frontier fallback 和质量评测。

## 13.4 为什么用 LangGraph

推荐回答：

> 因为这个系统不是一条直线。无论是 writer-reviewer 流程，还是 scholarly retrieval 流程，都有状态、分支和阶段事件，用图来编排比一个大函数更清楚，也更利于测试和扩展。

## 13.5 为什么用 SQLite

推荐回答：

> 这是本地工作台而不是高并发线上服务，SQLite 的优点是部署简单、调试方便、足够支持 session / paper / report 的结构化持久化。

## 13.6 这个项目怎么体现工程能力

推荐回答：

> 主要体现在三点：第一，我把流程拆成服务层和 graph 层；第二，我做了稳定 API/SSE 契约和本地持久化；第三，我补了 lint、unit test、offline eval 和 live smoke，让系统有工程闭环。

---

## 14. 一段你可以直接背的项目总结

> 我做了一个本地 research system，前端基于 `Vue + TypeScript`，后端基于 `FastAPI`。  
> 项目一开始是一个 TODO 驱动的通用 `DeepResearchAgent`，用来把开放研究问题拆成任务、调用搜索工具、生成任务总结并输出最终报告；后面我把它扩展成一个 scholarly workbench，支持多源论文召回、会话持久化、人工筛选、报告导出和前端工作台。  
> 在最新阶段，我又把 scholarly retrieval 从单层 fanout 升级成了多阶段 pipeline，加入 query budgeting、frontier fallback、candidate shaping 和评测脚本，使它不仅能用，而且能量化优化。  
> 整体上，这个项目更像一个“有工作流、有状态、有评测的人机协同研究系统”，而不是一个简单的模型调用 demo。

---

## 15. 最后一句建议

讲这个项目时，最重要的不是背库名，而是把下面这句话讲稳：

> 我做的是一个从通用研究代理演进到 scholarly workbench 的完整研究系统，重点不只是“生成答案”，而是“把研究过程结构化、持久化、可评测化”。

只要你把这句话讲明白，这个项目的技术含量就能立住。
