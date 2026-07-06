"""Structured scholarly memo synthesis backed by evidence cards."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import Configuration
from services.scholarly_contracts import default_llm_usage, merge_llm_usage
from services.scholarly_fulltext import ResolvedPaperFulltext, ScholarlyFulltextService
from services.scholarly_llm import ScholarlyLLMService
from services.scholarly_store import make_id, utc_now

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a",
    "an",
    "and",
    "approach",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "paper",
    "papers",
    "study",
    "task",
    "the",
    "to",
    "using",
    "with",
}

REPORT_TONE_LABELS = {
    "judgment": "判断",
    "evidence": "证据",
    "note": "说明",
    "action": "行动",
    "speculation": "推测",
}

SECTION_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "report-positioning",
        "title": "Report Positioning / 报告定位",
        "icon": "scope",
    },
    {
        "id": "evidence-statement",
        "title": "Evidence Statement / 证据说明",
        "icon": "stack",
    },
    {
        "id": "research-landscape",
        "title": "Research Landscape / 研究现状与路线图",
        "icon": "map",
    },
    {
        "id": "evidence-strength",
        "title": "Evidence Strength & Disputes / 证据强弱与争议",
        "icon": "shield",
    },
    {
        "id": "research-gaps",
        "title": "Research Gaps / 研究空白",
        "icon": "gap",
    },
    {
        "id": "promising-directions",
        "title": "Promising Directions / 值得跟进的方向",
        "icon": "spark",
    },
    {
        "id": "confirmed-references",
        "title": "Confirmed References / 已确认参考文献",
        "icon": "book",
    },
)

TASK_SECTION_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": 1,
        "title": "研究现状与主线",
        "intent": "界定目标问题边界，区分核心证据与邻近可迁移路线。",
        "sections": ("report-positioning", "research-landscape"),
    },
    {
        "id": 2,
        "title": "证据强弱与真实分歧",
        "intent": "梳理哪类结论由正文级证据支撑，哪类只适合当作迁移线索。",
        "sections": ("evidence-statement", "evidence-strength"),
    },
    {
        "id": 3,
        "title": "研究空白与下一步方向",
        "intent": "汇总尚未解决的边界、评测与迁移问题，给出下一步行动方向。",
        "sections": ("research-gaps", "promising-directions"),
    },
)

TEXT_TOKENS = (
    "text-guided",
    "text guided",
    "text prompt",
    "language prompt",
    "prompt",
    "prompting",
    "promptable",
    "language-driven",
    "language guided",
    "text-conditioned",
    "text conditioned",
    "multimodal",
    "vision-language",
    "vision language",
    "vl",
    "referring",
)
REFERRING_TOKENS = (
    "referring",
    "referring expression",
    "phrase grounding",
    "expression comprehension",
)
SEGMENT_TOKENS = (
    "segmentation",
    "segment",
    "mask",
    "mask decoder",
    "pixel-wise",
    "pixel wise",
    "semantic segmentation",
    "instance segmentation",
    "panoptic segmentation",
)
DIFFUSION_TOKENS = (
    "diffusion",
    "diffusive",
    "denoise",
    "denoising",
    "latent",
    "ddpm",
    "stable diffusion",
    "score-based",
)
MEDICAL_TOKENS = (
    "medical",
    "mri",
    "radiology",
    "ultrasound",
    "ct scan",
    "ct-based",
    "pathology",
    "clinical",
    "lesion",
)
REMOTE_TOKENS = (
    "remote sensing",
    "satellite",
    "aerial",
    "earth observation",
    "geospatial",
)
GROUNDING_TOKENS = (
    "grounding",
    "phrase grounding",
    "localization",
    "bounding box",
    "bbox",
)
GENERATION_TOKENS = (
    "text-to-image",
    "text to image",
    "image generation",
    "image synthesis",
    "image editing",
    "generative",
    "layout-guided",
    "layout guided",
)
LAYOUT_TOKENS = (
    "layout",
    "document",
    "page",
    "typography",
)
DENSE_TOKENS = (
    "dense prediction",
    "pixel prediction",
    "depth",
    "matting",
    "saliency",
    "panoptic",
)
BENCHMARK_TOKENS = (
    "benchmark",
    "dataset",
    "evaluation",
    "metric",
    "generalization",
    "iou",
    "dice",
    "f1",
)

FIT_TIER_PRIORITY = {
    "core": 0,
    "adjacent_transfer": 1,
    "off_target": 2,
}


@dataclass(slots=True)
class SupportingNote:
    """Auxiliary deep-research note matched by topic."""

    id: str
    title: str
    note_type: str
    tags: list[str]
    created_at: str
    content: str
    path: str | None


@dataclass(slots=True)
class PaperEvidenceCard:
    """Structured evidence card extracted from one confirmed paper."""

    paper_id: str
    title: str
    year: int | None
    source: str | None
    evidence_level: str
    fulltext_source: str
    problem: str
    setting: str
    method: str
    key_claims: list[str]
    evidence: list[str]
    datasets_metrics: list[str]
    limitations: list[str]
    open_questions: list[str]
    source_excerpt_refs: list[str]
    fit_tier: str
    fit_reason: str
    task_family: str
    modality_family: str
    conditioning_family: str
    prediction_family: str


@dataclass(slots=True)
class ScholarlyReportTaskArtifact:
    """Internal fixed task artifact kept for note compatibility."""

    id: int
    title: str
    intent: str
    summary: str
    note_id: str | None = None
    note_path: str | None = None


@dataclass(slots=True)
class ScholarlyReportResult:
    """Final report output plus internal metadata artifacts."""

    content: str
    report_context: dict[str, Any]
    report_artifacts: dict[str, Any]
    llm_usage: dict[str, Any]


class NotesWorkspaceRepository:
    """Read and write local notes without external tool calls."""

    def __init__(self, workspace: str) -> None:
        self.workspace = self._resolve_workspace(Path(workspace))
        self.index_path = self.workspace / "notes_index.json"

    @staticmethod
    def _resolve_workspace(path: Path) -> Path:
        if path.is_absolute():
            return path

        backend_root = Path(__file__).resolve().parents[2]
        repo_root = Path(__file__).resolve().parents[3]
        for candidate in (Path.cwd() / path, backend_root / path, repo_root / path):
            if candidate.exists():
                return candidate.resolve()
        return (backend_root / path).resolve()

    def find_supporting_notes(self, topic: str, *, limit: int = 5) -> list[SupportingNote]:
        """Return up to ``limit`` deep-research notes matched by topic title terms."""

        notes_index = self._load_index()
        topic_terms = self._topic_terms(topic)
        candidates: list[dict[str, Any]] = []
        for entry in notes_index.get("notes") or []:
            if not isinstance(entry, dict):
                continue
            tags = entry.get("tags") or []
            if "deep_research" not in tags:
                continue
            title = str(entry.get("title") or "").strip()
            score = self._match_score(topic, topic_terms, title)
            if score <= 0:
                continue
            created_at = str(entry.get("created_at") or "")
            candidates.append(
                {
                    "entry": entry,
                    "score": score,
                    "type_priority": 0
                    if str(entry.get("type") or "") in {"task_state", "conclusion"}
                    else 1,
                    "created_ts": self._sort_key(created_at).timestamp()
                    if created_at
                    else 0.0,
                }
            )

        candidates.sort(
            key=lambda item: (
                -int(item["score"]),
                int(item["type_priority"]),
                -float(item["created_ts"]),
            )
        )

        selected: list[SupportingNote] = []
        for item in candidates[:limit]:
            entry = item["entry"]
            note_id = str(entry.get("id") or "").strip()
            if not note_id:
                continue
            path = self.workspace / f"{note_id}.md"
            content = ""
            if path.exists():
                content = self._note_body(path.read_text(encoding="utf-8"))
            selected.append(
                SupportingNote(
                    id=note_id,
                    title=str(entry.get("title") or note_id),
                    note_type=str(entry.get("type") or "task_state"),
                    tags=[str(tag) for tag in entry.get("tags") or []],
                    created_at=str(entry.get("created_at") or ""),
                    content=content.strip(),
                    path=str(path) if path.exists() else None,
                )
            )
        return selected

    def upsert_task_note(
        self,
        *,
        session_id: str,
        topic: str,
        task: ScholarlyReportTaskArtifact,
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        supporting_notes: list[SupportingNote],
    ) -> tuple[str, str]:
        """Create or update one persisted task note for a memo task."""

        self.workspace.mkdir(parents=True, exist_ok=True)
        notes_index = self._load_index()
        tags = [
            "deep_research",
            "scholarly_report",
            f"scholarly_session_{session_id}",
            f"scholarly_task_{task.id}",
        ]
        existing = self._find_index_entry(notes_index, tags)
        note_id = str(existing.get("id") or "").strip() if existing else ""
        if not note_id:
            note_id = make_id("note")
        note_path = self.workspace / f"{note_id}.md"
        created_at = str(existing.get("created_at") or "").strip() if existing else utc_now()
        updated_at = utc_now()
        note_title = f"任务 {task.id}: {task.title}"
        note_path.write_text(
            self._render_task_note(
                note_id=note_id,
                title=note_title,
                tags=tags,
                created_at=created_at,
                updated_at=updated_at,
                topic=topic,
                task=task,
                report_context=report_context,
                paper_cards=paper_cards,
                supporting_notes=supporting_notes,
            ),
            encoding="utf-8",
        )
        self._upsert_index_entry(
            notes_index,
            {
                "id": note_id,
                "title": note_title,
                "type": "task_state",
                "tags": tags,
                "created_at": created_at,
            },
        )
        self._save_index(notes_index)
        return note_id, str(note_path)

    @staticmethod
    def _topic_terms(topic: str) -> set[str]:
        terms = NotesWorkspaceRepository._tokenize(topic)
        if re.search(r"[\u4e00-\u9fff]", topic):
            compact = re.sub(r"\s+", "", topic)
            terms.update(
                compact[index : index + 2]
                for index in range(max(0, len(compact) - 1))
            )
        return {term for term in terms if term and term not in STOPWORDS}

    @staticmethod
    def _match_score(topic: str, topic_terms: set[str], title: str) -> int:
        lowered_topic = topic.lower().strip()
        lowered_title = title.lower().strip()
        title_terms = NotesWorkspaceRepository._tokenize(title)
        overlap = len(topic_terms & title_terms)
        if lowered_topic and lowered_title and (
            lowered_topic in lowered_title or lowered_title in lowered_topic
        ):
            overlap += 3
        return overlap

    @staticmethod
    def _sort_key(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.min

    @staticmethod
    def _note_body(text: str) -> str:
        normalized = text.replace("\r\n", "\n")
        if not normalized.startswith("---\n"):
            return normalized
        end = normalized.find("\n---\n", 4)
        if end < 0:
            return normalized
        return normalized[end + len("\n---\n") :].strip()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower())
            if token and token not in STOPWORDS
        }

    def _render_task_note(
        self,
        *,
        note_id: str,
        title: str,
        tags: list[str],
        created_at: str,
        updated_at: str,
        topic: str,
        task: ScholarlyReportTaskArtifact,
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        supporting_notes: list[SupportingNote],
    ) -> str:
        counts = report_context.get("evidence_bucket_counts") or {}
        evidence_lines = [
            f"- 已确认论文：{report_context.get('evidence_count', 0)} / {report_context.get('evidence_limit', 0)}",
            f"- 证据分层：直接相关 {counts.get('core', 0)} / 可迁移参考 {counts.get('adjacent_transfer', 0)} / 附录参考 {counts.get('off_target', 0)}",
            f"- 正文级证据：{report_context.get('fulltext_count', 0)} 篇（上传 PDF {report_context.get('uploaded_pdf_count', 0)} 篇）",
            f"- 合成模式：{report_context.get('synthesis_mode', 'fallback')}",
        ]
        if report_context.get("evidence_limited"):
            evidence_lines.append("- 说明：证据数量不足；已确认论文数量不足，结论更适合作为研究备忘录而非稳定共识。")
        note_lines = [
            "---",
            f"id: {note_id}",
            f"title: {title}",
            "type: task_state",
            f"tags: {json.dumps(tags, ensure_ascii=False)}",
            f"created_at: {created_at}",
            f"updated_at: {updated_at}",
            "---",
            "",
            f"# {title}",
            "",
            f"研究主题：{topic}",
            f"任务目标：{task.intent}",
            "",
            "## 证据概览",
            *evidence_lines,
            "",
            "## 任务小结",
            task.summary.strip(),
            "",
            "## 代表证据卡",
        ]
        for card in paper_cards[:5]:
            note_lines.append(
                f"- [{card.fit_tier}] {card.title} ({card.year or 'n.d.'}, {card.fulltext_source}) - "
                f"{card.key_claims[0] if card.key_claims else card.fit_reason}"
            )
        if supporting_notes:
            note_lines.extend(["", "## 历史辅助笔记"])
            for note in supporting_notes[:3]:
                note_lines.append(
                    f"- {note.title} ({note.note_type}, {note.created_at or 'unknown'})："
                    f"{self._excerpt(note.content, 140)}"
                )
        return "\n".join(note_lines).strip() + "\n"

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"notes": [], "metadata": {"created_at": utc_now(), "total_notes": 0}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"notes": [], "metadata": {"created_at": utc_now(), "total_notes": 0}}
        if not isinstance(data, dict):
            return {"notes": [], "metadata": {"created_at": utc_now(), "total_notes": 0}}
        data.setdefault("notes", [])
        data.setdefault("metadata", {})
        return data

    def _save_index(self, data: dict[str, Any]) -> None:
        notes = data.get("notes") or []
        metadata = data.get("metadata") or {}
        metadata["created_at"] = metadata.get("created_at") or utc_now()
        metadata["total_notes"] = len(notes)
        data["metadata"] = metadata
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _find_index_entry(index_data: dict[str, Any], tags: list[str]) -> dict[str, Any] | None:
        required = set(tags)
        for entry in index_data.get("notes") or []:
            if not isinstance(entry, dict):
                continue
            note_tags = {str(tag) for tag in entry.get("tags") or []}
            if required.issubset(note_tags):
                return entry
        return None

    @staticmethod
    def _upsert_index_entry(index_data: dict[str, Any], entry: dict[str, Any]) -> None:
        notes = list(index_data.get("notes") or [])
        for position, existing in enumerate(notes):
            if not isinstance(existing, dict):
                continue
            if existing.get("id") == entry["id"]:
                notes[position] = entry
                index_data["notes"] = notes
                return
        notes.append(entry)
        index_data["notes"] = notes

    @staticmethod
    def _excerpt(text: str, limit: int) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        if len(compact) <= limit:
            return compact or "无摘要。"
        return compact[: limit - 1].rstrip() + "…"


class ScholarlyReportPipeline:
    """Build a topic-aligned research memo from confirmed papers."""

    def __init__(
        self,
        config: Configuration,
        *,
        fulltext: ScholarlyFulltextService | None = None,
        llm: ScholarlyLLMService | None = None,
    ) -> None:
        self.config = config
        self.notes = NotesWorkspaceRepository(config.notes_workspace)
        self.fulltext = fulltext
        self.llm = llm or ScholarlyLLMService(config)

    def build(
        self,
        detail: dict[str, Any],
        papers: list[dict[str, Any]],
        *,
        persist_artifacts: bool,
    ) -> ScholarlyReportResult:
        """Generate the final report plus metadata artifacts."""

        base_context = self._build_base_report_context(detail, papers)
        if not papers:
            return ScholarlyReportResult(
                content=self._empty_report(detail["topic"], base_context),
                report_context={
                    **base_context,
                    "synthesis_mode": "fallback",
                    "evidence_bucket_counts": {
                        "core": 0,
                        "adjacent_transfer": 0,
                        "off_target": 0,
                    },
                },
                report_artifacts=self._empty_artifacts(),
                llm_usage=default_llm_usage(),
            )

        topic_profile = self._topic_profile(str(detail.get("topic") or ""))
        supporting_notes = self.notes.find_supporting_notes(str(detail.get("topic") or ""), limit=5)
        paper_cards, card_usage = self._build_paper_cards(papers, topic_profile)
        evidence_buckets = self._build_evidence_buckets(paper_cards)
        report_context = self._enrich_report_context(
            base_context,
            topic_profile,
            paper_cards,
            evidence_buckets,
        )
        memo_sections = self._build_memo_sections(
            detail=detail,
            report_context=report_context,
            paper_cards=paper_cards,
            evidence_buckets=evidence_buckets,
            supporting_notes=supporting_notes,
        )
        tasks = self._build_task_artifacts(memo_sections, supporting_notes)
        (
            report_text,
            review_sections,
            section_generation,
            synthesis_mode,
            synthesis_usage,
        ) = self._compose_report(
            detail=detail,
            report_context=report_context,
            paper_cards=paper_cards,
            memo_sections=memo_sections,
            evidence_buckets=evidence_buckets,
            supporting_notes=supporting_notes,
        )
        report_context["synthesis_mode"] = synthesis_mode

        if persist_artifacts:
            for task in tasks:
                note_id, note_path = self.notes.upsert_task_note(
                    session_id=str(detail["id"]),
                    topic=str(detail["topic"]),
                    task=task,
                    report_context=report_context,
                    paper_cards=paper_cards,
                    supporting_notes=supporting_notes,
                )
                task.note_id = note_id
                task.note_path = note_path

        artifacts = {
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "intent": task.intent,
                    "summary": task.summary,
                    "note_id": task.note_id,
                }
                for task in tasks
            ],
            "supporting_notes": [
                {
                    "id": note.id,
                    "title": note.title,
                    "type": note.note_type,
                    "created_at": note.created_at,
                }
                for note in supporting_notes
            ],
            "paper_cards": [self._serialize_card(card) for card in paper_cards],
            "memo_sections": memo_sections,
            "review_sections": review_sections,
            "section_generation": section_generation,
            "evidence_buckets": evidence_buckets,
        }
        return ScholarlyReportResult(
            content=report_text,
            report_context=report_context,
            report_artifacts=artifacts,
            llm_usage=merge_llm_usage(card_usage, synthesis_usage),
        )

    def _empty_artifacts(self) -> dict[str, Any]:
        return {
            "tasks": [],
            "supporting_notes": [],
            "paper_cards": [],
            "memo_sections": [],
            "review_sections": [],
            "section_generation": [],
            "evidence_buckets": {
                "core": [],
                "adjacent_transfer": [],
                "off_target": [],
            },
        }

    @staticmethod
    def _empty_report(topic: str, report_context: dict[str, Any]) -> str:
        return (
            f"# {topic}\n\n"
            "## Report Positioning / 报告定位\n"
            "- 说明：当前会话还没有已确认论文，因此暂时无法生成分层研究备忘录。\n"
            "- 说明：尚无已确认参考文献。\n"
            "- 行动：请先在工作台中确认纳入论文，再重新生成报告。\n\n"
            "## Evidence Statement / 证据说明\n"
            f"- 证据：已确认论文 {report_context.get('evidence_count', 0)} / {report_context.get('evidence_limit', 0)}。\n"
        )

    def _build_base_report_context(
        self,
        detail: dict[str, Any],
        papers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        years = sorted(paper.get("year") for paper in papers if paper.get("year"))
        year_range_text = f"{years[0]}-{years[-1]}" if years else "unknown"
        sources = Counter(str(paper.get("source") or "unknown") for paper in papers)
        main_sources = [
            {"source": source, "count": count}
            for source, count in sources.most_common(3)
        ]
        return {
            "session_id": detail["id"],
            "topic": detail["topic"],
            "evidence_count": len(papers),
            "evidence_limit": self.config.scholarly_selection_limit,
            "evidence_limited": len(papers) < self.config.scholarly_selection_limit,
            "year_range": {
                "start": years[0] if years else None,
                "end": years[-1] if years else None,
            },
            "year_range_text": year_range_text,
            "main_sources": main_sources,
            "main_sources_text": ", ".join(
                f"{item['source']}({item['count']})" for item in main_sources
            )
            or "unknown",
            "query_summary": self._query_summary(detail.get("queries") or []),
            "fulltext_count": 0,
            "abstract_only_count": 0,
            "uploaded_pdf_count": 0,
            "evidence_mix": {
                "fulltext": 0,
                "abstract_only": 0,
                "uploaded_pdf": 0,
            },
        }

    def _enrich_report_context(
        self,
        report_context: dict[str, Any],
        topic_profile: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        evidence_buckets: dict[str, list[str]],
    ) -> dict[str, Any]:
        enriched = dict(report_context)
        fulltext_count = sum(1 for card in paper_cards if card.evidence_level == "fulltext")
        uploaded_pdf_count = sum(
            1 for card in paper_cards if card.fulltext_source == "uploaded_pdf"
        )
        abstract_only_count = len(paper_cards) - fulltext_count
        enriched["fulltext_count"] = fulltext_count
        enriched["abstract_only_count"] = abstract_only_count
        enriched["uploaded_pdf_count"] = uploaded_pdf_count
        enriched["evidence_mix"] = {
            "fulltext": fulltext_count,
            "abstract_only": abstract_only_count,
            "uploaded_pdf": uploaded_pdf_count,
        }
        enriched["topic_boundary"] = self._topic_boundary_text(topic_profile)
        enriched["topic_axes"] = topic_profile["required_axes"]
        enriched["evidence_bucket_counts"] = {
            "core": len(evidence_buckets["core"]),
            "adjacent_transfer": len(evidence_buckets["adjacent_transfer"]),
            "off_target": len(evidence_buckets["off_target"]),
        }
        return enriched

    def _build_paper_cards(
        self,
        papers: list[dict[str, Any]],
        topic_profile: dict[str, Any],
    ) -> tuple[list[PaperEvidenceCard], dict[str, Any]]:
        cards: list[PaperEvidenceCard] = []
        usage = default_llm_usage()
        for paper in papers:
            resolved = self._resolve_paper_text(paper)
            excerpts = self._select_excerpts(resolved, paper)
            card, card_usage = self._extract_card(paper, resolved, excerpts, topic_profile)
            cards.append(card)
            usage = merge_llm_usage(usage, card_usage)
        return cards, usage

    def _resolve_paper_text(self, paper: dict[str, Any]) -> ResolvedPaperFulltext:
        if self.fulltext is None:
            abstract_text = str(paper.get("abstract") or paper.get("ai_reason") or "").strip()
            return ResolvedPaperFulltext(
                paper_id=str(paper.get("id") or ""),
                title=str(paper.get("title") or "Untitled"),
                evidence_level="abstract",
                fulltext_source="abstract_only",
                text=abstract_text,
                extraction_status="missing",
            )
        return self.fulltext.resolve_paper(paper)

    def _extract_card(
        self,
        paper: dict[str, Any],
        resolved: ResolvedPaperFulltext,
        excerpts: list[str],
        topic_profile: dict[str, Any],
    ) -> tuple[PaperEvidenceCard, dict[str, Any]]:
        if self.llm.available():
            try:
                payload, usage, _ = self.llm.complete_json(
                    stage="paper_card_extraction",
                    system_prompt=(
                        "You are extracting a structured evidence card from an AI/CS paper. "
                        "Use only the provided metadata and excerpts. Return JSON only with keys: "
                        "problem, setting, method, key_claims, evidence, datasets_metrics, "
                        "limitations, open_questions. Each array field must contain short strings."
                    ),
                    user_payload={
                        "title": paper.get("title"),
                        "year": paper.get("year"),
                        "venue": paper.get("venue"),
                        "evidence_level": resolved.evidence_level,
                        "fulltext_source": resolved.fulltext_source,
                        "abstract": paper.get("abstract") or "",
                        "ai_reason": paper.get("ai_reason") or "",
                        "excerpts": excerpts,
                    },
                    max_tokens=900,
                )
                if payload:
                    card = self._normalize_card(paper, resolved, excerpts, payload)
                    return self._annotate_card(card, topic_profile), usage
                card = self._heuristic_card(paper, resolved, excerpts)
                return self._annotate_card(card, topic_profile), usage
            except Exception as exc:  # pragma: no cover - external LLM dependent
                logger.info("Paper card extraction fell back to heuristic mode: %s", exc)
        card = self._heuristic_card(paper, resolved, excerpts)
        return self._annotate_card(card, topic_profile), default_llm_usage()

    def _normalize_card(
        self,
        paper: dict[str, Any],
        resolved: ResolvedPaperFulltext,
        excerpts: list[str],
        payload: dict[str, Any],
    ) -> PaperEvidenceCard:
        return PaperEvidenceCard(
            paper_id=str(paper.get("id") or ""),
            title=str(paper.get("title") or "Untitled"),
            year=paper.get("year"),
            source=paper.get("source"),
            evidence_level=resolved.evidence_level,
            fulltext_source=resolved.fulltext_source,
            problem=self._one_liner(payload.get("problem")) or self._fallback_problem(paper, excerpts),
            setting=self._one_liner(payload.get("setting")) or self._fallback_setting(paper, excerpts),
            method=self._one_liner(payload.get("method")) or self._fallback_method(paper, excerpts),
            key_claims=self._string_list(payload.get("key_claims")) or self._fallback_claims(paper, excerpts),
            evidence=self._string_list(payload.get("evidence")) or self._fallback_claims(paper, excerpts),
            datasets_metrics=self._string_list(payload.get("datasets_metrics")),
            limitations=self._string_list(payload.get("limitations"))
            or self._fallback_limitations(resolved, excerpts),
            open_questions=self._string_list(payload.get("open_questions"))
            or self._fallback_questions(resolved, excerpts),
            source_excerpt_refs=excerpts[:4],
            fit_tier="off_target",
            fit_reason="",
            task_family="other",
            modality_family="general vision",
            conditioning_family="weak or unspecified conditioning",
            prediction_family="other",
        )

    def _heuristic_card(
        self,
        paper: dict[str, Any],
        resolved: ResolvedPaperFulltext,
        excerpts: list[str],
    ) -> PaperEvidenceCard:
        return PaperEvidenceCard(
            paper_id=str(paper.get("id") or ""),
            title=str(paper.get("title") or "Untitled"),
            year=paper.get("year"),
            source=paper.get("source"),
            evidence_level=resolved.evidence_level,
            fulltext_source=resolved.fulltext_source,
            problem=self._fallback_problem(paper, excerpts),
            setting=self._fallback_setting(paper, excerpts),
            method=self._fallback_method(paper, excerpts),
            key_claims=self._fallback_claims(paper, excerpts),
            evidence=self._fallback_claims(paper, excerpts),
            datasets_metrics=self._extract_keyword_sentences(excerpts, set(BENCHMARK_TOKENS), 3),
            limitations=self._fallback_limitations(resolved, excerpts),
            open_questions=self._fallback_questions(resolved, excerpts),
            source_excerpt_refs=excerpts[:4],
            fit_tier="off_target",
            fit_reason="",
            task_family="other",
            modality_family="general vision",
            conditioning_family="weak or unspecified conditioning",
            prediction_family="other",
        )

    def _annotate_card(
        self,
        card: PaperEvidenceCard,
        topic_profile: dict[str, Any],
    ) -> PaperEvidenceCard:
        signals = self._paper_signal_flags(card)
        card.task_family = self._task_family(signals)
        card.modality_family = self._modality_family(signals)
        card.conditioning_family = self._conditioning_family(signals)
        card.prediction_family = self._prediction_family(signals)
        fit_tier, fit_reason = self._fit_tier_and_reason(topic_profile, signals)
        card.fit_tier = fit_tier
        card.fit_reason = fit_reason
        return card

    def _build_evidence_buckets(self, paper_cards: list[PaperEvidenceCard]) -> dict[str, list[str]]:
        buckets = {
            "core": [],
            "adjacent_transfer": [],
            "off_target": [],
        }
        for card in paper_cards:
            if card.fit_tier not in buckets:
                buckets["off_target"].append(card.paper_id)
                continue
            buckets[card.fit_tier].append(card.paper_id)
        return buckets

    def _build_memo_sections(
        self,
        *,
        detail: dict[str, Any],
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        evidence_buckets: dict[str, list[str]],
        supporting_notes: list[SupportingNote],
    ) -> list[dict[str, Any]]:
        card_by_id = {card.paper_id: card for card in paper_cards}
        core_cards = [card_by_id[paper_id] for paper_id in evidence_buckets["core"] if paper_id in card_by_id]
        adjacent_cards = [
            card_by_id[paper_id]
            for paper_id in evidence_buckets["adjacent_transfer"]
            if paper_id in card_by_id
        ]
        off_target_cards = [
            card_by_id[paper_id]
            for paper_id in evidence_buckets["off_target"]
            if paper_id in card_by_id
        ]
        strong_cards = [card for card in core_cards if card.evidence_level == "fulltext"]
        if not strong_cards:
            strong_cards = [card for card in adjacent_cards if card.evidence_level == "fulltext"]
        if not strong_cards:
            strong_cards = core_cards[:2] or adjacent_cards[:2]

        sections: list[dict[str, Any]] = []
        counts = report_context["evidence_bucket_counts"]

        sections.append(
            self._memo_section(
                section_id="report-positioning",
                summary="先明确当前研究问题的边界，再区分直接证据、可迁移参考和附录材料。",
                items=[
                    self._memo_item(
                        "judgment",
                        report_context["topic_boundary"],
                    ),
                    self._memo_item(
                        "evidence",
                        f"当前确认论文共 {report_context['evidence_count']} 篇，其中可直接支撑主问题的 {counts['core']} 篇，"
                        f"可作为迁移参考的 {counts['adjacent_transfer']} 篇，附录保留 {counts['off_target']} 篇。",
                    ),
                    self._memo_item(
                        "note",
                        "medical、remote sensing、VL grounding、layout / text-to-image guidance 等邻近路线只作为迁移线索，"
                        "不直接并入主结论。",
                    ),
                    self._memo_item(
                        "note",
                        f"正文级证据 {report_context['fulltext_count']} 篇，上传 PDF {report_context['uploaded_pdf_count']} 篇。",
                    ),
                ],
                evidence_cards=self._memo_evidence_cards(core_cards[:2] or adjacent_cards[:2]),
            )
        )

        sections.append(
            self._memo_section(
                section_id="evidence-statement",
                summary="报告只基于当前已确认论文写结论，不把未核实线索直接并入正文。",
                items=[
                    self._memo_item(
                        "evidence",
                        f"年份覆盖 {report_context['year_range_text']}，主要来源为 {report_context['main_sources_text']}。",
                    ),
                    self._memo_item(
                        "evidence",
                        f"摘要级证据 {report_context['abstract_only_count']} 篇；这些论文可提示方向，但不能单独支撑强结论。",
                    ),
                    *(
                        [
                            self._memo_item(
                                "note",
                                "证据数量不足：当前确认论文数量仍然偏少，因此这份报告更适合作为研究备忘录而非稳定共识。",
                            )
                        ]
                        if report_context["evidence_limited"]
                        else []
                    ),
                    self._memo_item(
                        "note",
                        f"当前检索关注为 {report_context['query_summary']}。",
                    ),
                    self._memo_item(
                        "note",
                        "代表论文会优先展示与当前问题更相关、且证据更完整的工作，而不是简单按标题相似度拼接。",
                    ),
                ],
                evidence_cards=self._memo_evidence_cards(
                    strong_cards[:2] or core_cards[:2] or paper_cards[:2]
                ),
            )
        )

        landscape_items = [
            self._memo_item(
                "judgment",
                self._landscape_statement(core_cards, adjacent_cards),
            ),
            self._memo_item(
                "evidence",
                    self._route_snapshot("主线证据", core_cards),
            ),
            self._memo_item(
                "evidence",
                    self._route_snapshot("迁移参考", adjacent_cards),
            ),
        ]
        if off_target_cards:
            landscape_items.append(
                self._memo_item(
                    "note",
                    self._route_snapshot("附录参考", off_target_cards),
                )
            )
        sections.append(
            self._memo_section(
                section_id="research-landscape",
                summary="主结论优先依据直接相关证据，迁移参考主要用于补充比较和解释设计空间。",
                items=landscape_items,
                evidence_cards=self._memo_evidence_cards(core_cards[:3] or adjacent_cards[:3]),
            )
        )

        dispute_items = [
            self._memo_item(
                "judgment",
                self._evidence_strength_statement(report_context, core_cards, adjacent_cards),
            ),
            self._memo_item(
                "evidence",
                self._dispute_statement(core_cards, adjacent_cards),
            ),
        ]
        if report_context["abstract_only_count"]:
            dispute_items.append(
                self._memo_item(
                    "note",
                    f"仍有 {report_context['abstract_only_count']} 篇论文只有摘要级证据，方法细节和 failure modes 尚未全文核验。",
                )
            )
        if supporting_notes:
            dispute_items.append(
                self._memo_item(
                    "note",
                    "历史研究笔记已作为补充背景纳入，但不会替代论文证据。",
                )
            )
        sections.append(
            self._memo_section(
                section_id="evidence-strength",
                summary="这里强调哪些判断来自正文级实证，哪些仍停留在可迁移线索。",
                items=dispute_items,
                evidence_cards=self._memo_evidence_cards(strong_cards[:3] or core_cards[:3]),
            )
        )

        gaps = self._research_gaps(report_context, core_cards, adjacent_cards)
        sections.append(
            self._memo_section(
                section_id="research-gaps",
                summary="空白主要来自直接证据不足、评测口径分裂，以及邻近路线仍需进一步核验。",
                items=[self._memo_item("judgment", gap) for gap in gaps[:4]],
                evidence_cards=self._memo_evidence_cards(
                    self._cards_with_limits(core_cards, adjacent_cards)[:3]
                ),
            )
        )

        directions = self._promising_directions(report_context, core_cards, adjacent_cards)
        sections.append(
            self._memo_section(
                section_id="promising-directions",
                summary="这些方向来自当前证据中的重复信号，而不是零散的关键词联想。",
                items=[
                    {
                        "kind": "ordered",
                        "order": str(index),
                        "text": direction,
                    }
                    for index, direction in enumerate(directions[:5], start=1)
                ],
                evidence_cards=self._memo_evidence_cards(
                    (core_cards[:2] + adjacent_cards[:2])[:4]
                ),
            )
        )

        sections.append(
            self._memo_section(
                section_id="confirmed-references",
                summary="附录区保留全部已确认论文及其定位，避免参考文献抢占主体判断。",
                items=[
                    {
                        "kind": "ordered",
                        "order": str(index),
                        "text": (
                            f"[{card.fit_tier}] {card.title} ({card.year or 'n.d.'}, "
                            f"{card.source or 'unknown'}, {card.fulltext_source})"
                        ),
                    }
                    for index, card in enumerate(paper_cards, start=1)
                ],
                evidence_cards=[],
                appendix=True,
            )
        )
        return sections

    def _build_task_artifacts(
        self,
        memo_sections: list[dict[str, Any]],
        supporting_notes: list[SupportingNote],
    ) -> list[ScholarlyReportTaskArtifact]:
        section_map = {section["id"]: section for section in memo_sections}
        tasks: list[ScholarlyReportTaskArtifact] = []
        for spec in TASK_SECTION_GROUPS:
            summary_lines: list[str] = []
            for section_id in spec["sections"]:
                section = section_map.get(section_id)
                if not section:
                    continue
                summary_lines.append(f"### {section['title']}")
                for item in section.get("items") or []:
                    if item.get("kind") == "ordered":
                        summary_lines.append(f"{item.get('order', '1')}. {item.get('text', '')}")
                    else:
                        summary_lines.append(f"- {item.get('text', '')}")
                    if len(summary_lines) >= 7:
                        break
                if len(summary_lines) >= 7:
                    break
            if supporting_notes:
                summary_lines.append("### Supporting Historical Notes / 辅助历史笔记")
                for note in supporting_notes[:2]:
                    summary_lines.append(
                        f"- {note.title}：{self._excerpt(note.content, 120)}"
                    )
            tasks.append(
                ScholarlyReportTaskArtifact(
                    id=int(spec["id"]),
                    title=str(spec["title"]),
                    intent=str(spec["intent"]),
                    summary="\n".join(summary_lines).strip(),
                )
            )
        return tasks

    def _compose_report(
        self,
        *,
        detail: dict[str, Any],
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        memo_sections: list[dict[str, Any]],
        evidence_buckets: dict[str, list[str]],
        supporting_notes: list[SupportingNote],
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str, dict[str, Any]]:
        review_sections, section_generation, usage = self._build_review_sections(
            detail=detail,
            report_context=report_context,
            paper_cards=paper_cards,
            memo_sections=memo_sections,
            evidence_buckets=evidence_buckets,
            supporting_notes=supporting_notes,
        )
        synthesis_mode = (
            "llm"
            if any(
                record.get("mode") == "llm" and not record.get("appendix")
                for record in section_generation
            )
            else "fallback"
        )
        body_text = self._review_sections_to_markdown(review_sections)
        return (
            f"# {detail['topic']}\n\n{body_text.strip()}\n",
            review_sections,
            section_generation,
            synthesis_mode,
            usage,
        )

    def _build_review_sections(
        self,
        *,
        detail: dict[str, Any],
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        memo_sections: list[dict[str, Any]],
        evidence_buckets: dict[str, list[str]],
        supporting_notes: list[SupportingNote],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        usage = default_llm_usage()
        section_generation: list[dict[str, Any]] = []
        review_sections: list[dict[str, Any]] = []

        card_by_id = {card.paper_id: card for card in paper_cards}
        core_cards = [
            card_by_id[paper_id]
            for paper_id in evidence_buckets["core"]
            if paper_id in card_by_id
        ]
        adjacent_cards = [
            card_by_id[paper_id]
            for paper_id in evidence_buckets["adjacent_transfer"]
            if paper_id in card_by_id
        ]
        off_target_cards = [
            card_by_id[paper_id]
            for paper_id in evidence_buckets["off_target"]
            if paper_id in card_by_id
        ]
        strong_cards = [card for card in core_cards if card.evidence_level == "fulltext"]
        if not strong_cards:
            strong_cards = [card for card in adjacent_cards if card.evidence_level == "fulltext"]

        for section in memo_sections:
            section_id = str(section.get("id") or "")
            section_cards = self._review_section_cards(
                section_id=section_id,
                section=section,
                paper_cards=paper_cards,
                core_cards=core_cards,
                adjacent_cards=adjacent_cards,
                off_target_cards=off_target_cards,
                strong_cards=strong_cards,
            )
            review_section = self._fallback_review_section(
                detail=detail,
                section=section,
                report_context=report_context,
                paper_cards=paper_cards,
                core_cards=core_cards,
                adjacent_cards=adjacent_cards,
                off_target_cards=off_target_cards,
                strong_cards=strong_cards,
                supporting_notes=supporting_notes,
                section_cards=section_cards,
            )
            mode = "fallback"

            if self.llm.available() and not review_section["appendix"]:
                try:
                    payload, section_usage, _ = self.llm.complete_json(
                        stage="report_synthesis",
                        system_prompt=(
                            "You are writing one section of a Chinese AI/CS literature review. "
                            "Return JSON only with keys summary, narrative_paragraphs, insight_items. "
                            "narrative_paragraphs must be a list of 2 to 4 substantial Chinese paragraphs. "
                            "insight_items must be a short list of grounded bullets. "
                            "Use only the provided section evidence pack. "
                            "Keep adjacent-transfer evidence as transfer evidence and never promote it into the core conclusion."
                        ),
                        user_payload={
                            "topic": detail["topic"],
                            "section": {
                                "id": review_section["id"],
                                "title": review_section["title"],
                                "summary": review_section["summary"],
                                "target_style": "mixed review",
                            },
                            "report_context": {
                                "topic_boundary": report_context["topic_boundary"],
                                "evidence_count": report_context["evidence_count"],
                                "fulltext_count": report_context["fulltext_count"],
                                "abstract_only_count": report_context["abstract_only_count"],
                                "uploaded_pdf_count": report_context["uploaded_pdf_count"],
                                "evidence_bucket_counts": report_context["evidence_bucket_counts"],
                                "year_range": report_context["year_range_text"],
                                "main_sources": report_context["main_sources_text"],
                            },
                            "memo_items": [
                                {
                                    "kind": str(item.get("kind") or "bullet"),
                                    "tone": str(item.get("tone") or ""),
                                    "text": str(item.get("text") or ""),
                                    "order": str(item.get("order") or ""),
                                }
                                for item in section.get("items") or []
                                if str(item.get("text") or "").strip()
                            ][:6],
                            "section_evidence_pack": [
                                self._section_card_payload(card) for card in section_cards[:6]
                            ],
                        },
                        max_tokens=2400,
                        timeout_seconds=25.0,
                        disable_on_error=False,
                    )
                    usage = merge_llm_usage(usage, section_usage)
                    normalized = self._normalize_review_section_payload(
                        review_section,
                        payload,
                    )
                    if normalized is not None:
                        review_section = normalized
                        mode = "llm"
                except Exception as exc:  # pragma: no cover - external LLM dependent
                    logger.info(
                        "Review section synthesis fell back to deterministic mode for %s: %s",
                        section_id,
                        exc,
                    )

            review_sections.append(review_section)
            section_generation.append(
                {
                    "section_id": review_section["id"],
                    "title": review_section["title"],
                    "mode": mode,
                    "appendix": bool(review_section["appendix"]),
                }
            )

        return review_sections, section_generation, usage

    def _review_section_cards(
        self,
        *,
        section_id: str,
        section: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
        off_target_cards: list[PaperEvidenceCard],
        strong_cards: list[PaperEvidenceCard],
    ) -> list[PaperEvidenceCard]:
        card_by_id = {card.paper_id: card for card in paper_cards}
        explicit_cards = [
            card_by_id[str(card.get("paper_id"))]
            for card in section.get("evidence_cards") or []
            if str(card.get("paper_id") or "") in card_by_id
        ]
        if section_id == "report-positioning":
            fallback_cards = core_cards + adjacent_cards
        elif section_id == "evidence-statement":
            fallback_cards = strong_cards + core_cards + adjacent_cards
        elif section_id == "research-landscape":
            fallback_cards = core_cards + adjacent_cards + off_target_cards
        elif section_id == "evidence-strength":
            fallback_cards = strong_cards + self._cards_with_limits(core_cards, adjacent_cards)
        elif section_id == "research-gaps":
            fallback_cards = self._cards_with_limits(core_cards, adjacent_cards) + core_cards
        elif section_id == "promising-directions":
            fallback_cards = core_cards + adjacent_cards
        else:
            fallback_cards = paper_cards
        unique: list[PaperEvidenceCard] = []
        seen: set[str] = set()
        for card in explicit_cards + fallback_cards:
            if not card.paper_id or card.paper_id in seen:
                continue
            seen.add(card.paper_id)
            unique.append(card)
            if len(unique) >= 6:
                break
        return unique

    def _fallback_review_section(
        self,
        *,
        detail: dict[str, Any],
        section: dict[str, Any],
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
        off_target_cards: list[PaperEvidenceCard],
        strong_cards: list[PaperEvidenceCard],
        supporting_notes: list[SupportingNote],
        section_cards: list[PaperEvidenceCard],
    ) -> dict[str, Any]:
        appendix = bool(section.get("appendix"))
        insight_items = [
            self._normalize_report_item(item)
            for item in (
                list(section.get("items") or [])
                if appendix
                else list(section.get("items") or [])[:5]
            )
            if str(item.get("text") or "").strip()
        ]
        return {
            "id": str(section.get("id") or ""),
            "title": str(section.get("title") or ""),
            "icon": str(section.get("icon") or "book"),
            "summary": str(section.get("summary") or "").strip(),
            "narrative_paragraphs": self._fallback_review_narrative(
                detail=detail,
                section_id=str(section.get("id") or ""),
                report_context=report_context,
                paper_cards=paper_cards,
                core_cards=core_cards,
                adjacent_cards=adjacent_cards,
                off_target_cards=off_target_cards,
                strong_cards=strong_cards,
                supporting_notes=supporting_notes,
                section_cards=section_cards,
            ),
            "insight_items": insight_items,
            "evidence_cards": list(section.get("evidence_cards") or []),
            "appendix": appendix,
        }

    def _fallback_review_narrative(
        self,
        *,
        detail: dict[str, Any],
        section_id: str,
        report_context: dict[str, Any],
        paper_cards: list[PaperEvidenceCard],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
        off_target_cards: list[PaperEvidenceCard],
        strong_cards: list[PaperEvidenceCard],
        supporting_notes: list[SupportingNote],
        section_cards: list[PaperEvidenceCard],
    ) -> list[str]:
        counts = report_context.get("evidence_bucket_counts") or {}
        if section_id == "report-positioning":
            return [
                (
                    f"本报告把当前主题限定为 {report_context['topic_boundary']}。"
                    f"在这条边界内，当前已确认论文共 {report_context['evidence_count']} 篇，"
                    f"其中可直接支撑主问题的 {counts.get('core', 0)} 篇、可作为迁移参考的 {counts.get('adjacent_transfer', 0)} 篇、"
                    f"附录保留 {counts.get('off_target', 0)} 篇。"
                    "因此正文结论优先依据直接相关证据，其余论文主要用于补充背景和比较设计差异。"
                ),
                (
                    f"从证据形态看，当前有 {report_context['fulltext_count']} 篇正文级证据，"
                    f"其中 {report_context['uploaded_pdf_count']} 篇来自上传 PDF；另外仍有 "
                    f"{report_context['abstract_only_count']} 篇停留在摘要级。"
                    "medical、remote sensing、VL grounding、layout 或 text-to-image guidance 这类邻近路线"
                    "会被保留为迁移线索，而不会直接并入核心结论。"
                ),
            ]
        if section_id == "evidence-statement":
            limited_text = (
                "由于当前已确认论文数量仍然偏少，这份报告更适合作为阶段性研究判断，而不是稳定共识。"
                if report_context["evidence_limited"]
                else "当前证据量已经足以支撑一版较完整的阶段性综述，但强结论仍应优先参考正文级论文。"
            )
            return [
                (
                    f"当前证据池覆盖 {report_context['year_range_text']}，主要来源为 "
                    f"{report_context['main_sources_text']}。"
                    f"已确认论文 {report_context['evidence_count']} 篇中，"
                    f"正文级证据 {report_context['fulltext_count']} 篇，摘要级证据 "
                    f"{report_context['abstract_only_count']} 篇。"
                ),
                (
                    limited_text
                    + f" 当前检索关注集中在 {report_context['query_summary']}。"
                    "因此阅读这份报告时，应把正文级直接证据理解为主要支撑，把摘要级或邻近论文理解为方向提示和边界补充。"
                ),
            ]
        if section_id == "research-landscape":
            paragraphs = [
                (
                    "从核心证据看，"
                    + self._landscape_statement(core_cards, adjacent_cards)
                    + " "
                    + self._route_snapshot("主线证据", core_cards)
                ),
                (
                    "从邻近迁移证据看，"
                    + self._route_snapshot("迁移参考", adjacent_cards)
                    + " 这些工作更适合帮助理解 conditioning、localization granularity、benchmark 口径和跨域可迁移性，"
                    + "而不是直接替代目标问题中的核心设定。"
                ),
            ]
            if off_target_cards:
                paragraphs.append(
                    "另有少量已确认论文明显偏离当前主题边界，例如 "
                    + "；".join(card.title for card in off_target_cards[:2])
                    + "。这些论文被保留在附录，只用于记录检索边界和排除路径。"
                )
            return paragraphs
        if section_id == "evidence-strength":
            paragraphs = [
                (
                    self._evidence_strength_statement(report_context, core_cards, adjacent_cards)
                    + " "
                    + self._dispute_statement(core_cards, adjacent_cards)
                )
            ]
            follow_up: list[str] = []
            if report_context["abstract_only_count"]:
                follow_up.append(
                    f"仍有 {report_context['abstract_only_count']} 篇论文只有摘要级证据，"
                    "因此方法细节、failure modes 和评测边界仍需继续核验"
                )
            if supporting_notes:
                follow_up.append("历史研究笔记可用于补充背景，但不会替代论文正文证据")
            if strong_cards:
                follow_up.append(
                    "当前最可信的判断优先来自正文级直接相关论文，其次才是正文级迁移参考证据"
                )
            if follow_up:
                paragraphs.append("；".join(follow_up) + "。")
            return paragraphs
        if section_id == "research-gaps":
            gaps = self._research_gaps(report_context, core_cards, adjacent_cards)
            if not gaps:
                return [
                    "当前已确认论文还不足以支撑清晰的研究空白盘点，后续应优先补齐正文级直接证据并统一 benchmark 口径。"
                ]
            paragraphs = [
                "结合当前直接证据与迁移参考，最明显的研究空白主要集中在 "
                + "；".join(gaps[:2])
                + "。"
            ]
            if len(gaps) > 2:
                paragraphs.append("进一步看，" + "；".join(gaps[2:4]) + "。")
            return paragraphs
        if section_id == "promising-directions":
            directions = self._promising_directions(report_context, core_cards, adjacent_cards)
            if not directions:
                return [
                    "当前证据仍偏薄，下一步最务实的方向是先补全文、补 benchmark 和补关键设定下的对照实验。"
                ]
            paragraphs = [
                "就当前证据来看，下一步最值得继续推进的方向包括 "
                + "；".join(directions[:2])
                + "。"
            ]
            if len(directions) > 2:
                paragraphs.append("更具体地说，" + "；".join(directions[2:5]) + "。")
            return paragraphs
        representative = "；".join(
            f"{card.title} ({card.year or 'n.d.'})" for card in section_cards[:3]
        )
        return [
            (
                f"附录列出本轮已确认的 {len(paper_cards)} 篇论文，方便后续导出、复核和继续精读。"
                + (
                    f"代表性论文包括 {representative}。"
                    if representative
                    else f"主题为 {detail['topic']}。"
                )
            )
        ]

    def _normalize_review_section_payload(
        self,
        fallback_section: dict[str, Any],
        payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        paragraphs = [
            self._paragraph_text(paragraph)
            for paragraph in payload.get("narrative_paragraphs") or []
            if self._paragraph_text(paragraph)
        ]
        if not paragraphs:
            return None
        return {
            **fallback_section,
            "summary": self._one_liner(payload.get("summary")) or fallback_section["summary"],
            "narrative_paragraphs": paragraphs[:4],
            "insight_items": self._normalize_review_insights(
                payload.get("insight_items"),
                fallback_section["insight_items"],
            ),
        }

    def _normalize_review_insights(
        self,
        value: Any,
        fallback_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return fallback_items
        normalized: list[dict[str, Any]] = []
        for raw_item in value[:6]:
            if isinstance(raw_item, dict):
                item = self._normalize_report_item(raw_item)
                if item["text"]:
                    normalized.append(item)
                continue
            text = self._one_liner(raw_item)
            if text:
                normalized.append(self._memo_item("judgment", text))
        return normalized or fallback_items

    def _review_sections_to_markdown(self, review_sections: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for section in review_sections:
            lines.append(f"## {section['title']}")
            summary = str(section.get("summary") or "").strip()
            if summary:
                lines.append(summary)
                lines.append("")
            for paragraph in section.get("narrative_paragraphs") or []:
                text = str(paragraph or "").strip()
                if not text:
                    continue
                lines.append(text)
                lines.append("")
            for item in section.get("insight_items") or []:
                kind = str(item.get("kind") or "bullet")
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if kind == "ordered":
                    lines.append(f"{item.get('order', '1')}. {text}")
                    continue
                if kind == "paragraph":
                    lines.append(text)
                    lines.append("")
                    continue
                tone = str(item.get("tone") or "").strip()
                label = REPORT_TONE_LABELS.get(tone)
                lines.append(f"- {label}：{text}" if label else f"- {text}")
            evidence_cards = list(section.get("evidence_cards") or [])
            if evidence_cards and not section.get("appendix"):
                lines.append("")
                lines.append("### Representative Evidence / 代表证据")
                for card in evidence_cards[:4]:
                    title = str(card.get("title") or "Untitled")
                    fit_tier = str(card.get("fit_tier") or "off_target")
                    evidence_level = str(card.get("evidence_level") or "abstract")
                    claim = self._one_liner((card.get("key_claims") or [""])[0])
                    limitation = self._one_liner((card.get("limitations") or [""])[0])
                    summary_line = f"- [{fit_tier}] {title} ({evidence_level})"
                    if claim:
                        summary_line += f": {claim}"
                    if limitation:
                        summary_line += f" 限制：{limitation}"
                    lines.append(summary_line)
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _paragraph_text(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        return text[:520].strip()

    def _normalize_report_item(self, item: dict[str, Any]) -> dict[str, Any]:
        tone = str(item.get("tone") or "").strip()
        normalized_tone = (
            tone
            if tone in {"evidence", "judgment", "speculation", "action", "note"}
            else ""
        )
        kind = str(item.get("kind") or "bullet").strip()
        normalized_kind = (
            kind if kind in {"paragraph", "bullet", "ordered"} else "bullet"
        )
        return {
            "kind": normalized_kind,
            "tone": normalized_tone,
            "text": self._one_liner(item.get("text")),
            "order": str(item.get("order") or "").strip(),
        }

    def _memo_sections_to_markdown(self, memo_sections: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for section in memo_sections:
            lines.append(f"## {section['title']}")
            summary = str(section.get("summary") or "").strip()
            if summary:
                lines.append(summary)
            for item in section.get("items") or []:
                kind = str(item.get("kind") or "bullet")
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                if kind == "ordered":
                    order = str(item.get("order") or "1")
                    lines.append(f"{order}. {text}")
                    continue
                if kind == "paragraph":
                    lines.append(text)
                    continue
                tone = str(item.get("tone") or "").strip()
                label = REPORT_TONE_LABELS.get(tone)
                if label:
                    lines.append(f"- {label}：{text}")
                else:
                    lines.append(f"- {text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _memo_section(
        self,
        *,
        section_id: str,
        summary: str,
        items: list[dict[str, Any]],
        evidence_cards: list[dict[str, Any]],
        appendix: bool = False,
    ) -> dict[str, Any]:
        spec = next(item for item in SECTION_SPECS if item["id"] == section_id)
        return {
            "id": section_id,
            "title": spec["title"],
            "icon": spec["icon"],
            "summary": summary,
            "items": items,
            "evidence_cards": evidence_cards,
            "appendix": appendix,
        }

    @staticmethod
    def _memo_item(tone: str, text: str) -> dict[str, Any]:
        return {
            "kind": "bullet",
            "tone": tone,
            "text": text,
        }

    def _memo_evidence_cards(self, cards: list[PaperEvidenceCard]) -> list[dict[str, Any]]:
        unique: list[PaperEvidenceCard] = []
        seen: set[str] = set()
        for card in cards:
            if not card.paper_id or card.paper_id in seen:
                continue
            seen.add(card.paper_id)
            unique.append(card)
        return [
            {
                "paper_id": card.paper_id,
                "title": card.title,
                "fit_tier": card.fit_tier,
                "evidence_level": card.evidence_level,
                "task_family": card.task_family,
                "modality_family": card.modality_family,
                "conditioning_family": card.conditioning_family,
                "prediction_family": card.prediction_family,
                "key_claims": card.key_claims[:2],
                "limitations": card.limitations[:2],
            }
            for card in unique[:4]
        ]

    def _landscape_statement(
        self,
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> str:
        if core_cards:
            families = self._most_common_labels(core_cards, attr="task_family", limit=3)
            return (
                "直接相关证据已经形成可辨识主线，主要围绕 "
                f"{', '.join(families) if families else '目标问题本身'} 展开。"
            )
        if adjacent_cards:
            families = self._most_common_labels(adjacent_cards, attr="task_family", limit=3)
            return (
                "当前更像邻近路线拼图，直接命中目标设定的论文较少，"
                f"主要线索来自 {', '.join(families) if families else '邻近任务'}。"
            )
        return "已确认论文仍偏分散，需要继续补核心设定论文。"

    def _route_snapshot(self, label: str, cards: list[PaperEvidenceCard]) -> str:
        if not cards:
            return f"{label}：暂无代表论文。"
        snippets = [
            f"{card.title} -> {card.task_family}"
            for card in cards[:3]
        ]
        return f"{label}：{'; '.join(snippets)}。"

    def _evidence_strength_statement(
        self,
        report_context: dict[str, Any],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> str:
        core_fulltext = sum(1 for card in core_cards if card.evidence_level == "fulltext")
        adjacent_fulltext = sum(1 for card in adjacent_cards if card.evidence_level == "fulltext")
        if core_fulltext:
            return (
                f"当前最强证据来自 {core_fulltext} 篇正文级直接相关论文；"
                "只有同时报告文本条件、mask 预测和 diffusion 组件的论文才被视为主结论支撑。"
            )
        if adjacent_fulltext:
            return (
                "正文级证据主要落在迁移参考路线，"
                "因此现阶段更适合提炼可迁移设计，而不是下稳定主结论。"
            )
        return (
            f"当前 {report_context['evidence_count']} 篇论文中尚缺正文级直接相关证据，"
            "大部分判断仍需全文核验。"
        )

    def _dispute_statement(
        self,
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> str:
        limitation_corpus = " ".join(
            " ".join(card.limitations + card.open_questions) for card in core_cards + adjacent_cards
        ).lower()
        focus = []
        if self._contains_any(limitation_corpus, ("benchmark", "metric", "evaluation", "generalization")):
            focus.append("评测口径与泛化")
        if self._contains_any(limitation_corpus, ("prompt", "language", "referring")):
            focus.append("prompt / referring 设计")
        if self._contains_any(limitation_corpus, ("diffusion", "latent", "denoise")):
            focus.append("diffusion 组件是否真正带来 dense prediction 增益")
        if self._contains_any(limitation_corpus, ("boundary", "mask", "pixel")):
            focus.append("mask 质量与边界细节")
        if not focus:
            focus = ["跨 setting 是否仍成立", "相同 benchmark 下是否可比"]
        return "当前真实分歧主要集中在 " + "、".join(focus[:3]) + "。"

    def _research_gaps(
        self,
        report_context: dict[str, Any],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> list[str]:
        gaps: list[str] = []
        if not core_cards:
            gaps.append("直接命中目标设定的 core 论文偏少，当前证据池仍由邻近迁移路线主导。")
        elif sum(1 for card in core_cards if card.evidence_level == "fulltext") < max(1, len(core_cards) // 2):
            gaps.append("不少关键论文仍停留在摘要级，方法细节、failure modes 和评测边界尚未全文核验。")
        if report_context["abstract_only_count"]:
            gaps.append("摘要级证据占比仍高，导致部分结论只能停留在方向判断，而不能当成强证据。")
        if len(adjacent_cards) >= len(core_cards):
            gaps.append("medical / remote sensing / VL grounding 等邻近证据较多，但缺少同域验证来判断这些设计能否直接迁移。")
        corpus = " ".join(
            " ".join(card.datasets_metrics + card.limitations + card.open_questions)
            for card in core_cards + adjacent_cards
        ).lower()
        if not self._contains_any(corpus, BENCHMARK_TOKENS):
            gaps.append("benchmark、metric 和统一评测协议的信息不足，难以比较 prompt、mask fidelity 与泛化差异。")
        elif self._contains_any(corpus, ("benchmark", "dataset", "evaluation")):
            gaps.append("已有 benchmark 线索，但跨论文评测口径仍不统一，容易把邻近任务结果误读成主问题结论。")
        if not gaps:
            gaps.append("当前最大空白在于把关键论文之间的设置差异压平到同一评测框架下，再确认结论是否稳定。")
        return gaps

    def _promising_directions(
        self,
        report_context: dict[str, Any],
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> list[str]:
        directions: list[str] = []
        if not core_cards:
            directions.append("优先补足同时覆盖 text / prompt、segmentation / mask 和 diffusion / latent 的关键论文。")
        if sum(1 for card in core_cards if card.evidence_level == "fulltext") < max(1, len(core_cards) // 2):
            directions.append("优先上传或精读关键论文全文，把摘要级判断升级为正文级证据。")
        directions.append("围绕 prompt 形式、mask fidelity 与 generalization 建立统一 benchmark，而不是继续混用不可比 setting。")
        if any(card.modality_family == "medical imaging" for card in adjacent_cards) or any(
            card.modality_family == "remote sensing" for card in adjacent_cards
        ):
            directions.append("把 medical / remote sensing prompt segmentation 当作 transfer baseline，显式验证其在目标域是否仍成立。")
        if any(card.task_family == "vision-language grounding" for card in adjacent_cards):
            directions.append("比较 VL grounding 与 text-guided segmentation 在 condition encoding 和 localization granularity 上的可迁移部分。")
        if any("diffusion" in card.conditioning_family.lower() for card in core_cards + adjacent_cards):
            directions.append("拆分 diffusion 组件带来的真实收益：是改善 mask prediction，还是只提供更强先验。")
        directions.append("把明显偏离主问题的论文留在附录，避免无关生成类或泛视觉论文稀释主问题结论。")
        unique: list[str] = []
        for item in directions:
            if item not in unique:
                unique.append(item)
        return unique

    def _cards_with_limits(
        self,
        core_cards: list[PaperEvidenceCard],
        adjacent_cards: list[PaperEvidenceCard],
    ) -> list[PaperEvidenceCard]:
        ranked = [
            card
            for card in core_cards + adjacent_cards
            if card.limitations or card.open_questions
        ]
        ranked.sort(
            key=lambda card: (
                FIT_TIER_PRIORITY.get(card.fit_tier, 3),
                0 if card.evidence_level == "fulltext" else 1,
                -(card.year or 0),
            )
        )
        return ranked

    def _topic_profile(self, topic: str) -> dict[str, Any]:
        lowered = topic.lower()
        axes = []
        if self._contains_any(lowered, TEXT_TOKENS):
            axes.append("text/prompt/referring")
        if self._contains_any(lowered, SEGMENT_TOKENS):
            axes.append("segmentation/mask")
        if self._contains_any(lowered, DIFFUSION_TOKENS):
            axes.append("diffusion/latent")
        return {
            "requires_text": "text/prompt/referring" in axes,
            "requires_segmentation": "segmentation/mask" in axes,
            "requires_diffusion": "diffusion/latent" in axes,
            "required_axes": axes,
        }

    def _topic_boundary_text(self, topic_profile: dict[str, Any]) -> str:
        axes = topic_profile["required_axes"]
        if axes:
            axis_text = "、".join(axes)
            return (
                "目标边界：主结论只针对同时触及 "
                f"{axis_text} 的论文；其他论文最多作为可迁移邻近证据。"
            )
        return "目标边界：优先保留直接命中当前主题设定的论文，其他论文按邻近迁移或附录处理。"

    def _paper_signal_flags(self, card: PaperEvidenceCard) -> dict[str, bool]:
        text = " ".join(
            [
                card.title,
                card.problem,
                card.method,
                " ".join(card.key_claims),
                " ".join(card.evidence),
                " ".join(card.datasets_metrics),
                " ".join(card.limitations),
                " ".join(card.open_questions),
            ]
        ).lower()
        return {
            "text_prompt": self._contains_any(text, TEXT_TOKENS),
            "referring": self._contains_any(text, REFERRING_TOKENS),
            "segmentation": self._contains_any(text, SEGMENT_TOKENS),
            "diffusion": self._contains_any(text, DIFFUSION_TOKENS),
            "medical": self._contains_any(text, MEDICAL_TOKENS),
            "remote_sensing": self._contains_any(text, REMOTE_TOKENS),
            "grounding": self._contains_any(text, GROUNDING_TOKENS),
            "generation": self._contains_any(text, GENERATION_TOKENS),
            "layout": self._contains_any(text, LAYOUT_TOKENS),
            "dense_prediction": self._contains_any(text, DENSE_TOKENS),
            "benchmark": self._contains_any(text, BENCHMARK_TOKENS),
        }

    @staticmethod
    def _task_family(signals: dict[str, bool]) -> str:
        if signals["segmentation"] and signals["diffusion"] and (
            signals["text_prompt"] or signals["referring"]
        ):
            return "text-conditioned diffusion segmentation"
        if signals["medical"] and signals["segmentation"] and (
            signals["text_prompt"] or signals["referring"]
        ):
            return "medical prompt segmentation"
        if signals["remote_sensing"] and signals["segmentation"] and (
            signals["text_prompt"] or signals["referring"]
        ):
            return "remote sensing referring segmentation"
        if signals["grounding"]:
            return "vision-language grounding"
        if signals["diffusion"] and (signals["dense_prediction"] or signals["segmentation"]):
            return "diffusion dense prediction"
        if signals["layout"] or (signals["generation"] and signals["text_prompt"]):
            return "layout or text-to-image guidance"
        if signals["segmentation"] and (signals["text_prompt"] or signals["referring"]):
            return "text-guided segmentation"
        if signals["segmentation"]:
            return "segmentation"
        if signals["diffusion"]:
            return "diffusion modeling"
        return "other"

    @staticmethod
    def _modality_family(signals: dict[str, bool]) -> str:
        if signals["medical"]:
            return "medical imaging"
        if signals["remote_sensing"]:
            return "remote sensing"
        if signals["layout"]:
            return "documents or layout"
        if signals["grounding"] or signals["text_prompt"] or signals["referring"]:
            return "vision-language"
        return "general vision"

    @staticmethod
    def _conditioning_family(signals: dict[str, bool]) -> str:
        if signals["referring"]:
            return "referring expression"
        if signals["text_prompt"] and signals["diffusion"]:
            return "text prompt + latent diffusion"
        if signals["text_prompt"]:
            return "text prompt"
        if signals["layout"]:
            return "layout guidance"
        if signals["diffusion"]:
            return "latent diffusion prior"
        return "weak or unspecified conditioning"

    @staticmethod
    def _prediction_family(signals: dict[str, bool]) -> str:
        if signals["segmentation"]:
            return "segmentation mask"
        if signals["dense_prediction"]:
            return "dense prediction"
        if signals["grounding"]:
            return "grounding localization"
        if signals["generation"] or signals["layout"]:
            return "image generation or guidance"
        return "other"

    def _fit_tier_and_reason(
        self,
        topic_profile: dict[str, Any],
        signals: dict[str, bool],
    ) -> tuple[str, str]:
        axes: list[tuple[str, bool]] = []
        if topic_profile["requires_text"]:
            axes.append(("text/prompt/referring", signals["text_prompt"] or signals["referring"]))
        if topic_profile["requires_segmentation"]:
            axes.append(("segmentation/mask", signals["segmentation"]))
        if topic_profile["requires_diffusion"]:
            axes.append(("diffusion/latent", signals["diffusion"]))
        matched_axes = [label for label, hit in axes if hit]
        missing_axes = [label for label, hit in axes if not hit]
        domain_shift = (
            signals["medical"]
            or signals["remote_sensing"]
            or signals["grounding"]
            or signals["layout"]
            or (signals["generation"] and not signals["segmentation"])
        )
        adjacent_reasons = []
        if signals["medical"]:
            adjacent_reasons.append("medical transfer")
        if signals["remote_sensing"]:
            adjacent_reasons.append("remote sensing transfer")
        if signals["grounding"]:
            adjacent_reasons.append("VL grounding")
        if signals["layout"] or signals["generation"]:
            adjacent_reasons.append("layout/text-to-image guidance")
        if signals["diffusion"] and signals["dense_prediction"] and not signals["segmentation"]:
            adjacent_reasons.append("diffusion dense prediction")

        if axes:
            if len(matched_axes) == len(axes) and not domain_shift:
                return (
                    "core",
                    "Directly matches the topic boundary on "
                    + ", ".join(matched_axes)
                    + ".",
                )
            if matched_axes or adjacent_reasons:
                reason_parts = []
                if matched_axes:
                    reason_parts.append("matches " + ", ".join(matched_axes))
                if missing_axes:
                    reason_parts.append("still misses " + ", ".join(missing_axes))
                if adjacent_reasons:
                    reason_parts.append("best used as " + ", ".join(adjacent_reasons))
                return "adjacent_transfer", "; ".join(reason_parts) + "."
            return (
                "off_target",
                "Confirmed paper, but it does not match the topic's main conditioning or prediction setup.",
            )

        if signals["segmentation"] or signals["diffusion"] or signals["text_prompt"] or signals["referring"]:
            if domain_shift:
                return (
                    "adjacent_transfer",
                    "Touches related technical ingredients, but the primary setting is still better treated as transfer evidence.",
                )
            return (
                "core",
                "No explicit topic axes were detected, so the paper is treated as direct evidence based on the main technical ingredients.",
            )
        return (
            "off_target",
            "Confirmed paper, but its task family is too far from the current topic boundary.",
        )

    @staticmethod
    def _contains_any(text: str, tokens: tuple[str, ...] | set[str]) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in tokens)

    @staticmethod
    def _most_common_labels(
        cards: list[PaperEvidenceCard],
        *,
        attr: str,
        limit: int,
    ) -> list[str]:
        counter = Counter(getattr(card, attr) for card in cards if getattr(card, attr))
        return [label for label, _ in counter.most_common(limit)]

    @staticmethod
    def _serialize_card(card: PaperEvidenceCard) -> dict[str, Any]:
        return {
            "paper_id": card.paper_id,
            "title": card.title,
            "year": card.year,
            "source": card.source,
            "evidence_level": card.evidence_level,
            "fulltext_source": card.fulltext_source,
            "problem": card.problem,
            "setting": card.setting,
            "method": card.method,
            "key_claims": card.key_claims,
            "evidence": card.evidence,
            "datasets_metrics": card.datasets_metrics,
            "limitations": card.limitations,
            "open_questions": card.open_questions,
            "source_excerpt_refs": card.source_excerpt_refs,
            "fit_tier": card.fit_tier,
            "fit_reason": card.fit_reason,
            "task_family": card.task_family,
            "modality_family": card.modality_family,
            "conditioning_family": card.conditioning_family,
            "prediction_family": card.prediction_family,
        }

    def _compact_card_payload(self, card: PaperEvidenceCard) -> dict[str, Any]:
        return {
            "title": card.title,
            "year": card.year,
            "source": card.source,
            "evidence_level": card.evidence_level,
            "fulltext_source": card.fulltext_source,
            "problem": self._excerpt(card.problem, 160),
            "setting": self._excerpt(card.setting, 160),
            "method": self._excerpt(card.method, 160),
            "key_claims": [self._excerpt(item, 160) for item in card.key_claims[:3]],
            "evidence": [self._excerpt(item, 180) for item in card.evidence[:3]],
            "limitations": [self._excerpt(item, 160) for item in card.limitations[:3]],
            "open_questions": [self._excerpt(item, 160) for item in card.open_questions[:3]],
            "fit_tier": card.fit_tier,
            "fit_reason": self._excerpt(card.fit_reason, 180),
            "task_family": card.task_family,
            "modality_family": card.modality_family,
            "conditioning_family": card.conditioning_family,
            "prediction_family": card.prediction_family,
        }

    def _section_card_payload(self, card: PaperEvidenceCard) -> dict[str, Any]:
        payload = self._compact_card_payload(card)
        payload["source_excerpt_refs"] = [
            self._excerpt(item, 220) for item in card.source_excerpt_refs[:4]
        ]
        payload["fit_reason"] = self._excerpt(card.fit_reason, 220)
        return payload

    @staticmethod
    def _one_liner(value: Any) -> str:
        text = str(value or "").strip()
        text = re.sub(r"\s+", " ", text)
        return text[:320].strip()

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned = [re.sub(r"\s+", " ", str(item or "").strip()) for item in value]
        return [item for item in cleaned if item]

    def _select_excerpts(
        self,
        resolved: ResolvedPaperFulltext,
        paper: dict[str, Any],
    ) -> list[str]:
        text = resolved.text.strip()
        if not text:
            abstract = str(paper.get("abstract") or paper.get("ai_reason") or "").strip()
            return [abstract] if abstract else []
        paragraphs = [
            self._excerpt(paragraph, 520)
            for paragraph in re.split(r"\n\s*\n+", text)
            if paragraph.strip()
        ]
        if len(paragraphs) == 1:
            paragraphs = [
                self._excerpt(part, 520)
                for part in re.split(r"(?<=[。.!?])\s+", text)
                if part.strip()
            ]
        title_terms = self._top_terms(
            f"{paper.get('title') or ''} {paper.get('abstract') or ''}",
            limit=8,
        )
        scored: list[tuple[int, str]] = []
        priority_terms = {
            "method",
            "approach",
            "experiment",
            "result",
            "conclusion",
            "limitation",
            "future",
            "dataset",
            "benchmark",
            "evaluation",
            "framework",
        }
        for index, paragraph in enumerate(paragraphs):
            lowered = paragraph.lower()
            score = max(0, 8 - index)
            score += sum(lowered.count(term) for term in priority_terms)
            score += sum(lowered.count(term) for term in title_terms[:4])
            scored.append((score, paragraph))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [paragraphs[index] for index in range(min(2, len(paragraphs)))]
        for _, paragraph in scored:
            if paragraph not in selected:
                selected.append(paragraph)
            if len(selected) >= 8:
                break
        return selected[:8]

    def _fallback_problem(self, paper: dict[str, Any], excerpts: list[str]) -> str:
        return self._first_sentence(
            str(paper.get("abstract") or excerpts[0] if excerpts else paper.get("title") or "")
        ) or str(paper.get("title") or "问题设定仍需结合全文进一步确认。")

    def _fallback_setting(self, paper: dict[str, Any], excerpts: list[str]) -> str:
        candidate = self._keyword_sentence(
            excerpts,
            {"benchmark", "dataset", "evaluation", "task", "setting", "mask", "segmentation"},
        )
        if candidate:
            return candidate
        if paper.get("query_matches"):
            concepts = ", ".join(
                sorted(
                    {
                        str(item.get("concept") or "").strip()
                        for item in paper.get("query_matches") or []
                        if str(item.get("concept") or "").strip()
                    }
                )[:3]
            )
            if concepts:
                return f"当前论文主要落在这些检索设定或子任务中：{concepts}。"
        return "问题设定信息仍有限，需要继续核对输入条件、预测目标和评测边界。"

    def _fallback_method(self, paper: dict[str, Any], excerpts: list[str]) -> str:
        candidate = self._keyword_sentence(
            excerpts,
            {
                "method",
                "approach",
                "framework",
                "diffusion",
                "segmentation",
                "prompt",
                "grounding",
            },
        )
        if candidate:
            return candidate
        return self._first_sentence(str(paper.get("ai_reason") or paper.get("title") or ""))

    def _fallback_claims(self, paper: dict[str, Any], excerpts: list[str]) -> list[str]:
        claims = []
        if paper.get("ai_reason"):
            claims.append(self._one_liner(paper.get("ai_reason")))
        for excerpt in excerpts:
            sentence = self._first_sentence(excerpt)
            if sentence and sentence not in claims:
                claims.append(sentence)
            if len(claims) >= 3:
                break
        return claims or ["当前论文的关键结论仍需结合全文进一步确认。"]

    def _fallback_limitations(
        self,
        resolved: ResolvedPaperFulltext,
        excerpts: list[str],
    ) -> list[str]:
        sentences = self._extract_keyword_sentences(
            excerpts,
            {"limitation", "however", "future", "challenge", "constraint", "不足"},
            3,
        )
        if sentences:
            return sentences
        if resolved.evidence_level == "abstract":
            return ["当前仅有摘要级证据，无法可靠判断实验限制、边界条件与失败模式。"]
        return ["正文尚未显式提炼 limitation，小结需要继续精读 method / experiment / conclusion。"]

    def _fallback_questions(
        self,
        resolved: ResolvedPaperFulltext,
        excerpts: list[str],
    ) -> list[str]:
        sentences = self._extract_keyword_sentences(
            excerpts,
            {"future", "open", "question", "direction", "next"},
            3,
        )
        if sentences:
            return sentences
        if resolved.evidence_level == "abstract":
            return ["后续应优先核验这篇论文的输入条件、预测目标与 benchmark 设定。"]
        return ["值得继续追问该方法在不同 prompt、数据域和评测协议下是否仍保持同样结论。"]

    @staticmethod
    def _keyword_sentence(excerpts: list[str], keywords: set[str]) -> str:
        for excerpt in excerpts:
            lowered = excerpt.lower()
            if any(keyword in lowered for keyword in keywords):
                return ScholarlyReportPipeline._first_sentence(excerpt)
        return ""

    @staticmethod
    def _extract_keyword_sentences(
        excerpts: list[str],
        keywords: set[str],
        limit: int,
    ) -> list[str]:
        collected: list[str] = []
        for excerpt in excerpts:
            for sentence in re.split(r"(?<=[。.!?])\s+", excerpt):
                lowered = sentence.lower()
                if any(keyword in lowered for keyword in keywords):
                    cleaned = re.sub(r"\s+", " ", sentence).strip()
                    if cleaned and cleaned not in collected:
                        collected.append(cleaned)
                if len(collected) >= limit:
                    return collected[:limit]
        return collected[:limit]

    @staticmethod
    def _first_sentence(text: str) -> str:
        for sentence in re.split(r"(?<=[。.!?])\s+", text or ""):
            cleaned = re.sub(r"\s+", " ", sentence).strip()
            if len(cleaned) >= 12:
                return cleaned[:280]
        return re.sub(r"\s+", " ", text or "").strip()[:280]

    @staticmethod
    def _top_terms(text: str, *, limit: int) -> list[str]:
        counter = Counter(
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token not in STOPWORDS and len(token) > 2
        )
        return [token for token, _ in counter.most_common(limit)]

    @staticmethod
    def _query_summary(queries: list[Any]) -> str:
        if not queries:
            return "无检索式"
        if isinstance(queries[0], str):
            return ", ".join(str(item) for item in queries if item)
        concepts = []
        for item in queries:
            if not isinstance(item, dict):
                continue
            concept = str(item.get("concept") or "").strip()
            count = item.get("result_count") or 0
            if concept:
                concepts.append(f"{concept}({count})")
        return ", ".join(concepts) or "无检索式"

    @staticmethod
    def _excerpt(text: str, limit: int) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        if len(compact) <= limit:
            return compact or "无摘要。"
        return compact[: limit - 1].rstrip() + "…"
