<!-- refreshed: 2026-06-20 -->
# Architecture

**Analysis Date:** 2026-06-20

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                     Browser Vue Application                  │
├──────────────────────┬──────────────────────────────────────┤
│   UI + state surface │      API/SSE client                   │
│ `frontend/src/App.vue`│ `frontend/src/services/api.ts`       │
└──────────┬───────────┴──────────────────┬───────────────────┘
           │ POST /research/stream          │ Server-Sent Events
           ▼                                ▼
┌─────────────────────────────────────────────────────────────┐
│                         FastAPI API                          │
│                  `backend/src/main.py`                       │
└──────────┬──────────────────────────────────────────────────┘
           │ builds `Configuration`, instantiates agent
           ▼
┌─────────────────────────────────────────────────────────────┐
│                 DeepResearchAgent Orchestrator               │
│                  `backend/src/agent.py`                      │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ Planning     │ Search       │ Summarize    │ Report/Review  │
│`services/    │`services/    │`services/    │`services/      │
│ planner.py`  │ search.py`   │ summarizer.py`│ reporter.py`  │
└──────┬───────┴──────┬───────┴──────┬───────┴────────┬───────┘
       │              │              │                │
       ▼              ▼              ▼                ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ LLM Provider│ │ Search APIs │ │ NoteTool    │ │ SSE Events  │
│ Ollama/etc. │ │ Duck/Tavily │ │ `notes/`    │ │ Frontend UI │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Vue app shell | Captures research topic, tracks streaming workflow state, renders tasks, sources, tool calls, and final report | `frontend/src/App.vue` |
| API client | Opens `POST /research/stream`, parses SSE `data:` frames, and emits structured events to the UI | `frontend/src/services/api.ts` |
| FastAPI app | Defines HTTP routes, CORS, startup config logging, request DTOs, and response streaming | `backend/src/main.py` |
| Configuration | Reads env vars, models supported search backends, normalizes LLM base URLs, and resolves model IDs | `backend/src/config.py` |
| DeepResearchAgent | Coordinates LLM agents, notes, search, task execution, LangGraph report writing/review, and streaming events | `backend/src/agent.py` |
| State models | Defines task and workflow dataclasses passed between orchestration layers | `backend/src/models.py` |
| Prompts | Holds planner, summarizer, and report writer instructions | `backend/src/prompts.py` |
| PlanningService | Converts a research topic into structured `TodoItem` tasks from LLM JSON output | `backend/src/services/planner.py` |
| Search service | Dispatches configured search backend through HelloAgents `SearchTool` and formats source context | `backend/src/services/search.py` |
| SummarizationService | Builds per-task prompts, runs/streams task summaries, and strips tool call artifacts | `backend/src/services/summarizer.py` |
| ReportingService | Builds final report prompts, handles 429 fallback behavior, and strips tool call artifacts | `backend/src/services/reporter.py` |
| ToolCallTracker | Records HelloAgents tool calls, attaches note IDs to tasks, and emits frontend-ready tool events | `backend/src/services/tool_events.py` |
| Notes guidance | Builds prompt snippets that direct agents to create/read/update notes | `backend/src/services/notes.py` |
| Text processing | Removes `[TOOL_CALL:...]` text from model output before user-facing display | `backend/src/services/text_processing.py` |
| Utilities | Formats search sources, deduplicates URLs, and strips `<think>` blocks | `backend/src/utils.py` |

## Pattern Overview

**Overall:** Thin HTTP adapter over an in-process agentic workflow coordinator, with a single Vue SPA consuming streaming event updates.

**Key Characteristics:**
- Backend uses request-scoped `DeepResearchAgent` instances from `backend/src/main.py`; each request builds a fresh orchestrator from `Configuration`.
- Core workflow is service-oriented inside one process: planner, search, summarizer, reporter, and tool-event tracking are separate Python modules under `backend/src/services/`.
- Long-running work is surfaced to the browser as Server-Sent Events from `backend/src/main.py`, while synchronous output remains available through `POST /research`.
- State is dataclass-based in `backend/src/models.py`; there is no database-backed domain model.
- Frontend state is local Vue reactivity in `frontend/src/App.vue`; there is no router or global store.

## Layers

**Frontend UI Layer:**
- Purpose: User input, visual progress, task selection, source display, tool call display, and final report display.
- Location: `frontend/src/App.vue`, `frontend/src/style.css`.
- Contains: Vue template, Composition API refs/computed values, SSE event reducers, local UI helpers, and component-scoped CSS.
- Depends on: `frontend/src/services/api.ts`, Vue.
- Used by: Browser users through `frontend/src/main.ts`.

**Frontend API Layer:**
- Purpose: Isolate HTTP/SSE transport details from UI state updates.
- Location: `frontend/src/services/api.ts`.
- Contains: `ResearchRequest`, `ResearchStreamEvent`, and `runResearchStream(...)`.
- Depends on: Browser `fetch`, `ReadableStream`, `TextDecoder`, and `VITE_API_BASE_URL`.
- Used by: `frontend/src/App.vue`.

**HTTP Adapter Layer:**
- Purpose: Convert HTTP payloads to backend configuration and agent calls.
- Location: `backend/src/main.py`.
- Contains: `create_app()`, DTOs, CORS middleware, `/healthz`, `/research`, and `/research/stream`.
- Depends on: `backend/src/config.py`, `backend/src/agent.py`, FastAPI, Loguru.
- Used by: Uvicorn and frontend API calls.

**Configuration Layer:**
- Purpose: Centralize runtime configuration from environment and per-request overrides.
- Location: `backend/src/config.py`.
- Contains: `SearchAPI` enum and `Configuration` Pydantic model.
- Depends on: `os.environ`, `os.getenv`, Pydantic.
- Used by: `backend/src/main.py`, `backend/src/agent.py`, `backend/src/services/search.py`, `backend/src/services/planner.py`, `backend/src/services/summarizer.py`, and `backend/src/services/reporter.py`.

**Orchestration Layer:**
- Purpose: Own the end-to-end research workflow.
- Location: `backend/src/agent.py`.
- Contains: `DeepResearchAgent`, LLM initialization, HelloAgents tool setup, LangGraph writer/reviewer graph, task loops, streaming output, and final report persistence.
- Depends on: services in `backend/src/services/`, state in `backend/src/models.py`, prompts in `backend/src/prompts.py`, HelloAgents, LangGraph.
- Used by: `backend/src/main.py`.

**Domain Services Layer:**
- Purpose: Encapsulate task planning, search, summarization, reporting, notes, event tracking, and text cleanup.
- Location: `backend/src/services/`.
- Contains: `planner.py`, `search.py`, `summarizer.py`, `reporter.py`, `notes.py`, `tool_events.py`, and `text_processing.py`.
- Depends on: `backend/src/models.py`, `backend/src/config.py`, `backend/src/utils.py`, HelloAgents APIs.
- Used by: `backend/src/agent.py`.

**Persistence Layer:**
- Purpose: Store note artifacts written by HelloAgents NoteTool.
- Location: `backend/notes/` and, in the current tree, `backend/src/notes/`.
- Contains: Markdown note files and `notes_index.json`.
- Depends on: Local filesystem.
- Used by: `NoteTool` initialized in `backend/src/agent.py` and note path metadata emitted by `backend/src/services/tool_events.py`.

## Data Flow

### Streaming Research Request Path

1. Browser submits form in `frontend/src/App.vue` and calls `runResearchStream(...)` from `frontend/src/services/api.ts`.
2. `frontend/src/services/api.ts` sends `POST ${baseURL}/research/stream` with `topic` and optional `search_api`.
3. `backend/src/main.py` receives `ResearchRequest`, calls `_build_config(...)`, creates `DeepResearchAgent`, and returns `StreamingResponse`.
4. `DeepResearchAgent.run_stream(...)` in `backend/src/agent.py` creates `SummaryState`, emits initial status, and calls `PlanningService.plan_todo_list(...)`.
5. `PlanningService` in `backend/src/services/planner.py` prompts the planner agent, parses JSON tasks, and returns `TodoItem` objects.
6. `DeepResearchAgent._run_tasks_stream(...)` iterates tasks and delegates each task to `_execute_task(...)`.
7. `_execute_task(...)` calls `dispatch_search(...)` in `backend/src/services/search.py`, which uses `_GLOBAL_SEARCH_TOOL.run(...)` with the configured backend.
8. `prepare_research_context(...)` in `backend/src/services/search.py` formats sources; `SummarizationService.stream_task_summary(...)` in `backend/src/services/summarizer.py` streams summary chunks.
9. Tool calls are recorded by `ToolCallTracker` in `backend/src/services/tool_events.py` and emitted as SSE `tool_call` payloads.
10. LangGraph in `backend/src/agent.py` runs `writer_node` and `reviewer_node` to produce and review the report.
11. `_persist_final_report(...)` in `backend/src/agent.py` writes a conclusion note through `NoteTool` when notes are enabled.
12. `backend/src/main.py` serializes each event as `data: {...}\n\n`; `frontend/src/services/api.ts` decodes frames; `frontend/src/App.vue` updates task state, logs, sources, summaries, tool calls, and final report.

### Synchronous Research Request Path

1. `POST /research` in `backend/src/main.py` builds `Configuration` from env and request overrides.
2. `DeepResearchAgent.run(...)` in `backend/src/agent.py` executes planning, task search, summarization, LangGraph report generation, and final note persistence without incremental SSE output.
3. `backend/src/main.py` maps `SummaryStateOutput.todo_items` into JSON and returns `ResearchResponse`.

### Frontend Event Reduction

1. `frontend/src/services/api.ts` parses `data:` frames into `ResearchStreamEvent`.
2. `frontend/src/App.vue` handles event types including `status`, `todo_list`, `task_status`, `sources`, `task_summary_chunk`, `tool_call`, `final_report`, and `error`.
3. `frontend/src/App.vue` stores task-level data in `TodoTaskView`, including `summary`, `sourceItems`, `notices`, `noteId`, `notePath`, and `toolCalls`.

**State Management:**
- Backend workflow state uses `SummaryState`, `TodoItem`, and `SummaryStateOutput` dataclasses in `backend/src/models.py`.
- Backend concurrent task state mutation is guarded by `self._state_lock` in `backend/src/agent.py` when appending search context and source summaries.
- Tool call event state lives in `ToolCallTracker` in `backend/src/services/tool_events.py`.
- Frontend UI state uses Vue `ref`, `reactive`, and `computed` in `frontend/src/App.vue`.

## Key Abstractions

**Configuration:**
- Purpose: Typed runtime settings and env override handling.
- Examples: `SearchAPI`, `Configuration.from_env(...)`, `Configuration.sanitized_ollama_url()` in `backend/src/config.py`.
- Pattern: Pydantic settings-like model without a separate settings library.

**DeepResearchAgent:**
- Purpose: Request-scoped coordinator that owns agents, tools, workflow graph, task execution, and output events.
- Examples: `DeepResearchAgent.run(...)`, `DeepResearchAgent.run_stream(...)`, and `DeepResearchAgent._execute_task(...)` in `backend/src/agent.py`.
- Pattern: Facade/orchestrator over smaller service classes.

**Service Classes:**
- Purpose: Keep LLM prompt execution, search, reporting, and streaming behavior behind focused modules.
- Examples: `PlanningService` in `backend/src/services/planner.py`, `SummarizationService` in `backend/src/services/summarizer.py`, and `ReportingService` in `backend/src/services/reporter.py`.
- Pattern: Constructor-injected agent/config dependencies plus narrow public methods.

**ToolCallTracker:**
- Purpose: Convert HelloAgents tool listener payloads into durable in-memory events and task note metadata.
- Examples: `record(...)`, `drain(...)`, `_attach_note_to_task(...)` in `backend/src/services/tool_events.py`.
- Pattern: Stateful event buffer with cursor-based draining.

**SSE Event Contract:**
- Purpose: Stream backend progress to frontend.
- Examples: event generation in `backend/src/agent.py` and parsing in `frontend/src/services/api.ts`.
- Pattern: Typed-by-convention JSON events with a `type` field.

**TodoTaskView:**
- Purpose: Frontend projection of backend tasks plus UI-specific sources, tool calls, and note metadata.
- Examples: interface and reducers in `frontend/src/App.vue`.
- Pattern: Local view model maintained from SSE events.

## Entry Points

**Backend ASGI App:**
- Location: `backend/src/main.py`.
- Triggers: Uvicorn import of `app` or direct `python backend/src/main.py`.
- Responsibilities: Create FastAPI app, register routes, configure CORS, log sanitized startup configuration, and translate HTTP requests into agent runs.

**Research Agent API:**
- Location: `backend/src/agent.py`.
- Triggers: `DeepResearchAgent.run(...)` from `/research` and `DeepResearchAgent.run_stream(...)` from `/research/stream`.
- Responsibilities: Execute full research workflow and return either final output or streaming events.

**Frontend Mount:**
- Location: `frontend/src/main.ts`.
- Triggers: Vite/browser loading `frontend/index.html`.
- Responsibilities: Mount `App.vue` to `#app` and load global CSS.

**Frontend Research Submission:**
- Location: `frontend/src/App.vue`.
- Triggers: User form submit.
- Responsibilities: Reset workflow state, create `AbortController`, call `runResearchStream(...)`, and reduce stream events into UI state.

## Architectural Constraints

- **Threading:** FastAPI/Uvicorn serves requests in-process; the workflow itself is synchronous generator-based for SSE streaming. `backend/src/agent.py` imports `Thread` and `Queue`, but the active task loop is sequential in `_run_tasks_stream(...)`.
- **Global state:** `_GLOBAL_SEARCH_TOOL = SearchTool(backend="hybrid")` is module-level shared state in `backend/src/services/search.py`.
- **Module imports:** Backend modules use direct sibling imports such as `from config import Configuration` in `backend/src/main.py`; run commands must make `backend/src` importable.
- **Circular imports:** No circular import chain detected in the scanned backend files.
- **Persistence:** Notes are local filesystem artifacts managed by HelloAgents `NoteTool`, not by a repository-owned storage adapter.
- **Authentication:** No auth boundary exists in `backend/src/main.py`; do not add user-specific assumptions without introducing an auth design.
- **CORS:** `backend/src/main.py` allows all origins; production deployments must account for this explicitly.
- **Git state:** The working directory is not a Git repository, so repository state cannot be inferred from `git status`.

## Anti-Patterns

### Bypassing Configuration

**What happens:** Directly reading provider settings outside `backend/src/config.py` would duplicate env parsing.
**Why it's wrong:** `Configuration.from_env(...)` already centralizes env aliases and request overrides, and `backend/src/agent.py` assumes normalized values from that model.
**Do this instead:** Add new runtime settings to `Configuration` in `backend/src/config.py`, then consume `self.config` in `backend/src/agent.py` or services under `backend/src/services/`.

### Writing Tool Event Shapes Inline In The Frontend Only

**What happens:** Adding new backend event types only in `frontend/src/App.vue` without corresponding backend emissions creates undocumented stream contracts.
**Why it's wrong:** The SSE contract is shared across `backend/src/agent.py`, `backend/src/services/tool_events.py`, `frontend/src/services/api.ts`, and `frontend/src/App.vue`.
**Do this instead:** Emit a `type`-tagged dict from `backend/src/agent.py` or `ToolCallTracker`, parse it generically in `frontend/src/services/api.ts`, and add a focused reducer branch in `frontend/src/App.vue`.

### Adding Search Logic To The Agent Loop

**What happens:** Embedding provider-specific search behavior directly in `DeepResearchAgent._execute_task(...)`.
**Why it's wrong:** `backend/src/services/search.py` owns dispatch and source formatting; duplicating it fragments backend selection and formatting behavior.
**Do this instead:** Extend `SearchAPI` in `backend/src/config.py` and `dispatch_search(...)` or `prepare_research_context(...)` in `backend/src/services/search.py`.

## Error Handling

**Strategy:** Convert expected configuration errors to HTTP 400, guard unexpected API failures with HTTP 500 or SSE `error` events, and use fallback report generation for selected LLM quota failures.

**Patterns:**
- `ValueError` during request setup is returned as HTTP 400 in `backend/src/main.py`.
- Unexpected synchronous research failures return HTTP 500 with generic `"Research failed"` in `backend/src/main.py`.
- Streaming failures are logged and emitted as `{"type": "error", "detail": ...}` from `backend/src/main.py`.
- Search failures are logged and re-raised in `backend/src/services/search.py`.
- Report agent 429/quota failures fall back to template reports in `backend/src/services/reporter.py` and `backend/src/agent.py`.
- Frontend non-OK HTTP responses throw `Error` in `frontend/src/services/api.ts`.

## Cross-Cutting Concerns

**Logging:** Backend logs sanitized startup configuration with `loguru` in `backend/src/main.py`; services use stdlib `logging` in `backend/src/agent.py` and `backend/src/services/`. Frontend logs parse and clipboard issues with `console` in `frontend/src/App.vue`.

**Validation:** Request validation uses Pydantic models in `backend/src/main.py`; runtime configuration validation uses Pydantic fields and enum coercion in `backend/src/config.py`; frontend TypeScript interfaces in `frontend/src/services/api.ts` and `frontend/src/App.vue` provide compile-time shape checks.

**Authentication:** Not implemented in `backend/src/main.py` or `frontend/src/services/api.ts`.

**Secrets:** API keys are referenced by name through `backend/src/config.py`; `backend/src/main.py` masks `llm_api_key` before logging.

**Internationalization/Text Encoding:** User-facing strings in `frontend/src/App.vue` and prompts in `backend/src/prompts.py` are primarily Chinese, but several files display mojibake in the current environment. Preserve existing encoding when editing these files.

---

*Architecture analysis: 2026-06-20*
