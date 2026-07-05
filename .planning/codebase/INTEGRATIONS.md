# External Integrations

**Analysis Date:** 2026-06-20

## APIs & External Services

**LLM Providers:**
- Ollama - Default local LLM provider for planning, task summarization, report writing, and report review.
  - SDK/Client: `hello-agents` via `HelloAgentsLLM` in `backend/src/agent.py`.
  - Auth: `LLM_API_KEY` optional; falls back to a placeholder `"ollama"` key for Ollama in `backend/src/agent.py`.
  - Base URL: `OLLAMA_BASE_URL`, normalized with `/v1` by `Configuration.sanitized_ollama_url()` in `backend/src/config.py`.
- LM Studio - Optional OpenAI-compatible local LLM provider.
  - SDK/Client: `hello-agents` via `HelloAgentsLLM` in `backend/src/agent.py`.
  - Auth: `LLM_API_KEY` optional.
  - Base URL: `LMSTUDIO_BASE_URL` in `backend/src/config.py`.
- Custom OpenAI-compatible provider - Optional provider path selected when `LLM_PROVIDER` is not `ollama` or `lmstudio`.
  - SDK/Client: `hello-agents` plus OpenAI-compatible client support from `openai`.
  - Auth: `LLM_API_KEY`.
  - Base URL and model: `LLM_BASE_URL`, `LLM_MODEL_ID`.

**Search Providers:**
- HelloAgents SearchTool hybrid adapter - Central search dispatch layer.
  - SDK/Client: `SearchTool(backend="hybrid")` in `backend/src/services/search.py`.
  - Auth: provider-specific keys, if required by selected backend, are expected to be supplied through environment consumed by HelloAgents or provider SDKs.
- DuckDuckGo - Default search backend exposed as `SearchAPI.DUCKDUCKGO`.
  - SDK/Client: HelloAgents `SearchTool` in `backend/src/services/search.py`, with `ddgs` declared in `backend/pyproject.toml`.
  - Auth: none detected.
- Tavily - Optional search backend exposed as `SearchAPI.TAVILY`.
  - SDK/Client: HelloAgents `SearchTool` plus `tavily-python` declared in `backend/pyproject.toml`.
  - Auth: not referenced directly in code; provider key is expected to be managed by the dependency/environment when used.
- Perplexity - Optional search backend exposed as `SearchAPI.PERPLEXITY`.
  - SDK/Client: HelloAgents `SearchTool` in `backend/src/services/search.py`.
  - Auth: not referenced directly in code; provider key is expected to be managed by the dependency/environment when used.
- SearXNG - Optional search backend exposed as `SearchAPI.SEARXNG`.
  - SDK/Client: HelloAgents `SearchTool` in `backend/src/services/search.py`.
  - Auth: not referenced directly in code; provider endpoint/auth is expected to be managed by HelloAgents/environment when used.
- Advanced - Optional backend exposed as `SearchAPI.ADVANCED`.
  - SDK/Client: HelloAgents `SearchTool` in `backend/src/services/search.py`.
  - Auth: not referenced directly in code.

**Frontend-to-Backend API:**
- FastAPI backend - Browser client calls the streaming research API.
  - SDK/Client: native `fetch` in `frontend/src/services/api.ts`.
  - Auth: none.
  - Base URL: `VITE_API_BASE_URL`, default `http://localhost:8000`.

## Data Storage

**Databases:**
- Not detected. There is no ORM, database client, migration system, or database connection string in the scanned source.

**File Storage:**
- Local filesystem notes are persisted through HelloAgents `NoteTool`.
  - Workspace config: `NOTES_WORKSPACE`, default `./notes` from `backend/src/config.py`.
  - Tool initialization: `NoteTool(workspace=self.config.notes_workspace)` in `backend/src/agent.py`.
  - Existing note data: `backend/notes/`, `backend/src/notes/`, and indexes such as `backend/notes/notes_index.json`.
- Local frontend build output is generated under `frontend/dist/`; this directory is ignored for mapping as a build artifact.

**Caching:**
- No external cache detected.
- In-process reusable search tool `_GLOBAL_SEARCH_TOOL` is module-level state in `backend/src/services/search.py`.
- In-memory event tracking is implemented by `ToolCallTracker` in `backend/src/services/tool_events.py`.

## Authentication & Identity

**Auth Provider:**
- Not detected.
  - Implementation: API routes in `backend/src/main.py` do not require user authentication or authorization.
  - CORS: `CORSMiddleware` in `backend/src/main.py` allows all origins, credentials, methods, and headers.

## Monitoring & Observability

**Error Tracking:**
- None detected.

**Logs:**
- Backend startup and error logs use `loguru` sinks in `backend/src/main.py`.
- Service modules use stdlib `logging` in `backend/src/agent.py`, `backend/src/services/planner.py`, `backend/src/services/search.py`, `backend/src/services/reporter.py`, `backend/src/services/tool_events.py`, and `backend/src/utils.py`.
- Frontend logs parse/tool errors to the browser console in `frontend/src/App.vue` and `frontend/src/services/api.ts`.

## CI/CD & Deployment

**Hosting:**
- Not detected. No Dockerfile, compose file, GitHub Actions workflow, or platform manifest was found in the scanned tree.

**CI Pipeline:**
- None detected.

## Environment Configuration

**Required env vars:**
- No env var is strictly required for the default local path if Ollama is running at the default URL.
- Set `LLM_PROVIDER` to choose `ollama`, `lmstudio`, or a custom provider.
- Set `LOCAL_LLM` or `LLM_MODEL_ID` to choose the model.
- Set `LLM_API_KEY` when the selected provider requires an API key.
- Set `LLM_BASE_URL`, `OLLAMA_BASE_URL`, or `LMSTUDIO_BASE_URL` when the provider endpoint differs from defaults.
- Set `SEARCH_API` or pass `search_api` from the frontend to choose `duckduckgo`, `tavily`, `perplexity`, `searxng`, or `advanced`.
- Set `FETCH_FULL_PAGE`, `MAX_WEB_RESEARCH_LOOPS`, `STRIP_THINKING_TOKENS`, and `USE_TOOL_CALLING` to tune backend workflow behavior.
- Set `ENABLE_NOTES` and `NOTES_WORKSPACE` to control local note persistence.
- Set `VITE_API_BASE_URL` for the frontend API target.

**Secrets location:**
- Environment files are present at `backend/.env`, `backend/.env.example`, `backend/src/.env`, and `frontend/.env.local`; contents were not read.
- Secret values must stay out of `.planning/codebase/` documents. Use env var names only.

## Webhooks & Callbacks

**Incoming:**
- HTTP health check: `GET /healthz` in `backend/src/main.py`.
- Synchronous research request: `POST /research` in `backend/src/main.py`.
- Streaming research request: `POST /research/stream` in `backend/src/main.py`, returning `text/event-stream`.
- No third-party webhook receiver endpoints detected.

**Outgoing:**
- LLM calls are made through `HelloAgentsLLM` in `backend/src/agent.py`.
- Search calls are made through `_GLOBAL_SEARCH_TOOL.run(...)` in `backend/src/services/search.py`.
- Browser outbound calls are made from `frontend/src/services/api.ts` to `${VITE_API_BASE_URL}/research/stream`.
- No explicit outgoing webhook callbacks detected.

---

*Integration audit: 2026-06-20*
