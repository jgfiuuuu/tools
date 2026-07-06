"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent
from services.scholarly_workflow import ScholarlyResearchService

# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., description="Research topic supplied by the user")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )


class CreateResearchSessionRequest(BaseModel):
    """Create a scholarly research session."""

    topic: str = Field(..., min_length=1, description="Research question or topic")
    parent_session_id: str | None = Field(
        default=None,
        description="Optional parent session when deriving a new research thread",
    )


class UpdateSessionPaperRequest(BaseModel):
    """Update user-side paper selection metadata."""

    user_status: str | None = Field(
        default=None,
        description="candidate, included, saved, to_read, or excluded",
    )
    selected: bool | None = Field(default=None)
    tags: list[str] | None = Field(default=None)


class UploadSessionPaperPdfRequest(BaseModel):
    """Upload a locally available PDF for one paper."""

    filename: str = Field(..., min_length=1)
    content_base64: str = Field(..., min_length=1)


class DeriveResearchSessionRequest(BaseModel):
    """Create a child session from an existing session."""

    topic: str = Field(..., min_length=1)


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


def _scholarly_service() -> ScholarlyResearchService:
    return ScholarlyResearchService(Configuration.from_env())


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app() -> FastAPI:
    app = FastAPI(title="文献妙妙屋 API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "DeepResearch configuration loaded: provider=%s model=%s base_url=%s search_api=%s "
            "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            _mask_secret(config.llm_api_key),
        )

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise HTTPException(status_code=500, detail="Research failed") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
            }
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    @app.get("/research/sessions")
    def list_research_sessions() -> list[dict[str, Any]]:
        return _scholarly_service().list_sessions()

    @app.post("/research/sessions")
    def create_research_session(payload: CreateResearchSessionRequest) -> dict[str, Any]:
        try:
            return _scholarly_service().create_session(
                payload.topic.strip(),
                parent_session_id=payload.parent_session_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Parent session not found") from exc
        except Exception as exc:
            logger.exception("Scholarly session creation failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/research/sessions/stream")
    def create_research_session_stream(payload: CreateResearchSessionRequest) -> StreamingResponse:
        service = _scholarly_service()

        def event_iterator() -> Iterator[str]:
            for event in service.create_session_stream(
                payload.topic.strip(),
                parent_session_id=payload.parent_session_id,
            ):
                yield _sse(event)
            yield _sse({"type": "done"})

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.get("/research/sessions/{session_id}")
    def get_research_session(session_id: str) -> dict[str, Any]:
        try:
            return _scholarly_service().get_session_detail(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.delete("/research/sessions/{session_id}")
    def delete_research_session(session_id: str) -> dict[str, Any]:
        try:
            _scholarly_service().delete_session(session_id)
            return {"deleted": True, "session_id": session_id}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.post("/research/sessions/{session_id}/screen")
    def screen_research_session(session_id: str) -> dict[str, Any]:
        try:
            return _scholarly_service().rescreen_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.patch("/research/sessions/{session_id}/papers/{paper_id}")
    def update_research_session_paper(
        session_id: str,
        paper_id: str,
        payload: UpdateSessionPaperRequest,
    ) -> dict[str, Any]:
        try:
            return _scholarly_service().update_paper(
                session_id,
                paper_id,
                user_status=payload.user_status,
                selected=payload.selected,
                tags=payload.tags,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc

    @app.post("/research/sessions/{session_id}/papers/{paper_id}/pdf")
    def upload_research_session_paper_pdf(
        session_id: str,
        paper_id: str,
        payload: UploadSessionPaperPdfRequest,
    ) -> dict[str, Any]:
        try:
            return _scholarly_service().upload_paper_pdf(
                session_id,
                paper_id,
                filename=payload.filename.strip(),
                content_base64=payload.content_base64,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc

    @app.post("/research/sessions/{session_id}/papers/{paper_id}/fulltext/resolve")
    def resolve_research_session_paper_fulltext(
        session_id: str,
        paper_id: str,
    ) -> dict[str, Any]:
        try:
            return _scholarly_service().resolve_paper_fulltext(session_id, paper_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc

    @app.post("/research/sessions/{session_id}/report")
    def generate_research_report(session_id: str) -> dict[str, Any]:
        try:
            return _scholarly_service().generate_report(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.post("/research/sessions/{session_id}/report/stream")
    def generate_research_report_stream(session_id: str) -> StreamingResponse:
        service = _scholarly_service()

        def event_iterator() -> Iterator[str]:
            try:
                for event in service.generate_report_stream(session_id):
                    yield _sse(event)
                yield _sse({"type": "done"})
            except KeyError:
                yield _sse({"type": "error", "detail": "Session not found"})
            except Exception as exc:
                logger.exception("Report generation failed")
                yield _sse({"type": "error", "detail": str(exc)})

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.post("/research/sessions/{session_id}/derive")
    def derive_research_session(
        session_id: str,
        payload: DeriveResearchSessionRequest,
    ) -> dict[str, Any]:
        try:
            return _scholarly_service().derive_session(session_id, payload.topic.strip())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.get("/research/sessions/{session_id}/export.md", response_class=PlainTextResponse)
    def export_research_session_markdown(session_id: str) -> str:
        try:
            return _scholarly_service().export_markdown(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    @app.get("/research/sessions/{session_id}/export.bib", response_class=PlainTextResponse)
    def export_research_session_bibtex(session_id: str) -> str:
        try:
            return _scholarly_service().export_bibtex(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
