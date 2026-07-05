# ruff: noqa: E402

from __future__ import annotations

import gc
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any

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


class ScholarlyGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "scholarly.sqlite3")
        self.config = Configuration.from_env(
            overrides={
                "scholarly_db_path": self.db_path,
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


if __name__ == "__main__":
    unittest.main()
