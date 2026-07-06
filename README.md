# CiteWeave

CiteWeave is a local-first scholarly workbench for AI/CS literature review, integrating paper retrieval, screening, close reading, and evidence memo synthesis.

面向 AI/CS 文献调研的本地化学术工作平台，集成多源检索、人工筛选、全文阅读与研究备忘录生成。

![CiteWeave home view](docs/assets/readme-home.png)

## Overview

CiteWeave organizes literature review as a persistent research session rather than a one-shot generation flow.  
Each session keeps its candidate pool, screening decisions, full-text artifacts, memo content, and export results in a local workspace.

## Capabilities

- Multi-source retrieval from `OpenAlex`, `arXiv`, and `Semantic Scholar`
- Session-based screening with `include`, `exclude`, `save`, and `to_read`
- Local PDF upload and full-text extraction
- Structured memo synthesis from confirmed evidence
- Evidence stratification with `core`, `adjacent_transfer`, and `off_target`
- Export to `Markdown` and `BibTeX`

## Workflow

1. Create a research session for a specific topic.
2. Generate query tasks and recall candidate papers from multiple sources.
3. Review, rerank, and curate the candidate pool in the workbench.
4. Upload PDF or resolve full text when additional evidence is needed.
5. Generate a research memo from the confirmed paper set.
6. Export the memo and references for downstream writing.

## Stack

- Frontend: `Vue 3`, `TypeScript`, `Vite`
- Backend: `FastAPI`, `Pydantic`
- Workflow graph: `LangGraph`
- Storage: `SQLite`
- Model access: `openai` client with OpenAI-compatible endpoints
- Full-text parsing: `pypdf`

## Run Locally

Requirements:

- `Python >= 3.10`
- `uv`
- `Node.js`
- A usable OpenAI-compatible model endpoint, or local `Ollama` / `LMStudio`

Backend:

```powershell
cd backend
uv sync
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Default local addresses:

- frontend: `http://localhost:5173`
- backend: `http://localhost:8000`

## Main Endpoints

- `POST /research/sessions`
- `GET /research/sessions/{id}`
- `PATCH /research/sessions/{id}/papers/{paper_id}`
- `POST /research/sessions/{id}/papers/{paper_id}/pdf`
- `POST /research/sessions/{id}/papers/{paper_id}/fulltext/resolve`
- `POST /research/sessions/{id}/report/stream`
- `GET /research/sessions/{id}/export.md`
- `GET /research/sessions/{id}/export.bib`

## Repository Layout

```text
backend/
  src/
    main.py
    config.py
    services/
      scholarly_workflow.py
      scholarly_search.py
      scholarly_rerank.py
      scholarly_fulltext.py
      scholarly_report_pipeline.py
      scholarly_graph.py
      scholarly_store.py
  tests/
frontend/
  src/
    App.vue
    services/api.ts
docs/
  assets/
scripts/
```

## Scope

Appropriate for:

- AI/CS literature review preparation
- Personal research assistance
- Local-first workflow prototyping
- Portfolio presentation of retrieval, workbench, and memo generation

Not intended for:

- Public production deployment
- Replacement of academic databases
- Fully automatic final-review writing without human verification

## License

MIT. See [LICENSE](LICENSE).
