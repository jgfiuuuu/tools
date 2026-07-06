# ruff: noqa: E402

from __future__ import annotations

import base64
import gc
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import Configuration
from services.scholarly_graph import default_workflow_metrics
from services.scholarly_rerank import ScholarlyScreeningService
from services.scholarly_search import ScholarlySearchService
from services.scholarly_store import ScholarlyStore
from services.scholarly_workflow import ScholarlyResearchService

METRIC_KEYS = set(default_workflow_metrics())


def make_query_tasks() -> list[dict[str, Any]]:
    return [
        {
            "subtask_id": "concept_core",
            "concept": "Core topic",
            "intent": "Capture the main problem framing.",
            "base_terms": ["retrieval augmented generation", "evaluation"],
            "query_types": ["core", "recent"],
            "frontier_expansion": None,
            "parent_subtask_id": None,
            "variants": [
                {
                    "query_id": "concept_core_core",
                    "query_type": "core",
                    "query_text": "retrieval augmented generation evaluation",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                },
                {
                    "query_id": "concept_core_recent",
                    "query_type": "recent",
                    "query_text": "retrieval augmented generation evaluation recent advances 2024 2025",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                },
            ],
        },
        {
            "subtask_id": "concept_method",
            "concept": "Methods",
            "intent": "Locate method and benchmark papers.",
            "base_terms": ["retrieval augmented generation", "benchmark"],
            "query_types": ["core"],
            "frontier_expansion": None,
            "parent_subtask_id": None,
            "variants": [
                {
                    "query_id": "concept_method_core",
                    "query_type": "core",
                    "query_text": "retrieval augmented generation benchmark",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                }
            ],
        },
    ]


def make_dense_papers(count: int = 25) -> list[dict[str, Any]]:
    papers: list[dict[str, Any]] = []
    for index in range(count):
        papers.append(
            {
                "title": f"RAG Evaluation Study {index}",
                "abstract": (
                    "This paper studies retrieval augmented generation evaluation, "
                    "benchmark design, and recent retrieval quality signals."
                ),
                "year": 2025 if index < 10 else 2024,
                "authors": ["Ada Researcher"],
                "venue": "TestConf",
                "url": f"https://example.com/{index}",
                "source": "openalex",
                "citation_count": 140 - index,
                "query_matches": [
                    {
                        "subtask_id": "concept_core",
                        "concept": "Core topic",
                        "intent": "Capture the main problem framing.",
                        "query_type": "core",
                        "query_text": "retrieval augmented generation evaluation",
                        "source": "openalex",
                    },
                    {
                        "subtask_id": "concept_method",
                        "concept": "Methods",
                        "intent": "Locate method and benchmark papers.",
                        "query_type": "core",
                        "query_text": "retrieval augmented generation benchmark",
                        "source": "openalex",
                    },
                ],
            }
        )
    return papers


def make_sparse_papers() -> list[dict[str, Any]]:
    return [
        {
            "title": "Long-term Memory for General Agents",
            "abstract": "Persistent memory for autonomous agents operating over long tasks.",
            "year": 2023,
            "authors": ["Alex Agent"],
            "venue": "AgentConf",
            "source": "openalex",
            "citation_count": 7,
            "query_matches": [
                {
                    "subtask_id": "concept_core",
                    "concept": "Core topic",
                    "intent": "Capture the main problem framing.",
                    "query_type": "recent",
                    "query_text": "agent memory coding copilots recent",
                    "source": "openalex",
                    "frontier_expansion": "adjacent",
                }
            ],
        },
        {
            "title": "Tool Use for Web Agents",
            "abstract": "Tool augmentation for general agents with browser interaction.",
            "year": 2022,
            "authors": ["Blair Browser"],
            "venue": "WebAgent",
            "source": "arxiv",
            "citation_count": 2,
            "query_matches": [],
        },
    ]


def make_frontier_papers() -> list[dict[str, Any]]:
    return [
        {
            "title": "Editing Memory in Language Agents",
            "abstract": "Memory editing and persistent memory updates in language agents.",
            "year": 2025,
            "authors": ["Eden Editor"],
            "venue": "arXiv",
            "source": "arxiv",
            "citation_count": 5,
            "query_matches": [
                {
                    "subtask_id": "concept_core_adjacent",
                    "parent_subtask_id": "concept_core",
                    "concept": "Core topic adjacent",
                    "intent": "Expand to adjacent concepts when direct matches are sparse.",
                    "query_type": "core",
                    "query_text": "agent memory coding copilots adjacent",
                    "source": "arxiv",
                    "frontier_expansion": "adjacent",
                }
            ],
        },
        {
            "title": "RepoCoder: Repository-Level Code Completion Through Iterative Retrieval",
            "abstract": "Repository-level retrieval for code completion agents.",
            "year": 2023,
            "authors": ["Riley Repo"],
            "venue": "CodeLM",
            "source": "openalex",
            "citation_count": 60,
            "query_matches": [
                {
                    "subtask_id": "concept_core",
                    "concept": "Core topic",
                    "intent": "Capture the main problem framing.",
                    "query_type": "core",
                    "query_text": "agent memory coding copilots",
                    "source": "openalex",
                }
            ],
        },
    ]


def make_selected_report_papers(count: int) -> list[dict[str, Any]]:
    papers = make_dense_papers(max(count, 1))[:count]
    for index, paper in enumerate(papers, start=1):
        paper["rank"] = index
        paper["selected"] = True
        paper["user_status"] = "included"
        paper["tags"] = (
            ["retrieval", "benchmark", "evaluation"]
            if index % 2
            else ["agent", "evaluation", "tool"]
        )
        paper["ai_reason"] = (
            "Shows strong benchmark coverage, recent evaluation setup, and practical retrieval tradeoffs."
        )
        paper["relevance_label"] = "must_read" if index <= 8 else "candidate"
        paper["final_score"] = 100 - index
        if index <= 3:
            paper["source"] = "arxiv"
        elif index <= 12:
            paper["source"] = "openalex"
        else:
            paper["source"] = "semantic_scholar"
    return papers


def make_segmentation_query_tasks() -> list[dict[str, Any]]:
    return [
        {
            "subtask_id": "prompt_diffusion_segmentation",
            "concept": "Prompted diffusion segmentation",
            "intent": "Find papers that jointly study text or referring prompts, segmentation masks, and diffusion components.",
            "base_terms": ["text-guided segmentation", "diffusion mask", "referring prompts"],
            "query_types": ["core", "recent"],
            "frontier_expansion": None,
            "parent_subtask_id": None,
            "variants": [
                {
                    "query_id": "prompt_diffusion_segmentation_core",
                    "query_type": "core",
                    "query_text": "text-guided diffusion segmentation masks referring prompts",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                },
                {
                    "query_id": "prompt_diffusion_segmentation_recent",
                    "query_type": "recent",
                    "query_text": "recent text-guided diffusion segmentation masks 2024 2025",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                },
            ],
        },
        {
            "subtask_id": "adjacent_transfer_routes",
            "concept": "Adjacent transfer routes",
            "intent": "Track medical, remote sensing, grounding, and layout-conditioned neighboring routes without merging them into the core evidence pool.",
            "base_terms": ["medical prompt segmentation", "remote sensing referring segmentation", "vision-language grounding"],
            "query_types": ["core"],
            "frontier_expansion": None,
            "parent_subtask_id": None,
            "variants": [
                {
                    "query_id": "adjacent_transfer_routes_core",
                    "query_type": "core",
                    "query_text": "medical prompt segmentation remote sensing referring segmentation vision-language grounding",
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                }
            ],
        },
    ]


def make_segmentation_report_papers() -> list[dict[str, Any]]:
    papers = [
        {
            "title": "TextPromptDiff: Text-Guided Latent Diffusion for Segmentation Masks",
            "abstract": (
                "This paper studies text-guided segmentation masks with latent diffusion, "
                "prompt conditioning, and benchmark evaluation on natural images."
            ),
            "year": 2025,
            "authors": ["Lina Core"],
            "venue": "CVPR",
            "source": "arxiv",
            "citation_count": 64,
            "tags": ["diffusion", "prompt", "segmentation"],
            "ai_reason": "Directly combines text prompts, segmentation masks, and latent diffusion in one benchmarked setup.",
        },
        {
            "title": "RefSegDiff: Referring Expression Diffusion Mask Decoder",
            "abstract": (
                "Referring-expression conditioned mask decoding with diffusion denoising "
                "for segmentation and prompt-aware evaluation."
            ),
            "year": 2024,
            "authors": ["Kai Core"],
            "venue": "NeurIPS",
            "source": "openalex",
            "citation_count": 41,
            "tags": ["referring", "mask", "diffusion"],
            "ai_reason": "Direct evidence for referring prompts plus diffusion-based mask prediction.",
        },
        {
            "title": "MedPromptSeg: Promptable Medical Segmentation with Diffusion Priors",
            "abstract": (
                "Promptable medical image segmentation with text prompts and diffusion priors "
                "for MRI lesion delineation."
            ),
            "year": 2025,
            "authors": ["Mira Transfer"],
            "venue": "MICCAI",
            "source": "openalex",
            "citation_count": 22,
            "tags": ["medical", "prompt", "segmentation"],
            "ai_reason": "Useful transfer evidence for promptable segmentation, but the domain is medical imaging.",
        },
        {
            "title": "RS-RefSeg: Remote Sensing Referring Segmentation",
            "abstract": (
                "Remote sensing referring segmentation guided by language descriptions and "
                "high-resolution masks."
            ),
            "year": 2024,
            "authors": ["Rui Transfer"],
            "venue": "TGRS",
            "source": "semantic_scholar",
            "citation_count": 19,
            "tags": ["remote", "referring", "segmentation"],
            "ai_reason": "Provides referring-segmentation transfer signals, but not in the target domain.",
        },
        {
            "title": "GroundMask: Vision-Language Grounding for Mask Localization",
            "abstract": (
                "Vision-language grounding aligns phrases with masks and boxes for localization "
                "under open-vocabulary supervision."
            ),
            "year": 2023,
            "authors": ["Gale Transfer"],
            "venue": "ICCV",
            "source": "openalex",
            "citation_count": 53,
            "tags": ["grounding", "vision-language"],
            "ai_reason": "Grounding evidence is adjacent and transferable, but not direct segmentation-with-diffusion proof.",
        },
        {
            "title": "LayoutGuideDiff: Layout-to-Image Guidance for Structured Generation",
            "abstract": (
                "Layout-guided text-to-image diffusion provides structural priors and controllable "
                "region layouts for generation."
            ),
            "year": 2024,
            "authors": ["Dana Layout"],
            "venue": "SIGGRAPH",
            "source": "arxiv",
            "citation_count": 17,
            "tags": ["layout", "generation", "diffusion"],
            "ai_reason": "Generation-adjacent control signals can inspire conditioning design, but this is not a segmentation paper.",
        },
        {
            "title": "Temporal Action Tokens for Video Recognition",
            "abstract": "Video action recognition with token mixers and temporal pooling.",
            "year": 2022,
            "authors": ["Omar Off"],
            "venue": "ECCV",
            "source": "openalex",
            "citation_count": 8,
            "tags": ["video", "recognition"],
            "ai_reason": "Confirmed paper but clearly off the main topic boundary.",
        },
    ]
    for index, paper in enumerate(papers, start=1):
        paper["rank"] = index
        paper["selected"] = True
        paper["user_status"] = "included"
        paper["relevance_label"] = "must_read" if index <= 2 else "candidate"
        paper["final_score"] = 100 - index
        paper["relevance_score"] = 0.95 - (index * 0.03)
        paper["novelty_score"] = 0.72 - (index * 0.02)
        paper["query_matches"] = [
            {
                "subtask_id": "prompt_diffusion_segmentation",
                "concept": "Prompted diffusion segmentation",
                "intent": "Find papers that jointly study text or referring prompts, segmentation masks, and diffusion components.",
                "query_type": "core",
                "query_text": "text-guided diffusion segmentation masks referring prompts",
                "source": str(paper["source"]),
            }
        ]
    return papers


def seed_deep_research_notes(workspace: Path, notes: list[dict[str, str]]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    index_payload = {
        "notes": [],
        "metadata": {
            "created_at": "2026-07-01T00:00:00",
            "total_notes": 0,
        },
    }
    for position, note in enumerate(notes, start=1):
        note_id = note.get("id") or f"note_seed_{position}"
        created_at = note.get("created_at") or f"2026-07-0{position}T00:00:00"
        index_payload["notes"].append(
            {
                "id": note_id,
                "title": note["title"],
                "type": note.get("type", "task_state"),
                "tags": note.get("tags", ["deep_research"]),
                "created_at": created_at,
            }
        )
        note_path = workspace / f"{note_id}.md"
        note_path.write_text(
            "\n".join(
                [
                    "---",
                    f"id: {note_id}",
                    f"title: {note['title']}",
                    f"type: {note.get('type', 'task_state')}",
                    f"tags: {json.dumps(note.get('tags', ['deep_research']), ensure_ascii=False)}",
                    f"created_at: {created_at}",
                    f"updated_at: {created_at}",
                    "---",
                    "",
                    f"# {note['title']}",
                    "",
                    note["content"],
                    "",
                ]
            ),
            encoding="utf-8",
        )
    index_payload["metadata"]["total_notes"] = len(index_payload["notes"])
    (workspace / "notes_index.json").write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def make_uploaded_pdf_bytes(text: str) -> bytes:
    safe_text = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({safe_text}) Tj ET"
    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
        f"4 0 obj\n<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream\nendobj\n",
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj.encode("latin-1")
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("latin-1")
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")
    return pdf


class StubSearch(ScholarlySearchService):
    def __init__(
        self,
        config: Configuration,
        *,
        base_raw_papers: list[dict[str, Any]],
        frontier_raw_papers: list[dict[str, Any]] | None = None,
        base_source_statuses: dict[str, str] | None = None,
        frontier_source_statuses: dict[str, str] | None = None,
        planner_notices: list[str] | None = None,
        frontier_notices: list[str] | None = None,
    ) -> None:
        super().__init__(config)
        self.base_raw_papers = deepcopy(base_raw_papers)
        self.frontier_raw_papers = deepcopy(frontier_raw_papers or [])
        self.base_source_statuses = base_source_statuses or {
            "openalex": "ok",
            "arxiv": "ok",
            "semantic_scholar": "skipped_missing_api_key",
        }
        self.frontier_source_statuses = frontier_source_statuses or self.base_source_statuses
        self.planner_notices = list(planner_notices or [])
        self.frontier_notices = list(frontier_notices or [])

    def generate_query_plan(self, topic: str) -> tuple[list[dict[str, Any]], list[str]]:
        del topic
        return deepcopy(make_query_tasks()), list(self.planner_notices)

    def retrieve_candidates(
        self,
        topic: str,
        limit: int | None = None,
        *,
        query_tasks: list[dict[str, Any]] | None = None,
        planner_notices: list[str] | None = None,
    ) -> dict[str, Any]:
        del topic, limit
        tasks = deepcopy(query_tasks or make_query_tasks())
        is_frontier = any(task.get("frontier_expansion") for task in tasks)
        raw_papers = deepcopy(
            self.frontier_raw_papers if is_frontier else self.base_raw_papers
        )
        source_statuses = dict(
            self.frontier_source_statuses if is_frontier else self.base_source_statuses
        )
        notices = list(planner_notices or [])
        notices.extend(self.frontier_notices if is_frontier else [])
        skipped_sources = [
            source_name
            for source_name, status in source_statuses.items()
            if str(status).startswith("skipped")
        ]

        for task in tasks:
            task["result_count"] = len(raw_papers)
            task["status"] = "ok" if raw_papers else "failed"
            for variant in task.get("variants") or []:
                variant["result_count"] = len(raw_papers)
                variant["status"] = task["status"]
                variant.setdefault(
                    "sources_succeeded",
                    [
                        source_name
                        for source_name, status in source_statuses.items()
                        if status == "ok"
                    ],
                )
                variant.setdefault(
                    "sources_failed",
                    [
                        {"source": source_name, "reason": status}
                        for source_name, status in source_statuses.items()
                        if status == "failed"
                    ],
                )
                variant.setdefault(
                    "sources_skipped",
                    [
                        {"source": source_name, "reason": status}
                        for source_name, status in source_statuses.items()
                        if str(status).startswith("skipped")
                    ],
                )

        return {
            "queries": tasks,
            "raw_papers": raw_papers,
            "degradation_notices": notices,
            "source_statuses": source_statuses,
            "skipped_sources": skipped_sources,
        }

    def build_frontier_expansion_tasks(
        self,
        topic: str,
        query_tasks: list[dict[str, Any]],
        *,
        max_tasks: int = 6,
    ) -> list[dict[str, Any]]:
        if not self.frontier_raw_papers:
            return []
        return super().build_frontier_expansion_tasks(
            topic,
            deepcopy(query_tasks),
            max_tasks=max_tasks,
        )


class StubTimeoutLLM:
    def available(self) -> bool:
        return True

    def complete_json(self, **_: Any) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
        raise TimeoutError("synthetic timeout")

    def complete_text(self, **_: Any) -> Any:
        raise TimeoutError("synthetic timeout")


class ScholarlyGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "scholarly.sqlite3")
        self.notes_workspace = Path(self.tempdir.name) / "notes"
        self.artifact_workspace = Path(self.tempdir.name) / "artifacts"
        self.config = Configuration.from_env(
            overrides={
                "scholarly_db_path": self.db_path,
                "notes_workspace": str(self.notes_workspace),
                "scholarly_artifact_dir": str(self.artifact_workspace),
                "llm_provider": "",
                "llm_base_url": "",
                "llm_model_id": "",
                "local_llm": "",
                "semantic_scholar_api_key": None,
                "scholarly_candidate_limit": 50,
                "scholarly_selection_limit": 20,
            }
        )
        self.search = ScholarlySearchService(self.config)
        self.screening = ScholarlyScreeningService(self.config)
        self.stub_searches: list[StubSearch] = []

    def tearDown(self) -> None:
        self.search.session.close()
        for stub in self.stub_searches:
            stub.session.close()
        gc.collect()
        self.tempdir.cleanup()

    def test_dedupe_and_normalize_merges_duplicate_papers(self) -> None:
        papers = [
            {
                "title": "RAGBench",
                "abstract": "retrieval augmented generation benchmark",
                "doi": "10.1234/ragbench",
                "source": "openalex",
                "citation_count": 14,
                "query_matches": [
                    {
                        "subtask_id": "concept_core",
                        "query_type": "core",
                        "source": "openalex",
                    }
                ],
            },
            {
                "title": "RAGBench",
                "abstract": "",
                "doi": "10.1234/ragbench",
                "source": "arxiv",
                "citation_count": 4,
                "query_matches": [
                    {
                        "subtask_id": "concept_method",
                        "query_type": "core",
                        "source": "arxiv",
                    }
                ],
            },
        ]

        deduped = self.search.dedupe_and_normalize(papers, limit=10)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["source"], "arxiv+openalex")
        self.assertEqual(deduped[0]["citation_count"], 14)
        self.assertEqual(len(deduped[0]["query_matches"]), 2)
        for match in deduped[0]["query_matches"]:
            self.assertIn("frontier_expansion", match)
            self.assertIn("parent_subtask_id", match)

    def test_store_session_defaults_expose_stable_metadata_shape(self) -> None:
        store = ScholarlyStore(self.db_path)

        session = store.create_session("retrieval augmented generation evaluation benchmark")

        self.assertEqual(session["source_statuses"], {})
        self.assertEqual(session["skipped_sources"], [])
        self.assertEqual(session["degradation_notices"], [])
        self.assertFalse(session["frontier_mode"])
        self.assertIsNone(session["frontier_reason"])
        self.assertEqual(set(session["metrics"]), METRIC_KEYS)
        self.assertEqual(session["metadata"]["source_contributions"], {})

    def test_query_plan_and_frontier_tasks_keep_contract_fields(self) -> None:
        query_tasks, _ = self.search.generate_query_plan(
            "retrieval augmented generation evaluation benchmark"
        )
        frontier_tasks = self.search.build_frontier_expansion_tasks(
            "retrieval augmented generation evaluation benchmark",
            query_tasks,
        )

        self.assertTrue(query_tasks)
        for task in query_tasks:
            self.assertIn("frontier_expansion", task)
            self.assertIn("parent_subtask_id", task)
            for variant in task["variants"]:
                self.assertIn("frontier_expansion", variant)
                self.assertIn("parent_subtask_id", variant)
                self.assertIsNone(variant["frontier_expansion"])
                self.assertIsNone(variant["parent_subtask_id"])

        self.assertTrue(frontier_tasks)
        for task in frontier_tasks:
            self.assertIsNotNone(task["frontier_expansion"])
            self.assertIsNotNone(task["parent_subtask_id"])
            for variant in task["variants"]:
                self.assertEqual(
                    variant["frontier_expansion"],
                    task["frontier_expansion"],
                )
                self.assertEqual(
                    variant["parent_subtask_id"],
                    task["parent_subtask_id"],
                )

    def test_merge_source_statuses_handles_partial_and_skip_cases(self) -> None:
        merged = self.search.merge_source_statuses(
            {
                "openalex": "ok",
                "arxiv": "failed",
                "semantic_scholar": "skipped_missing_api_key",
            },
            {
                "openalex": "failed",
                "arxiv": "ok",
                "semantic_scholar": "ok",
            },
        )

        self.assertEqual(merged["openalex"], "partial_failure")
        self.assertEqual(merged["arxiv"], "partial_failure")
        self.assertEqual(merged["semantic_scholar"], "ok")

    def test_recall_budgeting_prioritizes_core_and_adjacent_variants(self) -> None:
        original = self.search._search_source
        self.search._search_source = lambda source, query, limit: ([], None)
        try:
            query_tasks, _ = self.search.generate_query_plan(
                "retrieval augmented generation benchmark evaluation"
            )
            direct_result = self.search.retrieve_candidates(
                "retrieval augmented generation benchmark evaluation",
                36,
                query_tasks=deepcopy(query_tasks),
                planner_notices=[],
            )
            frontier_tasks = self.search.build_frontier_expansion_tasks(
                "retrieval augmented generation benchmark evaluation",
                query_tasks,
            )
            frontier_result = self.search.retrieve_candidates(
                "retrieval augmented generation benchmark evaluation",
                24,
                query_tasks=deepcopy(frontier_tasks),
                planner_notices=[],
            )
        finally:
            self.search._search_source = original

        direct_core_budgets = [
            variant["result_budget"]
            for task in direct_result["queries"]
            for variant in task.get("variants") or []
            if variant.get("query_type") == "core"
        ]
        direct_support_budgets = [
            variant["result_budget"]
            for task in direct_result["queries"]
            for variant in task.get("variants") or []
            if variant.get("query_type") != "core"
        ]
        self.assertTrue(direct_core_budgets)
        self.assertTrue(direct_support_budgets)
        self.assertGreater(
            sum(direct_core_budgets) / len(direct_core_budgets),
            sum(direct_support_budgets) / len(direct_support_budgets),
        )

        frontier_budgets = {
            task["frontier_expansion"]: task["variants"][0]["result_budget"]
            for task in frontier_result["queries"]
            if task.get("variants")
        }
        self.assertGreater(frontier_budgets["adjacent"], frontier_budgets["broader"])
        self.assertGreater(frontier_budgets["recent"], frontier_budgets["broader"])

    def test_build_session_metadata_tracks_source_contributions_and_quality(self) -> None:
        topic = "agentic memory editing for coding copilots"
        query_tasks = [
            {
                "subtask_id": "concept_core",
                "concept": "Core topic",
                "intent": "Capture the main problem framing.",
                "base_terms": ["agent memory", "coding copilots"],
                "query_types": ["core"],
                "variants": [{"query_type": "core"}],
            }
        ]
        frontier_tasks = self.search.build_frontier_expansion_tasks(topic, query_tasks)
        raw_papers = [*make_sparse_papers(), *make_frontier_papers()]
        deduped = self.search.dedupe_and_normalize(raw_papers, limit=20)
        coarse = self.screening.coarse_rerank(topic, deduped, query_tasks, limit=20)
        final_ranked = self.screening.finalize_rerank(topic, coarse, query_tasks, limit=20)

        metadata = self.search.build_session_metadata(
            topic=topic,
            query_tasks=query_tasks,
            frontier_query_tasks=frontier_tasks,
            raw_papers=raw_papers,
            deduped_papers=deduped,
            final_papers=final_ranked,
            source_statuses={
                "openalex": "ok",
                "arxiv": "partial_failure",
                "semantic_scholar": "skipped_missing_api_key",
            },
            skipped_sources=["semantic_scholar"],
            degradation_notices=["arXiv partially degraded during fallback"],
            frontier_mode=True,
            frontier_reason="weak_core_query_hits",
            metrics={"frontier_added_raw_count": 2},
        )

        self.assertIn("source_contributions", metadata)
        self.assertEqual(
            metadata["source_contributions"]["semantic_scholar"]["status"],
            "skipped_missing_api_key",
        )
        self.assertGreater(metadata["metrics"]["direct_query_count"], 0)
        self.assertGreater(metadata["metrics"]["frontier_query_count"], 0)
        self.assertGreater(metadata["metrics"]["candidate_pool_purity"], 0)
        self.assertGreaterEqual(metadata["metrics"]["frontier_contribution_rate"], 0)
        self.assertGreater(metadata["metrics"]["dedupe_ratio"], 0)

    def test_frontier_decision_does_not_trigger_on_dense_results(self) -> None:
        topic = "retrieval augmented generation evaluation benchmark"
        coarse = self.screening.coarse_rerank(
            topic,
            make_dense_papers(12),
            make_query_tasks(),
            limit=50,
        )
        decision = self.screening.frontier_decision(topic, coarse, make_query_tasks())

        self.assertFalse(decision["frontier_mode"])
        self.assertIsNone(decision["frontier_reason"])
        self.assertGreaterEqual(decision["metrics"]["high_relevance_count"], 3)

    def test_frontier_decision_triggers_on_sparse_results(self) -> None:
        topic = "agentic memory editing for coding copilots"
        query_tasks = [
            {
                "subtask_id": "concept_core",
                "concept": "Core topic",
                "intent": "Capture the main problem framing.",
                "base_terms": ["agent memory", "coding copilots"],
                "query_types": ["core"],
                "variants": [{"query_type": "core"}],
            }
        ]
        coarse = self.screening.coarse_rerank(topic, make_sparse_papers(), query_tasks, limit=50)
        decision = self.screening.frontier_decision(topic, coarse, query_tasks)

        self.assertTrue(decision["frontier_mode"])
        self.assertIsNotNone(decision["frontier_reason"])
        self.assertIn("weak_core_query_hits", decision["frontier_reason"])

    def test_finalize_rerank_keeps_direct_hits_above_frontier_only_hits(self) -> None:
        topic = "agentic memory editing for coding copilots"
        papers = [
            {
                "title": "Memory Editing for Coding Agents",
                "abstract": "Memory editing for coding copilots and repository agents.",
                "year": 2025,
                "authors": ["Casey Direct"],
                "source": "openalex",
                "citation_count": 18,
                "query_matches": [
                    {
                        "subtask_id": "concept_core",
                        "concept": "Core topic",
                        "intent": "Capture the main problem framing.",
                        "query_type": "core",
                        "query_text": "agentic memory editing coding copilots",
                        "source": "openalex",
                    }
                ],
            },
            {
                "title": "Persistent Memory for Autonomous Agents",
                "abstract": "Persistent memory design for agents with evolving tasks and tools.",
                "year": 2024,
                "authors": ["Taylor Frontier"],
                "source": "arxiv",
                "citation_count": 12,
                "query_matches": [
                    {
                        "subtask_id": "concept_core_adjacent",
                        "parent_subtask_id": "concept_core",
                        "concept": "Core topic adjacent",
                        "intent": "Expand to adjacent concepts when direct matches are sparse.",
                        "query_type": "core",
                        "query_text": "agent memory adjacent",
                        "source": "arxiv",
                        "frontier_expansion": "adjacent",
                    }
                ],
            },
        ]
        query_tasks = [
            {
                "subtask_id": "concept_core",
                "concept": "Core topic",
                "intent": "Capture the main problem framing.",
                "base_terms": ["agent memory", "coding copilots"],
                "query_types": ["core"],
                "variants": [{"query_type": "core"}],
            }
        ]

        coarse = self.screening.coarse_rerank(topic, papers, query_tasks, limit=50)
        final_ranked = self.screening.finalize_rerank(topic, coarse, query_tasks, limit=50)

        self.assertEqual(final_ranked[0]["title"], "Memory Editing for Coding Agents")
        frontier_only = next(
            paper
            for paper in final_ranked
            if paper["title"] == "Persistent Memory for Autonomous Agents"
        )
        self.assertTrue(frontier_only["frontier_only"])
        self.assertNotEqual(frontier_only["relevance_label"], "must_read")

    def test_create_session_stream_uses_graph_and_persists_ready_session(self) -> None:
        store = ScholarlyStore(self.db_path)
        search = StubSearch(self.config, base_raw_papers=make_dense_papers(8))
        self.stub_searches.append(search)
        service = ScholarlyResearchService(
            self.config,
            store=store,
            search=search,
            screening=ScholarlyScreeningService(self.config),
        )

        events = list(
            service.create_session_stream(
                "retrieval augmented generation evaluation benchmark"
            )
        )
        event_types = [event["type"] for event in events]

        self.assertIn("session_created", event_types)
        self.assertIn("query_plan_generated", event_types)
        self.assertIn("query_generated", event_types)
        self.assertIn("source_skipped", event_types)
        self.assertIn("subtask_completed", event_types)
        self.assertIn("papers_recalled", event_types)
        self.assertIn("paper_ranked", event_types)
        self.assertIn("screening_done", event_types)

        self.assertLess(event_types.index("session_created"), event_types.index("query_plan_generated"))
        self.assertLess(event_types.index("query_plan_generated"), event_types.index("papers_recalled"))
        self.assertLess(event_types.index("papers_recalled"), event_types.index("paper_ranked"))
        self.assertLess(event_types.index("paper_ranked"), event_types.index("screening_done"))

        final_session = next(
            event["session"] for event in events if event["type"] == "screening_done"
        )
        self.assertEqual(final_session["status"], "ready")
        self.assertEqual(
            final_session["source_statuses"]["semantic_scholar"],
            "skipped_missing_api_key",
        )
        self.assertTrue(METRIC_KEYS.issubset(final_session["metadata"]["metrics"].keys()))
        self.assertIn("frontier_mode", final_session["metadata"])
        self.assertIn("frontier_reason", final_session["metadata"])
        self.assertIn("source_contributions", final_session["metadata"])
        created_session = next(
            event["session"] for event in events if event["type"] == "session_created"
        )
        self.assertEqual(set(created_session["metrics"]), METRIC_KEYS)
        self.assertIn("frontier_mode", created_session["metadata"])
        self.assertIn("source_statuses", created_session["metadata"])
        self.assertIn("source_contributions", created_session["metadata"])

    def test_create_session_matches_stream_final_shape(self) -> None:
        store = ScholarlyStore(self.db_path)
        search = StubSearch(self.config, base_raw_papers=make_dense_papers(10))
        self.stub_searches.append(search)
        service = ScholarlyResearchService(
            self.config,
            store=store,
            search=search,
            screening=ScholarlyScreeningService(self.config),
        )

        direct_detail = service.create_session(
            "retrieval augmented generation evaluation benchmark"
        )
        stream_events = list(
            service.create_session_stream(
                "retrieval augmented generation evaluation benchmark"
            )
        )
        stream_detail = next(
            event["session"] for event in stream_events if event["type"] == "screening_done"
        )

        self.assertEqual(direct_detail["status"], "ready")
        self.assertEqual(stream_detail["status"], "ready")
        self.assertEqual(
            [paper["title"] for paper in direct_detail["papers"]],
            [paper["title"] for paper in stream_detail["papers"]],
        )
        self.assertEqual(
            direct_detail["metadata"]["frontier_mode"],
            stream_detail["metadata"]["frontier_mode"],
        )
        self.assertEqual(
            direct_detail["metadata"]["metrics"]["selected_count"],
            stream_detail["metadata"]["metrics"]["selected_count"],
        )

    def test_frontier_session_and_rescreen_preserve_metadata_and_scores(self) -> None:
        store = ScholarlyStore(self.db_path)
        search = StubSearch(
            self.config,
            base_raw_papers=make_sparse_papers(),
            frontier_raw_papers=make_frontier_papers(),
            frontier_source_statuses={
                "openalex": "ok",
                "arxiv": "partial_failure",
                "semantic_scholar": "skipped_missing_api_key",
            },
            frontier_notices=["arXiv partially degraded during fallback"],
        )
        self.stub_searches.append(search)
        service = ScholarlyResearchService(
            self.config,
            store=store,
            search=search,
            screening=ScholarlyScreeningService(self.config),
        )

        detail = service.create_session("agentic memory editing for coding copilots")
        self.assertTrue(detail["metadata"]["frontier_mode"])
        self.assertGreater(detail["metadata"]["metrics"]["frontier_query_count"], 0)
        self.assertEqual(
            detail["metadata"]["metrics"]["frontier_added_raw_count"],
            len(make_frontier_papers()),
        )
        self.assertGreater(detail["metadata"]["metrics"]["frontier_contribution_rate"], 0)
        self.assertIn("source_contributions", detail["metadata"])
        self.assertGreater(
            detail["metadata"]["source_contributions"]["openalex"]["top_pool_hits"],
            0,
        )
        self.assertEqual(detail["source_statuses"]["arxiv"], "partial_failure")

        before = [
            (
                paper["title"],
                paper["final_score"],
                paper["relevance_score"],
                paper["novelty_score"],
                paper["relevance_label"],
            )
            for paper in detail["papers"]
        ]
        rescreened = service.rescreen_session(detail["id"])
        after = [
            (
                paper["title"],
                paper["final_score"],
                paper["relevance_score"],
                paper["novelty_score"],
                paper["relevance_label"],
            )
            for paper in rescreened["papers"]
        ]

        self.assertEqual(before, after)
        self.assertTrue(rescreened["metadata"]["frontier_mode"])
        self.assertEqual(
            rescreened["metadata"]["frontier_reason"],
            detail["metadata"]["frontier_reason"],
        )
        self.assertEqual(
            rescreened["metadata"]["metrics"]["frontier_added_raw_count"],
            detail["metadata"]["metrics"]["frontier_added_raw_count"],
        )
        self.assertEqual(
            rescreened["metadata"]["source_contributions"]["openalex"]["raw_hits"],
            detail["metadata"]["source_contributions"]["openalex"]["raw_hits"],
        )
        self.assertTrue(METRIC_KEYS.issubset(rescreened["metadata"]["metrics"].keys()))

    def test_store_session_defaults_include_report_metadata_shape(self) -> None:
        store = ScholarlyStore(self.db_path)

        session = store.create_session("retrieval augmented generation evaluation benchmark")

        self.assertEqual(session["metadata"]["report_context"], {})
        self.assertEqual(session["metadata"]["llm_usage"]["total_tokens"], 0)
        self.assertIn("screening", session["metadata"]["llm_usage"]["by_stage"])
        self.assertEqual(
            session["metadata"]["report_artifacts"],
            {
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
            },
        )

    def test_generate_report_builds_tiered_memo_artifacts(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation with referring prompts")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={
                "source_statuses": {
                    "openalex": "ok",
                    "arxiv": "ok",
                    "semantic_scholar": "ok",
                },
                "metrics": {"selected_count": 7},
            },
        )
        store.upsert_session_papers(
            session["id"],
            make_segmentation_report_papers(),
            clear_existing=True,
        )
        seed_deep_research_notes(
            self.notes_workspace,
            [
                {
                    "id": "note_prior_1",
                    "title": "promptable segmentation history",
                    "type": "task_state",
                    "tags": ["deep_research", "task_1"],
                    "content": "Earlier deep research separated direct prompt-segmentation evidence from medical and remote-sensing transfer routes.",
                }
            ],
        )
        service = ScholarlyResearchService(self.config, store=store)

        report = service.generate_report(session["id"])
        detail = store.get_session_detail(session["id"])
        artifacts = detail["metadata"]["report_artifacts"]
        context = detail["metadata"]["report_context"]

        self.assertIn("## Research Landscape / 研究现状与路线图", report["content_markdown"])
        self.assertIn("## Evidence Strength & Disputes / 证据强弱与争议", report["content_markdown"])
        self.assertIn("## Promising Directions / 值得跟进的方向", report["content_markdown"])
        self.assertIn("本报告把当前主题限定为", report["content_markdown"])
        self.assertEqual(len(artifacts["tasks"]), 3)
        self.assertEqual(len(artifacts["paper_cards"]), 7)
        self.assertEqual(len(artifacts["memo_sections"]), 7)
        self.assertEqual(len(artifacts["review_sections"]), 7)
        self.assertEqual(len(artifacts["section_generation"]), 7)
        self.assertEqual(context["evidence_count"], 7)
        self.assertEqual(context["year_range"]["start"], 2022)
        self.assertEqual(context["year_range"]["end"], 2025)
        self.assertEqual(context["fulltext_count"], 0)
        self.assertEqual(context["abstract_only_count"], 7)
        self.assertEqual(context["synthesis_mode"], "fallback")
        self.assertEqual(context["evidence_bucket_counts"]["core"], 2)
        self.assertEqual(context["evidence_bucket_counts"]["adjacent_transfer"], 4)
        self.assertEqual(context["evidence_bucket_counts"]["off_target"], 1)
        self.assertEqual(len(artifacts["supporting_notes"]), 1)
        self.assertEqual(len(artifacts["evidence_buckets"]["core"]), 2)
        self.assertEqual(len(artifacts["evidence_buckets"]["adjacent_transfer"]), 4)
        self.assertEqual(len(artifacts["evidence_buckets"]["off_target"]), 1)
        positioning_section = next(
            section
            for section in artifacts["review_sections"]
            if section["id"] == "report-positioning"
        )
        self.assertGreaterEqual(len(positioning_section["narrative_paragraphs"]), 2)
        self.assertTrue(positioning_section["narrative_paragraphs"][0])
        self.assertEqual(artifacts["section_generation"][0]["mode"], "fallback")
        for task in artifacts["tasks"]:
            self.assertTrue(task["summary"])
            self.assertTrue(task["note_id"])
            self.assertNotIn("note_path", task)
            self.assertTrue((self.notes_workspace / f"{task['note_id']}.md").exists())
        for note in artifacts["supporting_notes"]:
            self.assertNotIn("path", note)
        medical_card = next(
            card for card in artifacts["paper_cards"] if card["title"].startswith("MedPromptSeg")
        )
        remote_card = next(
            card for card in artifacts["paper_cards"] if card["title"].startswith("RS-RefSeg")
        )
        off_target_card = next(
            card
            for card in artifacts["paper_cards"]
            if card["title"].startswith("Temporal Action Tokens")
        )
        self.assertEqual(medical_card["fit_tier"], "adjacent_transfer")
        self.assertEqual(remote_card["fit_tier"], "adjacent_transfer")
        self.assertEqual(off_target_card["fit_tier"], "off_target")
        directions_section = next(
            section
            for section in artifacts["memo_sections"]
            if section["id"] == "promising-directions"
        )
        directions_text = " ".join(item["text"] for item in directions_section["items"]).lower()
        self.assertIn("benchmark", directions_text)
        self.assertTrue(
            any(token in directions_text for token in ("diffusion", "prompt", "segmentation"))
        )
        for legacy_token in ("retrieval", "agent", "memory", "tool orchestration"):
            self.assertNotIn(legacy_token, report["content_markdown"].lower())
        self.assertEqual(detail["status"], "reported")
        self.assertEqual(len(detail["reports"]), 1)

    def test_generate_report_marks_evidence_limited_when_under_twenty(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok"}},
        )
        store.upsert_session_papers(
            session["id"],
            make_segmentation_report_papers()[:2],
            clear_existing=True,
        )
        service = ScholarlyResearchService(self.config, store=store)

        report = service.generate_report(session["id"])
        detail = store.get_session_detail(session["id"])

        self.assertIn("证据数量不足", report["content_markdown"])
        for task in detail["metadata"]["report_artifacts"]["tasks"]:
            note_text = (self.notes_workspace / f"{task['note_id']}.md").read_text(encoding="utf-8")
            self.assertIn("证据数量不足", note_text)

    def test_generate_report_with_zero_confirmed_papers_keeps_empty_report_semantics(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok"}},
        )
        service = ScholarlyResearchService(self.config, store=store)

        report = service.generate_report(session["id"])
        detail = store.get_session_detail(session["id"])

        self.assertIn("尚无已确认参考文献", report["content_markdown"])
        self.assertEqual(detail["metadata"]["report_artifacts"]["tasks"], [])
        self.assertEqual(detail["metadata"]["report_artifacts"]["supporting_notes"], [])
        self.assertEqual(detail["metadata"]["report_artifacts"]["paper_cards"], [])
        self.assertEqual(detail["metadata"]["report_artifacts"]["memo_sections"], [])
        self.assertEqual(detail["metadata"]["report_artifacts"]["review_sections"], [])
        self.assertEqual(detail["metadata"]["report_artifacts"]["section_generation"], [])
        self.assertEqual(
            detail["metadata"]["report_artifacts"]["evidence_buckets"],
            {"core": [], "adjacent_transfer": [], "off_target": []},
        )

    def test_upload_pdf_is_used_as_fulltext_evidence_and_updates_stratification(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation with referring prompts")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok"}},
        )
        store.upsert_session_papers(
            session["id"],
            make_segmentation_report_papers()[:1],
            clear_existing=True,
        )
        service = ScholarlyResearchService(self.config, store=store)
        paper = store.get_session_detail(session["id"])["papers"][0]

        uploaded = service.upload_paper_pdf(
            session["id"],
            paper["id"],
            filename="textpromptdiff.pdf",
            content_base64=base64.b64encode(
                make_uploaded_pdf_bytes(
                    "Text-guided latent diffusion segmentation improves mask fidelity, prompt alignment, and benchmark consistency."
                )
            ).decode("ascii"),
        )
        report = service.generate_report(session["id"])
        detail = store.get_session_detail(session["id"])
        context = detail["metadata"]["report_context"]
        paper_cards = detail["metadata"]["report_artifacts"]["paper_cards"]
        uploaded_card = next(
            card for card in paper_cards if card["title"].startswith("TextPromptDiff")
        )

        self.assertEqual(uploaded["fulltext_source"], "uploaded_pdf")
        self.assertEqual(uploaded["fulltext_status"], "completed")
        self.assertEqual(context["fulltext_count"], 1)
        self.assertEqual(context["uploaded_pdf_count"], 1)
        self.assertEqual(context["abstract_only_count"], 0)
        self.assertEqual(uploaded_card["fulltext_source"], "uploaded_pdf")
        self.assertEqual(uploaded_card["evidence_level"], "fulltext")
        self.assertEqual(uploaded_card["fit_tier"], "core")
        self.assertIn("latent diffusion", " ".join(uploaded_card["evidence"]).lower())
        self.assertIn("正文级证据 1 篇", report["content_markdown"])

    def test_resolve_fulltext_prefers_direct_pdf_over_html_routes(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation with referring prompts")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok"}},
        )
        paper = make_segmentation_report_papers()[0]
        paper["arxiv_id"] = "2501.12345"
        paper["url"] = "https://papers.example.test/landing"
        paper["pdf_url"] = "https://papers.example.test/textpromptdiff.pdf"
        store.upsert_session_papers(session["id"], [paper], clear_existing=True)
        service = ScholarlyResearchService(self.config, store=store)
        session_paper = store.get_session_detail(session["id"])["papers"][0]
        pdf_response = Mock()
        pdf_response.raise_for_status.return_value = None
        pdf_response.content = make_uploaded_pdf_bytes(
            "Direct PDF fulltext should be preferred before html landing pages for text-guided diffusion segmentation."
        )

        with patch.object(service.fulltext.session, "get", return_value=pdf_response) as mock_get:
            with patch.object(
                service.fulltext,
                "_fetch_html_text",
                side_effect=AssertionError("should not fetch arXiv HTML before direct PDF"),
            ):
                with patch.object(
                    service.fulltext,
                    "_fetch_open_url",
                    side_effect=AssertionError("should not fetch landing page before direct PDF"),
                ):
                    resolved = service.resolve_paper_fulltext(session["id"], session_paper["id"])

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_get.call_args.args[0], paper["pdf_url"])
        self.assertEqual(resolved["fulltext_source"], "open_pdf")
        self.assertEqual(resolved["fulltext_status"], "completed")
        self.assertEqual(resolved["fulltext_original_filename"], "textpromptdiff.pdf")
        self.assertGreater(resolved["fulltext_text_char_count"], 0)

    def test_resolve_fulltext_keeps_uploaded_pdf_priority(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation with referring prompts")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok"}},
        )
        paper = make_segmentation_report_papers()[0]
        paper["url"] = "https://papers.example.test/landing"
        paper["pdf_url"] = "https://papers.example.test/textpromptdiff.pdf"
        store.upsert_session_papers(session["id"], [paper], clear_existing=True)
        service = ScholarlyResearchService(self.config, store=store)
        session_paper = store.get_session_detail(session["id"])["papers"][0]
        service.upload_paper_pdf(
            session["id"],
            session_paper["id"],
            filename="manual-textpromptdiff.pdf",
            content_base64=base64.b64encode(
                make_uploaded_pdf_bytes(
                    "Manually uploaded PDF should stay ahead of any open-access fulltext cache."
                )
            ).decode("ascii"),
        )

        with patch.object(
            service.fulltext.session,
            "get",
            side_effect=AssertionError("remote fetch should not run when uploaded PDF already exists"),
        ):
            resolved = service.resolve_paper_fulltext(session["id"], session_paper["id"])

        self.assertEqual(resolved["fulltext_source"], "uploaded_pdf")
        self.assertEqual(resolved["fulltext_status"], "completed")
        self.assertEqual(resolved["fulltext_original_filename"], "manual-textpromptdiff.pdf")


    def test_llm_timeout_still_produces_structured_fallback_memo(self) -> None:
        store = ScholarlyStore(self.db_path)
        session = store.create_session("text-guided diffusion segmentation with referring prompts")
        store.update_session(
            session["id"],
            status="ready",
            queries=make_segmentation_query_tasks(),
            metadata={"source_statuses": {"openalex": "ok", "arxiv": "ok"}},
        )
        store.upsert_session_papers(
            session["id"],
            make_segmentation_report_papers()[:4],
            clear_existing=True,
        )
        service = ScholarlyResearchService(self.config, store=store)
        service.report_pipeline.llm = StubTimeoutLLM()

        report = service.generate_report(session["id"])
        detail = store.get_session_detail(session["id"])

        self.assertEqual(detail["metadata"]["report_context"]["synthesis_mode"], "fallback")
        self.assertEqual(len(detail["metadata"]["report_artifacts"]["review_sections"]), 7)
        self.assertGreaterEqual(
            len(
                detail["metadata"]["report_artifacts"]["review_sections"][0][
                    "narrative_paragraphs"
                ]
            ),
            2,
        )
        self.assertEqual(len(detail["metadata"]["report_artifacts"]["memo_sections"]), 7)
        self.assertIn("## Report Positioning / 报告定位", report["content_markdown"])


if __name__ == "__main__":
    unittest.main()
