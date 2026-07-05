# 文献妙妙屋 · 简历导向技术路线图 V2

## 结论

下一阶段不应该继续只做 UI 打磨，关键原因是这个项目如果要放进简历，必须从“可用工具”升级为“有明确算法层、Agent 编排层、评测层的科研检索系统”。

一句话目标：

**把当前的文献工作台升级成一个可解释、可评测、可扩展的 Agentic Scholarly Retrieval System。**

---

## 1. 当前项目基线

当前 codebase 已经具备这些基础：

- 学术检索工作流后端
- 会话持久化
- 本地历史记录与删除
- 候选论文筛选工作台
- 研究报告生成
- 三栏前端工作台
- 双语/研究备忘录方向的 UI 基础

这说明项目已经从 demo 走到了“产品雏形”。

但如果要用于简历，现在还缺三类硬核能力：

1. **更先进的检索与重排算法**
2. **更明确的 Agent 编排与状态机设计**
3. **离线评测与可量化指标**

---

## 2. V2 项目定义

建议把项目重新定义为：

### 英文名

`Agentic Scholarly Retrieval & Review Workbench`

### 中文描述

一个面向 AI/CS 科研问题的智能文献检索与研究审阅系统，支持问题拆解、多源召回、精排筛选、引文扩展、双语研究备忘录生成，以及人在回路的工作流审阅。

### 简历导向卖点

- 不是普通 RAG
- 不是普通论文搜索
- 不是单轮问答

而是：

**多阶段检索系统 + Agent 工作流 + 人在回路 + 可量化评测**

---

## 3. 下一阶段核心目标

下一阶段建议只聚焦 4 个目标。

### 目标 A：引入 Agent 编排层

建议目标：

- 用 `LangGraph` 重构当前 scholarly workflow
- 明确节点、状态、分支与恢复逻辑

建议拆分节点：

1. `query_planning`
2. `multi_source_retrieval`
3. `dedup_normalization`
4. `candidate_reranking`
5. `frontier_fallback`
6. `citation_expansion`
7. `session_persistence`
8. `report_generation`
9. `human_review_sync`

预期结果：

- 工作流更可解释
- 更容易展示“Agent engineering”
- 更方便后续加 checkpoint / retry / human-in-the-loop

---

### 目标 B：把“50 -> 20”做成真正的算法链路

建议目标：

- 保留当前多源召回 50 篇逻辑
- 新增精排模块，把 top-50 压到 top-20

建议算法分层：

1. **第一层召回**
   - OpenAlex
   - arXiv
   - Semantic Scholar

2. **第二层粗排序**
   - BM25 / keyword overlap
   - embedding similarity

3. **第三层精排**
   - `ColBERT` late interaction reranker

输出：

- `recall_score`
- `semantic_score`
- `citation_signal`
- `novelty_score`
- `final_score`

预期结果：

- 项目能讲清楚“为什么是这 20 篇”
- 有明确算法层，不只是 prompt + API

---

### 目标 C：支持“前沿问题 / 少文献问题”的自适应检索

这是你这个项目非常适合做出的差异点。

建议目标：

- 针对 exact match 很少的问题，自动切换到 frontier mode

建议策略：

1. LLM 做 query decomposition
2. 如果高相关召回太少：
   - 启动 `HyDE`
   - 扩展 adjacent concepts
   - 加入 broader ancestor directions
3. 输出时显式区分：
   - `directly relevant`
   - `adjacent`
   - `background`
   - `frontier / speculative`

预期结果：

- 系统对新方向更有解释力
- 这会成为你项目最独特的研究工作流卖点

---

### 目标 D：建立离线评测体系

这是简历里最缺但最值钱的部分。

建议目标：

- 建一个小型 benchmark
- 能比较不同检索与精排策略

建议指标：

#### 检索指标

- `Recall@20`
- `Recall@50`
- `nDCG@20`
- `MRR`

#### 文献工作台指标

- top-20 中真实高相关论文占比
- 最新论文覆盖率
- 不同方向多样性
- citation coverage

#### 报告指标

- evidence grounding rate
- hallucination rate（人工抽样）
- bilingual consistency（抽样检查）

预期结果：

- 你能在简历或面试里讲“系统提升了什么”
- 不再只是“我做了个产品”

---

## 4. V2 推荐技术栈

### 必选

- `LangGraph`
- `OpenAI API / current report model`
- `OpenAlex`
- `arXiv`
- `Semantic Scholar`

### 强烈推荐

- `ColBERT` reranker
- `HyDE`
- `BM25 + dense hybrid retrieval`

### 进阶可选

- `DSPy`
- `GraphRAG` 风格的 citation / topic graph expansion
- `RAPTOR` 用于全文层级摘要

---

## 5. 推荐代码结构升级

当前后端已经有 scholarly workflow 的基础文件。下一阶段建议往下面收敛：

### backend

建议新增或细化模块：

- `services/workflow_graph.py`
  - LangGraph graph 定义

- `services/retrieval_router.py`
  - 普通检索 / frontier fallback 路由

- `services/reranker.py`
  - coarse rerank / ColBERT rerank

- `services/citation_graph.py`
  - citation expansion / related work neighborhood

- `services/evaluation.py`
  - 离线评测入口

- `prompts/`
  - query planner
  - frontier explainer
  - report generator

### frontend

前端下一阶段不建议大重构，建议只为新能力补展示：

- 检索模式标签
  - `strict`
  - `frontier`
  - `adjacent-expanded`

- 排序解释字段
  - 为什么入选 top-20

- citation expansion 来源说明

- report 中 evidence trace

---

## 6. 分阶段实施建议

### Phase 1：系统骨架升级

目标：

- 接入 LangGraph
- 保持当前 UI 与 API 基本可用
- 不引入太多新模型

完成标准：

- scholarly workflow 跑在 graph 上
- 事件流仍可推到前端
- 会话、报告、筛选不回退

---

### Phase 2：检索质量升级

目标：

- 加 hybrid retrieval
- 加 ColBERT rerank
- 加 frontier fallback

完成标准：

- top-20 质量可量化提升
- 前沿问题有可解释 fallback 路径

---

### Phase 3：研究智能升级

目标：

- citation expansion
- report grounding
- evaluation harness

完成标准：

- 可以输出“研究脉络”
- 可以比较不同算法版本
- 可以写成项目实验结果

---

## 7. 下一阶段最小可执行目标

如果只做一个短周期版本，我建议你下一阶段只做下面 3 件事：

1. **把后端 workflow 改造成 LangGraph**
2. **把 top-50 -> top-20 做成 hybrid + rerank**
3. **补一个最小评测脚本和样例集**

这是最像“简历版本升级”的组合。

原因很直接：

- `LangGraph` 解决“系统设计”
- `rerank` 解决“检索算法”
- `evaluation` 解决“结果可信度”

这三件事一旦补上，项目就会从工具原型升级成一个很像样的 AI systems project。

---

## 8. 简历 bullet 草稿

后续如果 V2 做完，可以往这个方向写：

- Built an **agentic scholarly retrieval and review system** for AI/CS literature analysis with multi-stage query planning, paper screening, and bilingual research memo generation.
- Refactored the backend workflow into a **LangGraph-based stateful execution graph** with streaming progress updates, resumable state, and human-in-the-loop review.
- Designed a **hybrid scholarly retrieval pipeline** with multi-source recall and top-k reranking to reduce noisy candidates from 50 to 20.
- Added **frontier-aware retrieval fallback** and citation-based expansion to support emerging topics with sparse direct literature.
- Implemented an **offline evaluation suite** for retrieval quality and report grounding metrics.

---

## 9. 我建议的直接下一步

直接下一步不要再做 UI。

建议改做：

1. 梳理现有 `scholarly_workflow.py` 的状态机
2. 设计 LangGraph 节点与 state schema
3. 先接入一个最小 rerank 层
4. 同时准备一个小 benchmark 数据集

等这层打稳，再回头继续前端解释性展示，会更值。

