# deepresearch 本地运行说明

## 当前恢复状态

本项目已按“项目内隔离环境”恢复：

- 后端虚拟环境：`backend/.venv/`
- 前端依赖目录：`frontend/node_modules/`
- 后端依赖声明：`backend/pyproject.toml`
- 前端依赖声明：`frontend/package.json`

这不会把依赖安装到全局 Python，也不会影响你电脑上的其他工程。

## 环境要求

当前已验证工具：

- Python 3.13.3
- uv 0.11.21
- Node.js 24.16.0
- npm 11.13.0

项目后端声明 `requires-python = ">=3.10"`。如果后续 AI/LLM 相关依赖在 Python 3.13 下出现兼容问题，建议改用 Python 3.11 或 3.12 重建 `backend/.venv/`。

## 后端依赖恢复

在项目根目录执行：

```powershell
cd backend
uv sync
```

已补充的关键依赖：

- `huggingface-hub>=1.22.0`

原因：`hello-agents==0.2.9` 的导入链会使用 `huggingface_hub`，但原项目依赖没有显式声明它。

## 前端依赖恢复

```powershell
cd frontend
npm install
```

如果 `frontend/node_modules/` 已存在且 `npm run build` 通过，可以暂时不重新安装。

## 启动方式

推荐从项目根目录使用脚本启动。

后端：

```powershell
.\scripts\start-backend.ps1
```

后端地址：

```text
http://localhost:8000
```

前端另开一个终端：

```powershell
.\scripts\start-frontend.ps1
```

前端地址：

```text
http://localhost:5174
```

## 手动启动方式

后端：

```powershell
cd backend
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir src --host 0.0.0.0 --port 8000 --reload
```

前端：

```powershell
cd frontend
npm run dev
```

## 配置文件

后端配置主要来自：

- `backend/.env`
- `backend/src/config.py`

前端 API 地址来自：

- `frontend/.env.local`
- `VITE_API_BASE_URL`

默认前端会访问：

```text
http://localhost:8000
```

## 科研文献工作台

当前版本新增了 AI/CS 文献调研工作台：

- 默认召回约 50 篇候选论文，筛选 20 篇进入工作台。
- 支持 arXiv、Semantic Scholar、OpenAlex 多源召回和去重。
- 每篇论文保留标题、作者、年份、链接、摘要、相关性标签和筛选理由。
- 支持本地 SQLite 历史会话、论文标注、报告保存。
- 支持基于确认文献生成中文主报告，并导出 Markdown 与 BibTeX。
- 第一版不自动下载 PDF，不绕过付费墙；开放 PDF 只保留链接。

可选环境变量：

```text
SCHOLARLY_DB_PATH=./scholarly_sessions.sqlite3
SCHOLARLY_CANDIDATE_LIMIT=50
SCHOLARLY_SELECTION_LIMIT=20
OPENALEX_API_KEY=
OPENALEX_EMAIL=
SEMANTIC_SCHOLAR_API_KEY=
UNPAYWALL_EMAIL=
```

新接口前缀：

```text
/research/sessions
/research/sessions/stream
```

## 已验证项

- `uv sync` 可重建 `backend/.venv/`
- Python 文件语法编译通过
- 前端 `npm run build` 通过

## 当前遗留问题

- 后端实际启动验证仍需单独确认运行。启动会读取本地环境变量并初始化 HelloAgents/SearchTool。
- 当前 `.git` 目录看起来不是完整仓库；如果要进入正式维护，应重新初始化或修复 git 仓库。
- `backend/src/prompts.py` 和部分历史 notes 可能存在中文乱码，需要后续专项检查。
- 项目目前没有测试体系，建议先补最小后端单元测试和前端流式解析测试。
- 后端 CORS 当前开放所有来源，不适合直接用于生产公网部署。
