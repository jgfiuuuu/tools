# Technology Stack

**Analysis Date:** 2026-06-20

## Languages

**Primary:**
- Python >=3.10 - Backend API, orchestration, LLM workflow, search dispatch, and note persistence under `backend/src/`.
- TypeScript 5.7.3 - Frontend API client and Vue component logic under `frontend/src/`.

**Secondary:**
- Vue Single File Component syntax - Main UI implementation in `frontend/src/App.vue`.
- CSS - Global baseline styles in `frontend/src/style.css` and component-scoped styles in `frontend/src/App.vue`.
- HTML - Vite host page in `frontend/index.html`.
- TOML - Python project and tooling configuration in `backend/pyproject.toml`.
- JSON - Frontend package metadata in `frontend/package.json`, TypeScript config in `frontend/tsconfig.json`, and local notes indexes such as `backend/notes/notes_index.json`.

## Runtime

**Environment:**
- Python >=3.10, declared by `backend/pyproject.toml`.
- Node.js runtime for Vite/Vue tooling; exact Node version is not pinned in `.nvmrc` or `frontend/package.json`.
- Browser runtime for the Vue SPA served from `frontend/`.

**Package Manager:**
- Python: `uv` lockfile present at `backend/uv.lock`; project metadata lives in `backend/pyproject.toml`.
- JavaScript: npm lockfile present at `frontend/package-lock.json`; package metadata lives in `frontend/package.json`.
- Lockfile: present for both backend and frontend.

## Frameworks

**Core:**
- FastAPI >=0.115.0 - HTTP API and SSE endpoint implementation in `backend/src/main.py`.
- Uvicorn >=0.32.0 - ASGI server used by the `if __name__ == "__main__"` entrypoint in `backend/src/main.py`.
- Vue 3.5.13 - Frontend application framework mounted from `frontend/src/main.ts`.
- Vite 6.0.7 - Frontend dev server and production build pipeline configured in `frontend/vite.config.ts`.
- HelloAgents 0.2.9 - LLM wrapper, tool-aware agents, SearchTool, and NoteTool usage in `backend/src/agent.py` and `backend/src/services/search.py`.
- LangGraph >=0.2.0 - Writer/reviewer state graph assembled in `backend/src/agent.py`.
- Pydantic - Runtime configuration model in `backend/src/config.py` and API payload models in `backend/src/main.py`.

**Testing:**
- Backend: no test runner config or `tests/` directory detected in the scanned tree.
- Frontend: no Vitest/Jest/Playwright test config detected in `frontend/`.
- Type checking is part of frontend build via `vue-tsc --noEmit` in `frontend/package.json`.

**Build/Dev:**
- Vite dev server uses port `5174` in `frontend/vite.config.ts`.
- Frontend production build command is `npm run build`, which runs `vue-tsc --noEmit && vite build` from `frontend/package.json`.
- Backend can be run directly through `python backend/src/main.py`, which starts Uvicorn on port `8000` in `backend/src/main.py`.
- Ruff is configured for backend linting in `backend/pyproject.toml`.
- Setuptools is the backend build backend via `backend/pyproject.toml`.

## Key Dependencies

**Critical:**
- `fastapi>=0.115.0` - Defines HTTP routes `/healthz`, `/research`, and `/research/stream` in `backend/src/main.py`.
- `hello-agents==0.2.9` - Provides `HelloAgentsLLM`, `ToolAwareSimpleAgent`, `SearchTool`, and `NoteTool` used across `backend/src/agent.py`, `backend/src/services/search.py`, and `backend/src/services/notes.py`.
- `langgraph>=0.2.0` - Provides `StateGraph`, `START`, and `END` for report writer/reviewer orchestration in `backend/src/agent.py`.
- `openai>=1.12.0` - Supports OpenAI-compatible LLM provider paths configured by `backend/src/config.py` and instantiated through HelloAgents in `backend/src/agent.py`.
- `ddgs>=9.6.1` - Supports DuckDuckGo-style search through HelloAgents search tooling selected by `backend/src/config.py`.
- `tavily-python>=0.5.0` - Supports Tavily search backend options exposed by `SearchAPI` in `backend/src/config.py`.
- `vue@^3.5.13` - Drives the reactive single-page UI in `frontend/src/App.vue`.
- `axios@^1.7.9` - Declared frontend dependency in `frontend/package.json`; the current API client uses `fetch` in `frontend/src/services/api.ts`.

**Infrastructure:**
- `python-dotenv==1.0.1` - Declared in `backend/pyproject.toml`; environment loading is otherwise handled through `os.environ` and `os.getenv` in `backend/src/config.py`.
- `requests>=2.31.0` - Declared backend HTTP dependency in `backend/pyproject.toml`.
- `loguru>=0.7.3` - Startup and request error logging in `backend/src/main.py`.
- `uvicorn[standard]>=0.32.0` - Local API serving in `backend/src/main.py`.
- `@vitejs/plugin-vue@^5.2.1` - Vue SFC compilation configured in `frontend/vite.config.ts`.
- `typescript@^5.7.3` and `vue-tsc@^2.2.0` - Strict TypeScript checking configured by `frontend/tsconfig.json`.

## Configuration

**Environment:**
- Backend configuration is centralized in `backend/src/config.py` using `Configuration.from_env()`.
- Supported backend env variable names include `LOCAL_LLM`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL_ID`, `LLM_BASE_URL`, `LMSTUDIO_BASE_URL`, `OLLAMA_BASE_URL`, `MAX_WEB_RESEARCH_LOOPS`, `FETCH_FULL_PAGE`, `STRIP_THINKING_TOKENS`, `USE_TOOL_CALLING`, `SEARCH_API`, `ENABLE_NOTES`, and `NOTES_WORKSPACE`.
- Frontend API base URL is read from `VITE_API_BASE_URL` in `frontend/src/services/api.ts`, defaulting to `http://localhost:8000`.
- Environment files are present at `backend/.env`, `backend/.env.example`, `backend/src/.env`, and `frontend/.env.local`; contents were not read.

**Build:**
- Backend project config: `backend/pyproject.toml`.
- Backend lockfile: `backend/uv.lock`.
- Frontend package config: `frontend/package.json`.
- Frontend lockfile: `frontend/package-lock.json`.
- Frontend Vite config: `frontend/vite.config.ts`.
- Frontend TypeScript configs: `frontend/tsconfig.json` and `frontend/tsconfig.node.json`.

## Platform Requirements

**Development:**
- Run backend from `backend/` or with `backend/src` on `PYTHONPATH` because modules import siblings as `from config import ...`, `from agent import ...`, and `from services...`.
- Ensure an OpenAI-compatible local or remote LLM provider is available. Defaults are `llm_provider=ollama`, `local_llm=llama3.2`, and `ollama_base_url=http://localhost:11434` in `backend/src/config.py`.
- Start backend on port `8000`; frontend `frontend/src/services/api.ts` expects this by default.
- Start frontend Vite dev server on port `5174` using `frontend/vite.config.ts`.

**Production:**
- Deployment target is not explicitly configured. The current shape is a separately served FastAPI backend plus Vite-built static frontend.
- No Dockerfile, CI workflow, or platform deployment config detected in the scanned tree.
- CORS is currently open to all origins in `backend/src/main.py`.

---

*Stack analysis: 2026-06-20*
