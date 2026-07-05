# Codebase Structure

**Analysis Date:** 2026-06-20

## Directory Layout

```text
deepresearch/
├── backend/                         # Python FastAPI backend and local note data
│   ├── pyproject.toml               # Backend package, dependency, build, and Ruff config
│   ├── uv.lock                      # Python dependency lockfile
│   ├── .env                         # Environment configuration file present; contents not read
│   ├── .env.example                 # Example environment file present; contents not read
│   ├── notes/                       # Local persisted NoteTool notes and notes index
│   └── src/                         # Backend application source
│       ├── main.py                  # FastAPI app, routes, CORS, startup logging
│       ├── agent.py                 # DeepResearchAgent workflow coordinator
│       ├── config.py                # Runtime configuration and SearchAPI enum
│       ├── models.py                # Workflow dataclasses
│       ├── prompts.py               # Planner/summarizer/reporter prompts
│       ├── utils.py                 # Source formatting and text cleanup helpers
│       ├── notes/                   # Additional local notes data under source tree
│       └── services/                # Backend domain services
├── frontend/                        # Vue/Vite frontend
│   ├── package.json                 # Frontend scripts and dependencies
│   ├── package-lock.json            # npm lockfile
│   ├── vite.config.ts               # Vite config and dev server port
│   ├── tsconfig.json                # Main TypeScript config
│   ├── tsconfig.node.json           # Vite config TypeScript project
│   ├── index.html                   # Vite HTML entry
│   ├── .env.local                   # Frontend env file present; contents not read
│   └── src/                         # Frontend application source
│       ├── main.ts                  # Vue mount entry
│       ├── App.vue                  # Main UI and local state container
│       ├── style.css                # Global baseline CSS
│       ├── env.d.ts                 # Vite env typings
│       └── services/
│           └── api.ts               # Backend SSE API client
└── .planning/
    └── codebase/                    # Generated codebase maps
```

Ignored during mapping: `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`, and `*.egg-info/`.

## Directory Purposes

**`backend/`:**
- Purpose: Python backend package, dependency metadata, runtime env files, and local note workspace.
- Contains: `backend/pyproject.toml`, `backend/uv.lock`, `backend/src/`, and `backend/notes/`.
- Key files: `backend/pyproject.toml`, `backend/uv.lock`, `backend/src/main.py`, `backend/src/agent.py`.

**`backend/src/`:**
- Purpose: FastAPI app and research workflow source.
- Contains: entrypoint modules, configuration, dataclasses, prompt templates, utility helpers, services, and local notes data.
- Key files: `backend/src/main.py`, `backend/src/agent.py`, `backend/src/config.py`, `backend/src/models.py`, `backend/src/prompts.py`, `backend/src/utils.py`.

**`backend/src/services/`:**
- Purpose: Focused service modules used by `DeepResearchAgent`.
- Contains: `planner.py`, `search.py`, `summarizer.py`, `reporter.py`, `notes.py`, `tool_events.py`, and `text_processing.py`.
- Key files: `backend/src/services/search.py` for external search, `backend/src/services/tool_events.py` for tool-call event mapping, and `backend/src/services/summarizer.py` for task summary streaming.

**`backend/notes/`:**
- Purpose: Local NoteTool workspace containing generated notes and `notes_index.json`.
- Contains: Markdown notes such as `backend/notes/note_20260401_164255_0.md` and index `backend/notes/notes_index.json`.
- Key files: `backend/notes/notes_index.json`.

**`backend/src/notes/`:**
- Purpose: Additional note workspace data currently located inside source tree.
- Contains: `backend/src/notes/notes_index.json`.
- Key files: `backend/src/notes/notes_index.json`.

**`frontend/`:**
- Purpose: Vite/Vue frontend project.
- Contains: package metadata, TypeScript config, Vite config, HTML entry, env file, source directory, and generated build/dependency directories.
- Key files: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`.

**`frontend/src/`:**
- Purpose: Browser application source.
- Contains: Vue mount entry, main app component, global CSS, Vite env typing, and frontend service modules.
- Key files: `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/style.css`, `frontend/src/services/api.ts`.

**`.planning/codebase/`:**
- Purpose: Generated codebase intelligence documents for planning and execution workflows.
- Contains: `STACK.md`, `INTEGRATIONS.md`, `ARCHITECTURE.md`, and `STRUCTURE.md`.
- Key files: `.planning/codebase/STACK.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`.

## Key File Locations

**Entry Points:**
- `backend/src/main.py`: FastAPI `app`, route registration, direct Uvicorn startup.
- `frontend/src/main.ts`: Vue app mount.
- `frontend/index.html`: Browser HTML entry for Vite.

**Configuration:**
- `backend/pyproject.toml`: Python package metadata, dependencies, build backend, Ruff settings.
- `backend/uv.lock`: Locked Python dependency graph.
- `backend/src/config.py`: Runtime env configuration model and `SearchAPI` enum.
- `frontend/package.json`: Frontend scripts and dependencies.
- `frontend/package-lock.json`: Locked npm dependency graph.
- `frontend/vite.config.ts`: Vue plugin and dev server port `5174`.
- `frontend/tsconfig.json`: Strict TypeScript settings and `@/*` path alias.
- `frontend/tsconfig.node.json`: TypeScript project config for `vite.config.ts`.
- `frontend/src/env.d.ts`: Vite client env typings.

**Core Logic:**
- `backend/src/agent.py`: Top-level research orchestration, LLM setup, LangGraph report flow, SSE event generation.
- `backend/src/models.py`: Shared state dataclasses for tasks and workflow output.
- `backend/src/prompts.py`: LLM prompts for task planning, task summaries, and report writing.
- `backend/src/services/planner.py`: Topic-to-task conversion and planner output parsing.
- `backend/src/services/search.py`: Search backend dispatch and source context preparation.
- `backend/src/services/summarizer.py`: Task summary generation and streaming.
- `backend/src/services/reporter.py`: Final report prompt construction and fallback behavior.
- `backend/src/services/tool_events.py`: Tool call recording and note metadata synchronization.
- `backend/src/services/notes.py`: NoteTool prompt guidance generation.
- `backend/src/services/text_processing.py`: User-facing text cleanup for tool-call artifacts.
- `backend/src/utils.py`: Shared source formatting, deduplication, and thinking-token cleanup.
- `frontend/src/App.vue`: Main UI behavior, stream event reducers, and display state.
- `frontend/src/services/api.ts`: Streaming API client.

**Testing:**
- Not detected. No backend `tests/` directory, no frontend `*.test.*` files, and no Vitest/Jest/Pytest config files were found in the scanned source.

**Generated/Local State:**
- `backend/notes/`: Generated local notes and index.
- `backend/src/notes/`: Additional generated/local notes under source tree.
- `backend/.venv/`: Python virtual environment; ignore for source changes.
- `frontend/node_modules/`: npm dependencies; ignore for source changes.
- `frontend/dist/`: Vite build output; ignore for source changes.
- `backend/helloagents_deep_researcher.egg-info/` and `backend/src/helloagents_deep_researcher.egg-info/`: Python packaging metadata; ignore for normal feature work.

## Naming Conventions

**Files:**
- Backend modules use snake_case Python filenames: `backend/src/services/tool_events.py`, `backend/src/services/text_processing.py`.
- Backend service modules use singular responsibility names: `planner.py`, `search.py`, `summarizer.py`, `reporter.py`, `notes.py`.
- Frontend TypeScript modules use short lower-case names: `frontend/src/main.ts`, `frontend/src/services/api.ts`.
- Vue component uses PascalCase SFC naming: `frontend/src/App.vue`.
- Config files keep ecosystem-standard names: `backend/pyproject.toml`, `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`.

**Directories:**
- Backend source lives under `backend/src/`.
- Backend service code lives under `backend/src/services/`.
- Frontend source lives under `frontend/src/`.
- Frontend API client modules live under `frontend/src/services/`.
- Local note workspaces are named `notes/`, as in `backend/notes/` and `backend/src/notes/`.

## Where to Add New Code

**New Backend API Endpoint:**
- Primary code: add route handlers inside `create_app()` in `backend/src/main.py`.
- Request/response models: define small Pydantic models near existing `ResearchRequest` and `ResearchResponse` in `backend/src/main.py` unless reused across modules.
- Shared workflow behavior: call into `backend/src/agent.py` or a service under `backend/src/services/`.

**New Runtime Setting:**
- Primary code: add a field to `Configuration` in `backend/src/config.py`.
- Env alias: add explicit env name handling inside `Configuration.from_env()` in `backend/src/config.py`.
- Consumer code: read through `self.config` in `backend/src/agent.py` or service constructors under `backend/src/services/`.

**New Search Backend:**
- Primary code: extend `SearchAPI` in `backend/src/config.py`.
- Dispatch behavior: update `dispatch_search(...)` in `backend/src/services/search.py`.
- Frontend option: add the backend value to `searchOptions` in `frontend/src/App.vue`.

**New Agent Workflow Step:**
- Primary code: add orchestration in `backend/src/agent.py`.
- If the step is reusable or complex, create a focused service in `backend/src/services/`.
- State shape: add fields to `SummaryState` or `TodoItem` in `backend/src/models.py`.
- Streaming event: emit a `type`-tagged dict in `backend/src/agent.py` and handle it in `frontend/src/App.vue`.

**New Frontend API Call:**
- Transport code: add function and interfaces in `frontend/src/services/api.ts`.
- UI state and event handling: update `frontend/src/App.vue`.
- Environment-dependent base URLs: continue using `VITE_API_BASE_URL` from `frontend/src/services/api.ts`.

**New Frontend View/Component:**
- Current app has a single-component architecture in `frontend/src/App.vue`.
- For small additions, place local state and rendering in `frontend/src/App.vue`.
- For reusable or growing UI sections, create new Vue SFCs under `frontend/src/components/` and import them from `frontend/src/App.vue`; this directory does not currently exist.

**Utilities:**
- Backend shared text/source helpers: `backend/src/utils.py`.
- Backend service-specific helpers: colocate inside the relevant `backend/src/services/*.py` file.
- Frontend API helpers: `frontend/src/services/api.ts`.
- Frontend UI-only helpers: keep near the Composition API state in `frontend/src/App.vue` unless reused.

**Tests:**
- Testing structure is not established.
- Add backend tests under `backend/tests/` when introducing Python unit or integration tests.
- Add frontend tests under `frontend/src/**/*.test.ts` or a `frontend/tests/` directory only after adding the corresponding test runner config.

## Special Directories

**`backend/.venv/`:**
- Purpose: Python virtual environment.
- Generated: Yes.
- Committed: Should not be treated as source.

**`frontend/node_modules/`:**
- Purpose: npm dependency install directory.
- Generated: Yes.
- Committed: Should not be treated as source.

**`frontend/dist/`:**
- Purpose: Vite production build output.
- Generated: Yes.
- Committed: Should not be treated as source.

**`backend/notes/`:**
- Purpose: Local NoteTool workspace with generated research notes.
- Generated: Yes, by runtime tool calls.
- Committed: Present in the working tree; treat as local/runtime data unless product requirements say notes are fixtures.

**`backend/src/notes/`:**
- Purpose: Additional NoteTool workspace data under source.
- Generated: Yes.
- Committed: Present in the working tree; avoid adding app logic here.

**`backend/helloagents_deep_researcher.egg-info/` and `backend/src/helloagents_deep_researcher.egg-info/`:**
- Purpose: Python packaging metadata.
- Generated: Yes.
- Committed: Present in the working tree; ignore for feature work.

**`.planning/codebase/`:**
- Purpose: GSD codebase map documents.
- Generated: Yes, by codebase mapping workflow.
- Committed: Intended planning artifact.

---

*Structure analysis: 2026-06-20*
