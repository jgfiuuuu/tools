# CiteWeave

Local-first scholarly workbench for paper retrieval, screening, close reading, and evidence memo synthesis.

一个面向 AI/CS 文献调研的本地研究工作台，强调持续筛选、证据整理和研究备忘录生成，而不是一次性回答。

<<<<<<< HEAD
<p align="center">
  一个面向 AI/CS 文献调研的本地研究工作台，强调持续筛选、证据整理和研究备忘录生成。
</p>
=======
![CiteWeave home view](docs/assets/readme-home.png)
>>>>>>> d589219 (docs: 重写 README 首页展示)

## What It Is

`CiteWeave` focuses on one workflow:

1. Create a research session.
2. Recall papers from multiple scholarly sources.
3. Screen, rerank, and manually curate the candidate pool.
4. Upload PDF or resolve full text when needed.
5. Generate a structured research memo from confirmed evidence.
6. Export the result as `Markdown` or `BibTeX`.

It is not a chat shell and not a generic PDF manager. It is a workbench for maintaining research context across retrieval, review, and reporting.

<<<<<<< HEAD
一个偏研究过程管理的本地工具。
=======
## Core Capabilities
>>>>>>> d589219 (docs: 重写 README 首页展示)

- Multi-source paper recall with `OpenAlex`, `arXiv`, and `Semantic Scholar`
- Persistent research sessions backed by local `SQLite`
- Human-in-the-loop screening with `include / exclude / save / to_read`
- PDF upload and full-text extraction
- Tiered memo synthesis with `core`, `adjacent_transfer`, and `off_target`
- Export of memo content and references

<<<<<<< HEAD
主工作台把检索、筛选、精读和报告都收在同一个界面里，优先保留研究过程本身。
=======
## Stack
>>>>>>> d589219 (docs: 重写 README 首页展示)

- Frontend: `Vue 3`, `TypeScript`, `Vite`
- Backend: `FastAPI`, `Pydantic`
- Workflow: `LangGraph`
- Storage: `SQLite`
- LLM access: `openai` client with OpenAI-compatible endpoints
- Full text: `pypdf`

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

<<<<<<< HEAD
=======
Detailed local setup notes are in [README.zh-CN.md](README.zh-CN.md).
>>>>>>> d589219 (docs: 重写 README 首页展示)

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

Good fit:

- AI/CS literature review preparation
- Personal research assistance
- Local-first workflow prototyping
- Portfolio presentation of retrieval, workbench, and memo generation

Not the target:

- Public production deployment
- Full replacement for academic databases
- Fully automatic final-review writing without human verification

## License

MIT. See [LICENSE](LICENSE).
