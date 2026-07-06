# ruff: noqa: D102,D107,D202

"""High-level scholarly research session workflow."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
import base64

from config import Configuration
from services.scholarly_contracts import (
    default_workflow_metrics,
    merge_llm_usage,
)
from services.scholarly_fulltext import ScholarlyFulltextService
from services.scholarly_llm import ScholarlyLLMService
from services.scholarly_graph import ScholarlyWorkflowGraph
from services.scholarly_report_pipeline import (
    ScholarlyReportPipeline,
    ScholarlyReportResult,
)
from services.scholarly_rerank import ScholarlyScreeningService
from services.scholarly_search import ScholarlySearchService
from services.scholarly_store import ScholarlyStore


class ScholarlyResearchService:
    """Coordinate scholarly recall, screening, reporting, and exports."""

    def __init__(
        self,
        config: Configuration,
        *,
        store: ScholarlyStore | None = None,
        search: ScholarlySearchService | None = None,
        screening: ScholarlyScreeningService | None = None,
    ) -> None:
        self.config = config
        self.store = store or ScholarlyStore(config.scholarly_db_path)
        self.search = search or ScholarlySearchService(config)
        self.screening = screening or ScholarlyScreeningService(config)
        self.llm = ScholarlyLLMService(config)
        self.fulltext = ScholarlyFulltextService(config, self.store)
        self.report_pipeline = ScholarlyReportPipeline(
            config,
            fulltext=self.fulltext,
            llm=self.llm,
        )
        self.graph = ScholarlyWorkflowGraph(
            config,
            self.store,
            self.search,
            self.screening,
        )

    def create_session(self, topic: str, parent_session_id: str | None = None) -> dict[str, Any]:
        """Create a session and run the full recall/screening pipeline."""

        state = self.graph.invoke(topic, parent_session_id=parent_session_id)
        if state.get("error"):
            raise RuntimeError(str(state["error"]))
        return self.store.get_session_detail(state["session_id"])

    def create_session_stream(
        self,
        topic: str,
        parent_session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream session creation progress events."""

        try:
            for update in self.graph.stream(topic, parent_session_id=parent_session_id):
                if not isinstance(update, dict) or not update:
                    continue
                _, payload = next(iter(update.items()))
                if not isinstance(payload, dict):
                    continue
                yield from payload.get("events") or []
        except Exception as exc:
            yield {"type": "error", "detail": str(exc)}

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.store.list_sessions()

    def get_session_detail(self, session_id: str) -> dict[str, Any]:
        return self.store.get_session_detail(session_id)

    def delete_session(self, session_id: str) -> None:
        self.store.delete_session(session_id)

    def rescreen_session(self, session_id: str) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        query_tasks = detail.get("queries") or []
        papers = detail["papers"]
        coarse_ranked = self.screening.coarse_rerank(
            detail["topic"],
            papers,
            query_tasks,
            limit=self.config.scholarly_candidate_limit,
        )
        decision = self.screening.frontier_decision(
            detail["topic"],
            coarse_ranked,
            query_tasks,
        )
        screened = self.screening.finalize_rerank(
            detail["topic"],
            coarse_ranked,
            query_tasks,
            limit=self.config.scholarly_candidate_limit,
        )
        selected = [
            paper
            for paper in screened
            if paper.get("selected")
        ][: self.config.scholarly_selection_limit]
        existing_metadata = detail.get("metadata") or {}
        metrics = default_workflow_metrics(existing_metadata.get("metrics"))
        metrics.update(
            {
                **decision["metrics"],
                "coarse_candidate_count": len(coarse_ranked),
                "final_candidate_count": len(screened),
                "selected_count": len(selected),
            }
        )
        frontier_mode = existing_metadata.get("frontier_mode")
        frontier_reason = existing_metadata.get("frontier_reason")
        metadata = self.search.build_session_metadata(
            topic=detail["topic"],
            query_tasks=query_tasks,
            final_papers=screened,
            source_statuses=detail.get("source_statuses") or {},
            skipped_sources=detail.get("skipped_sources") or [],
            degradation_notices=detail.get("degradation_notices") or [],
            frontier_mode=(
                bool(frontier_mode)
                if frontier_mode is not None
                else bool(decision["frontier_mode"])
            ),
            frontier_reason=frontier_reason or decision["frontier_reason"],
            metrics=metrics,
            existing_metadata=existing_metadata,
        )
        self.store.upsert_session_papers(session_id, screened, clear_existing=True)
        self.store.update_session(
            session_id,
            status="ready",
            queries=query_tasks,
            metadata=metadata,
        )
        return self.store.get_session_detail(session_id)

    def update_paper(
        self,
        session_id: str,
        paper_id: str,
        *,
        user_status: str | None = None,
        selected: bool | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if user_status == "excluded":
            selected = False
        elif user_status in {"included", "saved", "to_read"} and selected is None:
            selected = True
        return self.store.update_session_paper(
            session_id,
            paper_id,
            user_status=user_status,
            selected=selected,
            tags=tags,
        )

    def generate_report(self, session_id: str) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        result = self._build_report(detail, persist_artifacts=True)
        report = self.store.create_report(session_id, result.content)
        self._persist_report_metadata(detail, result)
        return report

    def generate_report_stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        detail = self.store.get_session_detail(session_id)
        result = self._build_report(detail, persist_artifacts=True)
        for chunk in self._chunk_text(result.content, 900):
            yield {"type": "report_chunk", "session_id": session_id, "content": chunk}
        report = self.store.create_report(session_id, result.content)
        self._persist_report_metadata(detail, result)
        yield {"type": "report_done", "session_id": session_id, "report": report}

    def upload_paper_pdf(
        self,
        session_id: str,
        paper_id: str,
        *,
        filename: str,
        content_base64: str,
    ) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        paper = next((item for item in detail["papers"] if item["id"] == paper_id), None)
        if paper is None:
            raise KeyError(paper_id)
        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise ValueError("无效的 PDF Base64 内容。") from exc
        self.fulltext.upload_pdf(
            paper_id=paper_id,
            filename=filename,
            content=content,
        )
        return self.store.get_session_paper(session_id, paper_id)

    def resolve_paper_fulltext(
        self,
        session_id: str,
        paper_id: str,
    ) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        paper = next((item for item in detail["papers"] if item["id"] == paper_id), None)
        if paper is None:
            raise KeyError(paper_id)
        self.fulltext.ensure_fulltext(paper)
        return self.store.get_session_paper(session_id, paper_id)

    def derive_session(self, parent_session_id: str, topic: str) -> dict[str, Any]:
        parent = self.store.get_session(parent_session_id)
        child = self.store.create_session(topic, parent_session_id=parent["id"])
        return child

    def export_markdown(self, session_id: str) -> str:
        detail = self.store.get_session_detail(session_id)
        report = self.store.latest_report(session_id)
        if report:
            return report["content_markdown"]
        return self._build_report(detail, persist_artifacts=False).content

    def export_bibtex(self, session_id: str) -> str:
        detail = self.store.get_session_detail(session_id)
        entries = [self._bibtex_entry(paper) for paper in self._included_papers(detail["papers"])]
        return "\n\n".join(entry for entry in entries if entry).strip() + "\n"

    def _included_papers(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        included = [
            paper
            for paper in papers
            if paper.get("selected") and paper.get("user_status") != "excluded"
        ]
        return sorted(included, key=lambda item: item.get("rank") or 9999)[: self.config.scholarly_selection_limit]

    def _build_report(
        self,
        detail: dict[str, Any],
        *,
        persist_artifacts: bool,
    ) -> ScholarlyReportResult:
        papers = self._included_papers(detail["papers"])
        return self.report_pipeline.build(
            detail,
            papers,
            persist_artifacts=persist_artifacts,
        )

    def _persist_report_metadata(
        self,
        detail: dict[str, Any],
        result: ScholarlyReportResult,
    ) -> None:
        metadata = dict(detail.get("metadata") or {})
        metadata["report_context"] = result.report_context
        metadata["report_artifacts"] = result.report_artifacts
        metadata["llm_usage"] = merge_llm_usage(
            metadata.get("llm_usage"),
            result.llm_usage,
        )
        self.store.update_session(
            detail["id"],
            status="reported",
            metadata=metadata,
        )

    @staticmethod
    def _chunk_text(text: str, size: int) -> Iterator[str]:
        for index in range(0, len(text), size):
            yield text[index : index + size]

    def _bibtex_entry(self, paper: dict[str, Any]) -> str:
        title = str(paper.get("title") or "Untitled")
        key = self._bibtex_key(paper)
        authors = " and ".join(paper.get("authors") or [])
        fields = {
            "title": title,
            "author": authors,
            "year": paper.get("year"),
            "journal": paper.get("venue"),
            "doi": paper.get("doi"),
            "url": paper.get("url") or paper.get("pdf_url"),
        }
        body = []
        for name, value in fields.items():
            if value:
                body.append(f"  {name} = {{{self._bibtex_escape(str(value))}}}")
        return "@article{" + key + ",\n" + ",\n".join(body) + "\n}"

    @staticmethod
    def _bibtex_key(paper: dict[str, Any]) -> str:
        authors = paper.get("authors") or []
        first = re.sub(r"[^A-Za-z0-9]", "", authors[0].split()[-1] if authors else "paper")
        year = paper.get("year") or "nd"
        title_token = re.sub(r"[^A-Za-z0-9]", "", str(paper.get("title") or "work").split()[0])
        return f"{first}{year}{title_token}"[:48] or "paper"

    @staticmethod
    def _bibtex_escape(value: str) -> str:
        return value.replace("{", "\\{").replace("}", "\\}")
