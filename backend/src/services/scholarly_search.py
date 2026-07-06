# ruff: noqa: D202,D107

"""Scholarly literature planning, search, and screening services."""

from __future__ import annotations

import html
import json
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import requests

from config import Configuration
from services.scholarly_contracts import (
    WORKFLOW_METRIC_DEFAULTS,
    default_llm_usage,
    default_session_metadata,
    default_workflow_metrics,
    merge_llm_usage,
)
from services.scholarly_llm import ScholarlyLLMService
from services.scholarly_store import normalize_title, paper_key

logger = logging.getLogger(__name__)

ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "based",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "via",
    "with",
    "idea",
    "research",
    "study",
    "研究",
    "想法",
    "方法",
    "模型",
    "问题",
}
TERM_LIBRARY = [
    {
        "canonical": "retrieval augmented generation",
        "label": "RAG",
        "kind": "method",
        "patterns": [
            "retrieval augmented generation",
            "retrieval augmented",
            "rag",
            "检索增强生成",
            "检索增强",
        ],
    },
    {
        "canonical": "representation learning",
        "label": "representation",
        "kind": "property",
        "patterns": [
            "representation learning",
            "representation",
            "表征学习",
            "表征",
            "表示学习",
            "表示",
        ],
    },
    {
        "canonical": "embeddings",
        "label": "embeddings",
        "kind": "property",
        "patterns": ["embeddings", "embedding", "嵌入", "向量表征"],
    },
    {
        "canonical": "retrieval",
        "label": "retrieval",
        "kind": "method",
        "patterns": ["retrieval", "dense retrieval", "检索", "召回"],
    },
    {
        "canonical": "benchmark evaluation",
        "label": "evaluation",
        "kind": "evaluation",
        "patterns": ["benchmark", "evaluation", "评估", "基准", "测评"],
    },
    {
        "canonical": "multimodal",
        "label": "multimodal",
        "kind": "method",
        "patterns": ["multimodal", "multi-modal", "多模态"],
    },
    {
        "canonical": "memory",
        "label": "memory",
        "kind": "method",
        "patterns": ["memory", "persistent memory", "记忆"],
    },
    {
        "canonical": "code generation",
        "label": "code generation",
        "kind": "application",
        "patterns": ["code generation", "coding", "代码生成"],
    },
    {
        "canonical": "question answering",
        "label": "question answering",
        "kind": "application",
        "patterns": ["question answering", "qa", "问答"],
    },
]
VARIANT_SUFFIXES = {
    "core": "",
    "survey": " survey review",
    "recent": " recent advances 2024 2025",
    "benchmark": " benchmark evaluation",
}
FRONTIER_NEIGHBORS = {
    "retrieval augmented generation": [
        "knowledge grounding",
        "context augmentation",
        "retrieval systems",
    ],
    "representation learning": [
        "feature learning",
        "embedding spaces",
        "latent representation",
    ],
    "embeddings": ["vector search", "dense retrieval", "semantic indexing"],
    "retrieval": ["information retrieval", "dense retrieval", "reranking"],
    "benchmark evaluation": ["leaderboard", "evaluation protocol", "diagnostic benchmark"],
    "multimodal": ["vision language", "cross modal", "multimodal reasoning"],
    "memory": ["long-term memory", "episodic memory", "persistent context"],
    "code generation": ["coding agents", "software engineering", "program synthesis"],
    "question answering": ["knowledge intensive qa", "fact grounding", "long-form qa"],
}
DIRECT_BUCKET_SHARES = {
    "direct_core": 0.64,
    "direct_support": 0.36,
}
FRONTIER_BUCKET_SHARES = {
    "frontier_adjacent": 0.5,
    "frontier_recent": 0.3,
    "frontier_broader": 0.2,
}
QUERY_TYPE_WEIGHTS = {
    "core": 1.0,
    "benchmark": 0.82,
    "recent": 0.72,
    "survey": 0.56,
}
FRONTIER_EXPANSION_WEIGHTS = {
    "adjacent": 1.0,
    "recent": 0.78,
    "broader": 0.58,
}


def tokenize(text: str) -> list[str]:
    """Tokenize mixed English and Chinese research text for scoring."""

    lowered = (text or "").lower()
    english = re.findall(r"[a-z][a-z0-9\-]{2,}", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
    return [token for token in english + chinese if token not in STOPWORDS]


def contains_cjk(text: str) -> bool:
    """Return whether a string contains Chinese/Japanese/Korean characters."""

    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def unique_strings(values: list[str]) -> list[str]:
    """Return a case-insensitive unique list preserving order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value.strip())
    return result


class ScholarlySearchService:
    """Plan AI/CS scholarly queries and search multiple literature sources."""

    def __init__(self, config: Configuration) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "DeepResearch Scholarly Workbench/0.1",
                "Accept": "application/json,application/xml,text/xml,*/*",
            }
        )
        self.timeout = 20
        self.max_retries = 1
        self.llm = ScholarlyLLMService(config)
        self._last_llm_usage = default_llm_usage()

    def generate_query_plan(self, topic: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Build concept-first scholarly query subtasks."""

        notices: list[str] = []
        self._last_llm_usage = default_llm_usage()
        rule_plan = self._rule_query_plan(topic)

        if not self._should_try_llm(topic):
            return rule_plan, notices

        llm_plan, usage = self._llm_query_plan(topic, rule_plan)
        self._last_llm_usage = merge_llm_usage(self._last_llm_usage, usage)
        if llm_plan:
            return llm_plan, notices

        notices.append("LLM 检索式规划不可用，已回退到规则拆词。")
        return rule_plan, notices

    def latest_llm_usage(self) -> dict[str, Any]:
        """Expose the most recent query-planning usage payload."""

        return default_llm_usage(self._last_llm_usage)

    def recall(
        self,
        topic: str,
        limit: int | None = None,
        *,
        query_tasks: list[dict[str, Any]] | None = None,
        planner_notices: list[str] | None = None,
    ) -> dict[str, Any]:
        """Recall, annotate, and de-duplicate candidate papers."""

        target = limit or self.config.scholarly_candidate_limit
        retrieved = self.retrieve_candidates(
            topic,
            target,
            query_tasks=query_tasks,
            planner_notices=planner_notices,
        )
        return {
            "queries": retrieved["queries"],
            "papers": self.dedupe_and_normalize(
                retrieved["raw_papers"],
                limit=target,
            ),
            "degradation_notices": retrieved["degradation_notices"],
            "source_statuses": retrieved["source_statuses"],
            "skipped_sources": retrieved["skipped_sources"],
        }

    def retrieve_candidates(
        self,
        topic: str,
        limit: int | None = None,
        *,
        query_tasks: list[dict[str, Any]] | None = None,
        planner_notices: list[str] | None = None,
    ) -> dict[str, Any]:
        """Recall raw papers and source health without de-duplication."""

        target = limit or self.config.scholarly_candidate_limit
        notices = list(planner_notices or [])
        if query_tasks is None:
            query_tasks, generated_notices = self.generate_query_plan(topic)
            notices.extend(generated_notices)
        self._apply_recall_budgets(query_tasks, target)

        raw_papers: list[dict[str, Any]] = []
        source_counters, source_statuses, skipped_sources = self._initial_source_tracking()
        for task in query_tasks:
            task_results = 0
            variant_statuses = []
            for variant in task.get("variants") or []:
                variant_results = self._run_variant(
                    task=task,
                    variant=variant,
                    raw_papers=raw_papers,
                    source_counters=source_counters,
                    source_statuses=source_statuses,
                )
                task_results += variant_results
                variant_statuses.append(str(variant.get("status") or "idle"))
            task["result_count"] = task_results
            task["status"] = self._summarize_variant_statuses(variant_statuses)

        final_statuses = self._finalize_source_statuses(source_statuses, source_counters)
        notices.extend(self._build_source_notices(final_statuses))
        return {
            "queries": query_tasks,
            "raw_papers": raw_papers,
            "degradation_notices": unique_strings(notices),
            "source_statuses": final_statuses,
            "skipped_sources": skipped_sources,
        }

    def dedupe_and_normalize(
        self,
        papers: list[dict[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Normalize recalled papers and keep the strongest recall pool."""

        target = limit or self.config.scholarly_candidate_limit
        normalized = [self._normalize_paper(item) for item in self._dedupe(papers)]
        normalized.sort(key=self._recall_priority_key, reverse=True)
        return normalized[:target]

    def build_frontier_expansion_tasks(
        self,
        topic: str,
        query_tasks: list[dict[str, Any]],
        *,
        max_tasks: int = 6,
    ) -> list[dict[str, Any]]:
        """Build conservative adjacent/broader/recent variants for sparse topics."""

        frontier_tasks: list[dict[str, Any]] = []
        seed_tasks = [
            task
            for task in query_tasks
            if isinstance(task, dict) and task.get("base_terms")
        ] or query_tasks

        for task in seed_tasks[:2]:
            base_terms = unique_strings(
                [str(item).strip() for item in task.get("base_terms") or [] if str(item).strip()]
            )
            if not base_terms:
                continue

            adjacent_terms = unique_strings(base_terms[:2] + self._adjacent_terms(base_terms))
            broader_terms = self._broader_terms(topic, base_terms)
            frontier_tasks.append(
                self._make_frontier_task(
                    parent_task=task,
                    expansion_type="adjacent",
                    concept=f"{task.get('concept') or 'core'} adjacent",
                    intent="Expand to adjacent concepts when direct matches are sparse.",
                    base_terms=adjacent_terms[:4] or base_terms[:2],
                    query_types=["core"],
                )
            )
            frontier_tasks.append(
                self._make_frontier_task(
                    parent_task=task,
                    expansion_type="broader",
                    concept=f"{task.get('concept') or 'core'} broader",
                    intent="Back off to broader literature for frontier/background evidence.",
                    base_terms=broader_terms,
                    query_types=["core"],
                )
            )
            frontier_tasks.append(
                self._make_frontier_task(
                    parent_task=task,
                    expansion_type="recent",
                    concept=f"{task.get('concept') or 'core'} recent",
                    intent="Check only the latest adjacent frontier signal.",
                    base_terms=base_terms[:3],
                    query_types=["recent"],
                )
            )
            if len(frontier_tasks) >= max_tasks:
                break

        return frontier_tasks[:max_tasks]

    def merge_source_statuses(self, *status_maps: dict[str, str]) -> dict[str, str]:
        """Merge source health statuses across multiple recall passes."""

        merged: dict[str, str] = {}
        for mapping in status_maps:
            for source_name, status in mapping.items():
                previous = merged.get(source_name)
                merged[source_name] = self._merge_source_status(previous, status)
        return merged

    def query_mix_summary(
        self,
        query_tasks: list[dict[str, Any]] | None = None,
        frontier_query_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Summarize direct vs frontier query volume from task variants."""

        summary = {
            "direct_query_count": 0,
            "direct_core_query_count": 0,
            "frontier_query_count": 0,
            "frontier_adjacent_query_count": 0,
            "frontier_broader_query_count": 0,
            "frontier_recent_query_count": 0,
        }
        for task in [*(query_tasks or []), *(frontier_query_tasks or [])]:
            if not isinstance(task, dict):
                continue
            for variant in task.get("variants") or []:
                if not isinstance(variant, dict):
                    continue
                expansion = variant.get("frontier_expansion") or task.get("frontier_expansion")
                if expansion:
                    summary["frontier_query_count"] += 1
                    bucket_key = f"frontier_{str(expansion).strip().lower()}_query_count"
                    if bucket_key in summary:
                        summary[bucket_key] += 1
                    continue
                summary["direct_query_count"] += 1
                if variant.get("query_type") == "core":
                    summary["direct_core_query_count"] += 1
        return summary

    def source_contribution_summary(
        self,
        raw_papers: list[dict[str, Any]] | None = None,
        deduped_papers: list[dict[str, Any]] | None = None,
        ranked_papers: list[dict[str, Any]] | None = None,
        selected_papers: list[dict[str, Any]] | None = None,
        *,
        source_statuses: dict[str, str] | None = None,
        existing_summary: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Track which sources contribute to raw, shaped, and selected pools."""

        summary: dict[str, dict[str, Any]] = {}
        existing_map = existing_summary if isinstance(existing_summary, dict) else {}

        for source_name, payload in existing_map.items():
            summary[str(source_name)] = self._empty_source_contribution(
                status=str(payload.get("status") or "idle")
            )
            for field in (
                "raw_hits",
                "deduped_hits",
                "top_pool_hits",
                "selected_hits",
                "direct_top_hits",
                "frontier_top_hits",
            ):
                value = payload.get(field)
                summary[str(source_name)][field] = self._safe_int(value) or 0

        known_sources = set(summary)
        if isinstance(source_statuses, dict):
            known_sources.update(str(item) for item in source_statuses)
        for papers in (raw_papers, deduped_papers, ranked_papers, selected_papers):
            for paper in papers or []:
                known_sources.update(self._paper_sources(paper))
        for source_name in known_sources:
            summary.setdefault(
                source_name,
                self._empty_source_contribution(
                    status=(
                        str(source_statuses.get(source_name))
                        if isinstance(source_statuses, dict) and source_name in source_statuses
                        else "idle"
                    )
                ),
            )
            if isinstance(source_statuses, dict) and source_name in source_statuses:
                summary[source_name]["status"] = str(source_statuses[source_name])

        if raw_papers is not None:
            for payload in summary.values():
                payload["raw_hits"] = 0
            for paper in raw_papers:
                for source_name in self._paper_sources(paper):
                    self._ensure_source_contribution(summary, source_name)["raw_hits"] += 1

        if deduped_papers is not None:
            for payload in summary.values():
                payload["deduped_hits"] = 0
            for paper in deduped_papers:
                for source_name in self._paper_sources(paper):
                    self._ensure_source_contribution(summary, source_name)["deduped_hits"] += 1

        if ranked_papers is not None:
            for payload in summary.values():
                payload["top_pool_hits"] = 0
                payload["direct_top_hits"] = 0
                payload["frontier_top_hits"] = 0
            for paper in ranked_papers:
                for source_name in self._paper_sources(paper):
                    self._ensure_source_contribution(summary, source_name)["top_pool_hits"] += 1
                match_profile = self._paper_match_profile(paper)
                for source_name in match_profile["direct_sources"]:
                    self._ensure_source_contribution(summary, source_name)["direct_top_hits"] += 1
                for source_name in match_profile["frontier_sources"]:
                    self._ensure_source_contribution(summary, source_name)["frontier_top_hits"] += 1

        if selected_papers is not None:
            for payload in summary.values():
                payload["selected_hits"] = 0
            for paper in selected_papers:
                for source_name in self._paper_sources(paper):
                    self._ensure_source_contribution(summary, source_name)["selected_hits"] += 1

        return {
            source_name: summary[source_name]
            for source_name in sorted(summary)
        }

    def candidate_pool_metrics(
        self,
        topic: str,
        papers: list[dict[str, Any]] | None,
        query_tasks: list[dict[str, Any]] | None = None,
        *,
        selected_papers: list[dict[str, Any]] | None = None,
        limit: int = 20,
    ) -> dict[str, int | float]:
        """Estimate purity, drift, and direct/frontier contribution in the top pool."""

        top_pool = list(papers or [])[:limit]
        if not top_pool:
            return {
                "candidate_pool_purity": 0.0,
                "candidate_drift_score": 0.0,
                "direct_hit_coverage": 0.0,
                "frontier_contribution_rate": 0.0,
                "frontier_selected_count": 0,
            }

        topic_tokens = self._topic_token_set(topic, query_tasks or [])
        direct_task_ids = self._direct_task_ids(query_tasks or [])
        pure_count = 0
        drift_count = 0
        direct_hits: set[str] = set()
        frontier_papers = 0

        for paper in top_pool:
            match_profile = self._paper_match_profile(paper)
            topic_profile = self._paper_topic_profile(paper, topic_tokens)
            alignment = max(
                match_profile["query_overlap"],
                topic_profile["topic_overlap"],
                topic_profile["title_overlap"],
            )
            if (
                match_profile["direct_hits"]
                or match_profile["direct_core_hits"]
                or alignment >= 0.18
                or (
                    match_profile["frontier_hits"]
                    and alignment >= 0.14
                )
            ):
                pure_count += 1
            if (
                not match_profile["direct_hits"]
                and alignment < 0.10
                and (match_profile["frontier_only"] or not match_profile["query_matches"])
            ):
                drift_count += 1
            if match_profile["frontier_hits"]:
                frontier_papers += 1
            direct_hits.update(
                item.get("subtask_id")
                for item in match_profile["direct_core_matches"]
                if item.get("subtask_id") in direct_task_ids
            )

        selected = (
            list(selected_papers)
            if selected_papers is not None
            else [paper for paper in papers or [] if paper.get("selected")]
        )
        frontier_selected_count = sum(
            1
            for paper in selected
            if self._paper_match_profile(paper)["frontier_hits"] > 0
        )
        pool_size = len(top_pool)
        return {
            "candidate_pool_purity": round(pure_count / pool_size, 3),
            "candidate_drift_score": round(drift_count / pool_size, 3),
            "direct_hit_coverage": round(
                len(direct_hits) / max(1, len(direct_task_ids)),
                3,
            ),
            "frontier_contribution_rate": round(frontier_papers / pool_size, 3),
            "frontier_selected_count": frontier_selected_count,
        }

    def build_session_metadata(
        self,
        *,
        topic: str,
        query_tasks: list[dict[str, Any]] | None = None,
        frontier_query_tasks: list[dict[str, Any]] | None = None,
        raw_papers: list[dict[str, Any]] | None = None,
        deduped_papers: list[dict[str, Any]] | None = None,
        final_papers: list[dict[str, Any]] | None = None,
        source_statuses: dict[str, str] | None = None,
        skipped_sources: list[str] | None = None,
        degradation_notices: list[str] | None = None,
        frontier_mode: bool = False,
        frontier_reason: str | None = None,
        metrics: dict[str, Any] | None = None,
        existing_metadata: dict[str, Any] | None = None,
        llm_usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compose stable session metadata plus retrieval quality summaries."""

        existing = existing_metadata if isinstance(existing_metadata, dict) else {}
        merged_metrics = default_workflow_metrics(existing.get("metrics"))
        metric_overrides = metrics if isinstance(metrics, dict) else {}
        for key in WORKFLOW_METRIC_DEFAULTS:
            value = metric_overrides.get(key)
            if value is not None:
                merged_metrics[key] = value

        query_mix = self.query_mix_summary(
            query_tasks,
            frontier_query_tasks=frontier_query_tasks,
        )
        merged_metrics["direct_query_count"] = query_mix["direct_query_count"]
        merged_metrics["direct_core_query_count"] = query_mix["direct_core_query_count"]
        if frontier_query_tasks is not None:
            merged_metrics["frontier_query_count"] = query_mix["frontier_query_count"]
            merged_metrics["frontier_adjacent_query_count"] = query_mix[
                "frontier_adjacent_query_count"
            ]
            merged_metrics["frontier_broader_query_count"] = query_mix[
                "frontier_broader_query_count"
            ]
            merged_metrics["frontier_recent_query_count"] = query_mix[
                "frontier_recent_query_count"
            ]

        selected_papers = [
            paper
            for paper in final_papers or []
            if paper.get("selected")
        ]
        candidate_metrics = self.candidate_pool_metrics(
            topic,
            final_papers or deduped_papers or [],
            query_tasks,
            selected_papers=selected_papers,
        )
        for key, value in candidate_metrics.items():
            merged_metrics[key] = value

        if raw_papers is not None:
            merged_metrics["raw_paper_count"] = len(raw_papers)
        if deduped_papers is not None:
            merged_metrics["deduped_paper_count"] = len(deduped_papers)
        if raw_papers:
            merged_metrics["dedupe_ratio"] = round(
                len(deduped_papers or []) / max(1, len(raw_papers)),
                3,
            )
        if final_papers is not None:
            merged_metrics["final_candidate_count"] = len(final_papers)
            merged_metrics["selected_count"] = len(selected_papers)

        source_contributions = self.source_contribution_summary(
            raw_papers,
            deduped_papers,
            (final_papers or deduped_papers or [])[:20],
            selected_papers if final_papers is not None else None,
            source_statuses=source_statuses,
            existing_summary=existing.get("source_contributions"),
        )
        return default_session_metadata(
            {
                **existing,
                "source_statuses": (
                    source_statuses
                    if source_statuses is not None
                    else existing.get("source_statuses") or {}
                ),
                "skipped_sources": (
                    skipped_sources
                    if skipped_sources is not None
                    else existing.get("skipped_sources") or []
                ),
                "degradation_notices": (
                    degradation_notices
                    if degradation_notices is not None
                    else existing.get("degradation_notices") or []
                ),
                "frontier_mode": frontier_mode,
                "frontier_reason": (
                    frontier_reason
                    if frontier_reason is not None
                    else existing.get("frontier_reason")
                ),
                "metrics": merged_metrics,
                "source_contributions": source_contributions,
                "llm_usage": merge_llm_usage(existing.get("llm_usage"), llm_usage),
            }
        )

    def _initial_source_tracking(
        self,
    ) -> tuple[dict[str, dict[str, int]], dict[str, str], list[str]]:
        source_counters = {
            "openalex": {"attempted": 0, "succeeded": 0, "failed": 0},
            "arxiv": {"attempted": 0, "succeeded": 0, "failed": 0},
            "semantic_scholar": {"attempted": 0, "succeeded": 0, "failed": 0},
        }
        source_statuses: dict[str, str] = {
            "openalex": "enabled",
            "arxiv": "enabled",
            "semantic_scholar": "enabled",
        }
        skipped_sources: list[str] = []
        if not self.config.semantic_scholar_api_key:
            source_statuses["semantic_scholar"] = "skipped_missing_api_key"
            skipped_sources.append("semantic_scholar")
        return source_counters, source_statuses, skipped_sources

    def _apply_recall_budgets(
        self,
        query_tasks: list[dict[str, Any]],
        target: int,
    ) -> None:
        """Assign per-variant recall budgets for direct vs frontier passes."""

        if not query_tasks:
            return

        frontier_mode = any(task.get("frontier_expansion") for task in query_tasks)
        bucket_shares = (
            FRONTIER_BUCKET_SHARES if frontier_mode else DIRECT_BUCKET_SHARES
        )
        bucket_variants: dict[str, list[dict[str, Any]]] = {}

        for task in query_tasks:
            if not isinstance(task, dict):
                continue
            task_bucket = self._task_recall_bucket(task)
            task["recall_bucket"] = task_bucket
            task_variants = [
                variant
                for variant in task.get("variants") or []
                if isinstance(variant, dict)
            ]
            for variant in task_variants:
                bucket = self._variant_recall_bucket(task, variant)
                variant["recall_bucket"] = bucket
                variant["recall_priority"] = round(
                    self._variant_recall_priority(task, variant),
                    3,
                )
                bucket_variants.setdefault(bucket, []).append(variant)

        min_total_budget = max(12, len([v for values in bucket_variants.values() for v in values]) * 3)
        total_budget = max(target, min_total_budget)
        for bucket_name, variants in bucket_variants.items():
            share = bucket_shares.get(
                bucket_name,
                1 / max(1, len(bucket_variants)),
            )
            bucket_budget = max(len(variants) * 3, math.ceil(total_budget * share))
            total_weight = sum(
                float(variant.get("recall_priority") or 0.0)
                for variant in variants
            )
            for variant in variants:
                priority = float(variant.get("recall_priority") or 0.0)
                proportional = bucket_budget * (
                    priority / max(total_weight, 1e-6)
                )
                variant["result_budget"] = max(3, min(14, math.ceil(proportional)))

        for task in query_tasks:
            variants = [
                variant
                for variant in task.get("variants") or []
                if isinstance(variant, dict)
            ]
            task["result_budget"] = sum(
                self._safe_int(variant.get("result_budget")) or 0
                for variant in variants
            )

    @staticmethod
    def _task_recall_bucket(task: dict[str, Any]) -> str:
        expansion = str(task.get("frontier_expansion") or "").strip().lower()
        if expansion:
            return f"frontier_{expansion}"
        query_types = {
            str(item).strip().lower()
            for item in task.get("query_types") or []
            if str(item).strip()
        }
        return "direct_core" if "core" in query_types else "direct_support"

    def _variant_recall_bucket(
        self,
        task: dict[str, Any],
        variant: dict[str, Any],
    ) -> str:
        expansion = str(
            variant.get("frontier_expansion") or task.get("frontier_expansion") or ""
        ).strip().lower()
        if expansion:
            return f"frontier_{expansion}"
        return "direct_core" if variant.get("query_type") == "core" else "direct_support"

    def _variant_recall_priority(
        self,
        task: dict[str, Any],
        variant: dict[str, Any],
    ) -> float:
        query_type = str(variant.get("query_type") or "core").strip().lower()
        expansion = str(
            variant.get("frontier_expansion") or task.get("frontier_expansion") or ""
        ).strip().lower()
        priority = QUERY_TYPE_WEIGHTS.get(query_type, 0.6)
        if expansion:
            priority *= FRONTIER_EXPANSION_WEIGHTS.get(expansion, 0.6)
        if task.get("parent_subtask_id"):
            priority *= 0.95
        return priority

    def _run_variant(
        self,
        *,
        task: dict[str, Any],
        variant: dict[str, Any],
        raw_papers: list[dict[str, Any]],
        source_counters: dict[str, dict[str, int]],
        source_statuses: dict[str, str],
    ) -> int:
        query_text = str(variant.get("query_text") or "").strip()
        if not query_text:
            variant["status"] = "empty"
            return 0

        variant["sources_attempted"] = []
        variant["sources_succeeded"] = []
        variant["sources_failed"] = []
        variant["sources_skipped"] = []
        total_results = 0

        for source_name in ("openalex", "arxiv", "semantic_scholar"):
            current_status = source_statuses.get(source_name, "enabled")
            if current_status.startswith("skipped"):
                variant["sources_skipped"].append(
                    {"source": source_name, "reason": current_status}
                )
                continue

            source_counters[source_name]["attempted"] += 1
            variant["sources_attempted"].append(source_name)
            variant_budget = self._safe_int(variant.get("result_budget")) or 4
            results, error = self._search_source(source_name, query_text, variant_budget)
            if error is not None:
                source_counters[source_name]["failed"] += 1
                variant["sources_failed"].append(
                    {"source": source_name, "reason": error}
                )
                continue

            source_counters[source_name]["succeeded"] += 1
            variant["sources_succeeded"].append(source_name)
            for paper in results:
                paper.setdefault("query_matches", []).append(
                    {
                        "subtask_id": task["subtask_id"],
                        "concept": task["concept"],
                        "intent": task["intent"],
                        "query_type": variant["query_type"],
                        "query_text": query_text,
                        "source": source_name,
                        "frontier_expansion": (
                            variant.get("frontier_expansion")
                            or task.get("frontier_expansion")
                        ),
                        "parent_subtask_id": task.get("parent_subtask_id"),
                    }
                )
            raw_papers.extend(results)
            total_results += len(results)

        variant["result_count"] = total_results
        variant["status"] = self._variant_status(variant)
        return total_results

    def _search_source(
        self,
        source_name: str,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if source_name == "openalex":
            return self._search_openalex(query, limit)
        if source_name == "arxiv":
            return self._search_arxiv(query, limit)
        return self._search_semantic_scholar(query, limit)

    def _search_arxiv(
        self,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        search_query = self._build_arxiv_query(query)
        if not search_query:
            return [], "skipped_non_english_query"
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query={search_query}"
            f"&start=0&max_results={limit}"
            "&sortBy=relevance&sortOrder=descending"
        )
        response, error = self._request(url, timeout=(5, 35))
        if error is not None:
            logger.warning("arXiv search failed for %s: %s", query, error)
            return [], error

        try:
            root = ET.fromstring(response.text)
        except Exception as exc:  # pragma: no cover - defensive parsing
            logger.warning("arXiv XML parse failed for %s: %s", query, exc)
            return [], str(exc)

        papers: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", ARXIV_NS):
            title = self._text(entry.find("atom:title", ARXIV_NS))
            abstract = self._text(entry.find("atom:summary", ARXIV_NS))
            published = self._text(entry.find("atom:published", ARXIV_NS))
            arxiv_url = self._text(entry.find("atom:id", ARXIV_NS))
            arxiv_id = arxiv_url.rstrip("/").split("/")[-1] if arxiv_url else None
            authors = [
                self._text(author.find("atom:name", ARXIV_NS))
                for author in entry.findall("atom:author", ARXIV_NS)
            ]
            pdf_url = None
            for link in entry.findall("atom:link", ARXIV_NS):
                if link.attrib.get("title") == "pdf":
                    pdf_url = link.attrib.get("href")
            papers.append(
                {
                    "title": title,
                    "abstract": abstract,
                    "year": self._year(published),
                    "authors": [item for item in authors if item],
                    "venue": "arXiv",
                    "arxiv_id": arxiv_id,
                    "url": arxiv_url,
                    "pdf_url": pdf_url,
                    "source": "arxiv",
                    "citation_count": 0,
                }
            )
        return papers, None

    def _search_semantic_scholar(
        self,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        headers = {"x-api-key": self.config.semantic_scholar_api_key or ""}
        params = {
            "query": query,
            "limit": limit,
            "fields": (
                "title,abstract,year,authors,venue,url,externalIds,"
                "citationCount,openAccessPdf"
            ),
        }
        response, error = self._request(url, params=params, headers=headers)
        if error is not None:
            logger.warning("Semantic Scholar search failed for %s: %s", query, error)
            return [], error

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive parsing
            logger.warning("Semantic Scholar JSON parse failed for %s: %s", query, exc)
            return [], str(exc)

        papers: list[dict[str, Any]] = []
        for item in payload.get("data") or []:
            external = item.get("externalIds") or {}
            pdf = item.get("openAccessPdf") or {}
            papers.append(
                {
                    "title": item.get("title") or "",
                    "abstract": item.get("abstract") or "",
                    "year": item.get("year"),
                    "authors": [
                        author.get("name")
                        for author in item.get("authors") or []
                        if author.get("name")
                    ],
                    "venue": item.get("venue"),
                    "doi": external.get("DOI"),
                    "arxiv_id": external.get("ArXiv"),
                    "semantic_scholar_id": item.get("paperId"),
                    "url": item.get("url"),
                    "pdf_url": pdf.get("url"),
                    "source": "semantic_scholar",
                    "citation_count": item.get("citationCount") or 0,
                }
            )
        return papers, None

    def _search_openalex(
        self,
        query: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        url = "https://api.openalex.org/works"
        headers = {}
        if self.config.openalex_api_key:
            headers["Authorization"] = f"Bearer {self.config.openalex_api_key}"
        params: dict[str, Any] = {
            "search": query,
            "per-page": limit,
            "select": (
                "id,doi,title,display_name,publication_year,authorships,"
                "primary_location,open_access,cited_by_count,abstract_inverted_index"
            ),
        }
        if self.config.openalex_email:
            params["mailto"] = self.config.openalex_email
        response, error = self._request(url, params=params, headers=headers)
        if error is not None:
            logger.warning("OpenAlex search failed for %s: %s", query, error)
            return [], error

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive parsing
            logger.warning("OpenAlex JSON parse failed for %s: %s", query, exc)
            return [], str(exc)

        papers: list[dict[str, Any]] = []
        for item in payload.get("results") or []:
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            open_access = item.get("open_access") or {}
            authors = []
            for authorship in item.get("authorships") or []:
                author = authorship.get("author") or {}
                if author.get("display_name"):
                    authors.append(author["display_name"])
            papers.append(
                {
                    "title": item.get("display_name") or item.get("title") or "",
                    "abstract": self._openalex_abstract(
                        item.get("abstract_inverted_index")
                    ),
                    "year": item.get("publication_year"),
                    "authors": authors,
                    "venue": source.get("display_name"),
                    "doi": self._clean_doi(item.get("doi")),
                    "openalex_id": item.get("id"),
                    "url": location.get("landing_page_url") or item.get("id"),
                    "pdf_url": location.get("pdf_url") or open_access.get("oa_url"),
                    "source": "openalex",
                    "citation_count": item.get("cited_by_count") or 0,
                }
            )
        return papers, None

    def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> tuple[requests.Response, str | None]:
        error_message = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout if timeout is not None else self.timeout,
                )
                response.raise_for_status()
                return response, None
            except requests.HTTPError as exc:
                error_message = self._format_request_error(exc)
                response = exc.response
                status_code = response.status_code if response is not None else 0
                if status_code not in {429, 500, 502, 503, 504}:
                    return requests.Response(), error_message
            except requests.RequestException as exc:
                error_message = self._format_request_error(exc)
            if attempt < self.max_retries:
                time.sleep(0.5 * (attempt + 1))
        return requests.Response(), error_message or "request_failed"

    def _rule_query_plan(self, topic: str) -> list[dict[str, Any]]:
        normalized_topic = re.sub(r"\s+", " ", topic.strip())
        detected_terms = self._detect_terms(normalized_topic)
        method_terms = [
            term["canonical"]
            for term in detected_terms
            if term["kind"] in {"method", "application"}
        ]
        property_terms = [
            term["canonical"]
            for term in detected_terms
            if term["kind"] == "property"
        ]
        evaluation_terms = [
            term["canonical"]
            for term in detected_terms
            if term["kind"] == "evaluation"
        ]
        fallback_tokens = unique_strings(tokenize(normalized_topic))
        if not method_terms and fallback_tokens:
            method_terms = fallback_tokens[:2]
        if not property_terms and len(fallback_tokens) > 2:
            property_terms = fallback_tokens[2:4]

        core_terms = unique_strings(method_terms + property_terms)[:5]
        if not core_terms:
            core_terms = ["retrieval augmented generation", "representation learning"]

        tasks = [
            self._make_query_task(
                subtask_id="concept_core",
                concept="核心问题",
                intent="定位最直接讨论该研究问题的方法论文与综述。",
                base_terms=core_terms,
                query_types=["core", "survey", "recent"],
            )
        ]

        if method_terms:
            tasks.append(
                self._make_query_task(
                    subtask_id="concept_method",
                    concept="方法机制",
                    intent="聚焦检索增强机制、模块设计与方法实现。",
                    base_terms=method_terms[:4],
                    query_types=["core", "recent"],
                )
            )

        if property_terms:
            tasks.append(
                self._make_query_task(
                    subtask_id="concept_property",
                    concept="表征与学习目标",
                    intent="聚焦 representation learning、embedding 和表示质量相关工作。",
                    base_terms=property_terms[:4] + method_terms[:2],
                    query_types=["core", "survey"],
                )
            )

        benchmark_terms = unique_strings(evaluation_terms + method_terms[:2] + property_terms[:2])
        if benchmark_terms:
            tasks.append(
                self._make_query_task(
                    subtask_id="concept_evaluation",
                    concept="评测与基准",
                    intent="定位 benchmark、evaluation 与实验设计相关文献。",
                    base_terms=benchmark_terms[:4],
                    query_types=["benchmark", "recent"],
                )
            )

        return tasks[:5]

    def _llm_query_plan(
        self,
        topic: str,
        seed_plan: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
        if not self.llm.available():
            return None, default_llm_usage()
        seed_payload = [
            {
                "concept": task["concept"],
                "intent": task["intent"],
                "base_terms": task["base_terms"],
                "query_types": task["query_types"],
            }
            for task in seed_plan
        ]
        prompt = (
            "You are helping generate AI/CS literature search plans. "
            "Given a research topic and a rule-based seed plan, refine it into 3-5 concept-first search tasks. "
            "Return JSON only in the form "
            '{"tasks":[{"concept":"...", "intent":"...", "base_terms":["..."], "query_types":["core","survey","recent"]}]}. '
            "Every base_terms item must be concise English academic search terms."
        )
        try:
            payload, usage, _ = self.llm.complete_json(
                stage="screening",
                system_prompt=prompt,
                user_payload={"topic": topic, "seed_plan": seed_payload},
                temperature=0.0,
                max_tokens=900,
            )
        except Exception as exc:  # pragma: no cover - depends on external LLM
            logger.warning("LLM query planning failed: %s", exc)
            return None, default_llm_usage()
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(tasks, list):
            return None, usage

        planned: list[dict[str, Any]] = []
        for index, task in enumerate(tasks, start=1):
            if not isinstance(task, dict):
                continue
            base_terms = [str(item).strip() for item in task.get("base_terms") or [] if str(item).strip()]
            query_types = self._normalize_query_types(task.get("query_types"))
            if not base_terms:
                continue
            planned.append(
                self._make_query_task(
                    subtask_id=f"llm_{index}",
                    concept=str(task.get("concept") or f"概念 {index}").strip(),
                    intent=str(task.get("intent") or "定位相关文献").strip(),
                    base_terms=base_terms[:5],
                    query_types=query_types,
                )
            )
        return planned[:5] or None, usage

    def _should_try_llm(self, topic: str) -> bool:
        return contains_cjk(topic) or len(tokenize(topic)) < 4

    def _detect_terms(self, topic: str) -> list[dict[str, str]]:
        lowered = topic.lower()
        detected: list[dict[str, str]] = []
        for item in TERM_LIBRARY:
            if any(pattern in lowered for pattern in item["patterns"]):
                detected.append(
                    {
                        "canonical": item["canonical"],
                        "label": item["label"],
                        "kind": item["kind"],
                    }
                )
        return detected

    def _make_query_task(
        self,
        *,
        subtask_id: str,
        concept: str,
        intent: str,
        base_terms: list[str],
        query_types: list[str],
    ) -> dict[str, Any]:
        variants = []
        base_query = " ".join(unique_strings(base_terms))
        for query_type in query_types:
            suffix = VARIANT_SUFFIXES.get(query_type, "")
            query_text = " ".join(
                part for part in [base_query, suffix.strip()] if part
            ).strip()
            variants.append(
                {
                    "query_id": f"{subtask_id}_{query_type}",
                    "query_type": query_type,
                    "query_text": query_text,
                    "result_count": 0,
                    "result_budget": 0,
                    "status": "pending",
                    "recall_bucket": "direct_core" if query_type == "core" else "direct_support",
                    "recall_priority": 0.0,
                    "frontier_expansion": None,
                    "parent_subtask_id": None,
                }
            )
        return {
            "subtask_id": subtask_id,
            "concept": concept,
            "intent": intent,
            "base_terms": unique_strings(base_terms),
            "query_types": query_types,
            "variants": variants,
            "result_count": 0,
            "result_budget": 0,
            "status": "pending",
            "recall_bucket": "direct_core" if "core" in query_types else "direct_support",
            "frontier_expansion": None,
            "parent_subtask_id": None,
        }

    @staticmethod
    def _normalize_query_types(value: Any) -> list[str]:
        if not isinstance(value, list):
            return ["core", "recent"]
        normalized = []
        for item in value:
            text = str(item).strip().lower()
            if text in VARIANT_SUFFIXES and text not in normalized:
                normalized.append(text)
        return normalized or ["core", "recent"]

    def _make_frontier_task(
        self,
        *,
        parent_task: dict[str, Any],
        expansion_type: str,
        concept: str,
        intent: str,
        base_terms: list[str],
        query_types: list[str],
    ) -> dict[str, Any]:
        task = self._make_query_task(
            subtask_id=f"{parent_task.get('subtask_id')}_{expansion_type}",
            concept=concept,
            intent=intent,
            base_terms=base_terms,
            query_types=query_types,
        )
        task["frontier_expansion"] = expansion_type
        task["parent_subtask_id"] = parent_task.get("subtask_id")
        task["recall_bucket"] = f"frontier_{expansion_type}"
        for variant in task["variants"]:
            variant["frontier_expansion"] = expansion_type
            variant["parent_subtask_id"] = parent_task.get("subtask_id")
            variant["recall_bucket"] = f"frontier_{expansion_type}"
        return task

    def _adjacent_terms(self, base_terms: list[str]) -> list[str]:
        joined = " ".join(base_terms).lower()
        candidates: list[str] = []
        for canonical, neighbors in FRONTIER_NEIGHBORS.items():
            if canonical in joined:
                candidates.extend(neighbors)
        if not candidates:
            candidates.extend(base_terms[1:3])
        if not candidates:
            candidates.append("related methods")
        return unique_strings(candidates)[:3]

    def _broader_terms(self, topic: str, base_terms: list[str]) -> list[str]:
        topic_terms = unique_strings(tokenize(topic))
        broader = [*base_terms[:2], *topic_terms[:2], "survey", "review"]
        return unique_strings(broader)[:4]

    def _build_arxiv_query(self, query: str) -> str:
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9._+\-]*", query)
        if not tokens:
            return ""
        if len(tokens) <= 2:
            return quote_plus(f'all:"{" ".join(tokens)}"')

        phrase_terms = tokens[:3]
        trailing_terms = [token for token in tokens[3:] if token]
        parts = [f'all:"{" ".join(phrase_terms)}"']
        parts.extend(f"all:{token}" for token in trailing_terms[:3])
        return quote_plus(" AND ".join(parts))

    def _dedupe(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        title_index: dict[str, str] = {}
        for paper in papers:
            title = str(paper.get("title") or "").strip()
            if not title:
                continue
            key = paper_key(paper)
            title_key = normalize_title(title)
            existing_key = title_index.get(title_key)
            if existing_key:
                key = existing_key
            if key not in merged:
                merged[key] = paper
                title_index[title_key] = key
                continue
            merged[key] = self._merge_paper(merged[key], paper)
        return list(merged.values())

    def _normalize_paper(self, paper: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(paper)
        normalized["title"] = str(normalized.get("title") or "Untitled").strip()
        normalized["abstract"] = re.sub(r"\s+", " ", str(normalized.get("abstract") or "")).strip()
        normalized["authors"] = [
            str(author).strip()
            for author in normalized.get("authors") or []
            if str(author).strip()
        ]
        normalized["year"] = self._safe_int(normalized.get("year"))
        normalized["citation_count"] = self._safe_int(normalized.get("citation_count")) or 0
        normalized["query_matches"] = self._merge_query_matches(
            normalized.get("query_matches") or [],
            [],
        )
        sources = {
            item.strip()
            for item in str(normalized.get("source") or "unknown").split("+")
            if item.strip()
        }
        normalized["source"] = "+".join(sorted(sources)) or "unknown"
        return normalized

    def _recall_priority_key(self, paper: dict[str, Any]) -> tuple[float, ...]:
        match_profile = self._paper_match_profile(paper)
        citation_signal = math.log10((paper.get("citation_count") or 0) + 1)
        year = paper.get("year") or 0
        source_count = len(
            [item for item in str(paper.get("source") or "").split("+") if item]
        )
        return (
            match_profile["direct_core_hits"],
            match_profile["direct_hits"],
            match_profile["query_overlap"],
            match_profile["title_query_overlap"],
            1 if not match_profile["frontier_only"] else 0,
            0 if match_profile["drift_flag"] else 1,
            match_profile["unique_subtasks"],
            match_profile["unique_sources"],
            source_count,
            match_profile["frontier_hits"],
            citation_signal,
            year,
        )

    def _merge_paper(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        result = dict(left)
        for key in (
            "abstract",
            "doi",
            "arxiv_id",
            "semantic_scholar_id",
            "openalex_id",
            "url",
            "pdf_url",
            "venue",
        ):
            if not result.get(key) and right.get(key):
                result[key] = right[key]
        result["citation_count"] = max(
            int(result.get("citation_count") or 0),
            int(right.get("citation_count") or 0),
        )
        sources = {
            item for item in str(result.get("source") or "").split("+") if item
        }
        sources.update(
            item for item in str(right.get("source") or "").split("+") if item
        )
        result["source"] = "+".join(sorted(sources))
        if not result.get("authors") and right.get("authors"):
            result["authors"] = right["authors"]
        result["query_matches"] = self._merge_query_matches(
            result.get("query_matches") or [],
            right.get("query_matches") or [],
        )
        return result

    def _merge_source_status(self, left: str | None, right: str | None) -> str:
        if not left:
            return right or "idle"
        if not right:
            return left
        if left == right:
            return left
        if left.startswith("skipped") and right.startswith("skipped"):
            return left
        if left.startswith("skipped"):
            return right if right in {"ok", "partial_failure"} else "partial_failure"
        if right.startswith("skipped"):
            return left if left in {"ok", "partial_failure"} else "partial_failure"
        pair = {left, right}
        if "partial_failure" in pair:
            return "partial_failure"
        if pair == {"ok", "failed"}:
            return "partial_failure"
        if "ok" in pair:
            return "ok"
        if "failed" in pair:
            return "failed"
        if "idle" in pair:
            return right if left == "idle" else left
        return right

    @staticmethod
    def _empty_source_contribution(*, status: str = "idle") -> dict[str, Any]:
        return {
            "status": status,
            "raw_hits": 0,
            "deduped_hits": 0,
            "top_pool_hits": 0,
            "selected_hits": 0,
            "direct_top_hits": 0,
            "frontier_top_hits": 0,
        }

    def _ensure_source_contribution(
        self,
        summary: dict[str, dict[str, Any]],
        source_name: str,
    ) -> dict[str, Any]:
        summary.setdefault(source_name, self._empty_source_contribution())
        return summary[source_name]

    @staticmethod
    def _paper_sources(paper: dict[str, Any]) -> set[str]:
        sources = {
            item.strip()
            for item in str(paper.get("source") or "").split("+")
            if item.strip()
        }
        for match in paper.get("query_matches") or []:
            source_name = str(match.get("source") or "").strip()
            if source_name:
                sources.add(source_name)
        return sources

    @staticmethod
    def _direct_task_ids(query_tasks: list[dict[str, Any]]) -> set[str]:
        return {
            str(task.get("subtask_id"))
            for task in query_tasks
            if isinstance(task, dict)
            and task.get("subtask_id")
            and not task.get("frontier_expansion")
            and (
                "core" in (task.get("query_types") or [])
                or any(
                    variant.get("query_type") == "core"
                    for variant in task.get("variants") or []
                    if isinstance(variant, dict)
                )
            )
        }

    def _topic_token_set(
        self,
        topic: str,
        query_tasks: list[dict[str, Any]],
    ) -> set[str]:
        tokens = tokenize(topic)
        for task in query_tasks:
            if not isinstance(task, dict) or task.get("frontier_expansion"):
                continue
            tokens.extend(
                tokenize(" ".join(str(item) for item in task.get("base_terms") or []))
            )
        return set(tokens)

    @staticmethod
    def _paper_topic_profile(
        paper: dict[str, Any],
        topic_tokens: set[str],
    ) -> dict[str, float]:
        title_tokens = set(tokenize(str(paper.get("title") or "")))
        paper_tokens = set(
            tokenize(
                f"{paper.get('title') or ''} {paper.get('abstract') or ''}"
            )
        )
        if not topic_tokens:
            return {
                "topic_overlap": 0.0,
                "title_overlap": 0.0,
            }
        return {
            "topic_overlap": len(paper_tokens & topic_tokens) / max(1, len(topic_tokens)),
            "title_overlap": len(title_tokens & topic_tokens) / max(1, len(topic_tokens)),
        }

    def _paper_match_profile(self, paper: dict[str, Any]) -> dict[str, Any]:
        query_matches = self._merge_query_matches(paper.get("query_matches") or [], [])
        paper_tokens = set(
            tokenize(
                f"{paper.get('title') or ''} {paper.get('abstract') or ''}"
            )
        )
        title_tokens = set(tokenize(str(paper.get("title") or "")))
        query_tokens = set(
            tokenize(
                " ".join(
                    " ".join(
                        part
                        for part in (
                            str(match.get("query_text") or "").strip(),
                            str(match.get("concept") or "").strip(),
                        )
                        if part
                    )
                    for match in query_matches
                )
            )
        )
        direct_matches = [
            match
            for match in query_matches
            if not match.get("frontier_expansion")
        ]
        direct_core_matches = [
            match
            for match in direct_matches
            if match.get("query_type") == "core"
        ]
        frontier_matches = [
            match
            for match in query_matches
            if match.get("frontier_expansion")
        ]
        direct_sources = {
            str(match.get("source")).strip()
            for match in direct_matches
            if str(match.get("source") or "").strip()
        }
        frontier_sources = {
            str(match.get("source")).strip()
            for match in frontier_matches
            if str(match.get("source") or "").strip()
        }
        query_overlap = (
            len(paper_tokens & query_tokens) / max(1, len(query_tokens))
            if query_tokens
            else 0.0
        )
        title_query_overlap = (
            len(title_tokens & query_tokens) / max(1, len(query_tokens))
            if query_tokens
            else 0.0
        )
        frontier_only = bool(frontier_matches) and not direct_matches
        drift_flag = (
            frontier_only
            and query_overlap < 0.10
            and title_query_overlap < 0.06
        ) or (not query_matches)
        return {
            "query_matches": query_matches,
            "direct_matches": direct_matches,
            "direct_core_matches": direct_core_matches,
            "frontier_matches": frontier_matches,
            "direct_hits": len(direct_matches),
            "direct_core_hits": len(direct_core_matches),
            "frontier_hits": len(frontier_matches),
            "frontier_only": frontier_only,
            "direct_sources": direct_sources,
            "frontier_sources": frontier_sources,
            "query_overlap": round(query_overlap, 3),
            "title_query_overlap": round(title_query_overlap, 3),
            "unique_subtasks": len(
                {
                    str(item.get("subtask_id"))
                    for item in query_matches
                    if item.get("subtask_id")
                }
            ),
            "unique_sources": len(
                {str(item.get("source")) for item in query_matches if item.get("source")}
            ),
            "drift_flag": drift_flag,
        }

    @staticmethod
    def _merge_query_matches(
        left: list[dict[str, Any]],
        right: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in left + right:
            if not isinstance(item, dict):
                continue
            normalized = ScholarlySearchService._normalize_query_match(item)
            key = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
        return merged

    @staticmethod
    def _normalize_query_match(item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        for key in ("subtask_id", "concept", "intent", "query_type", "query_text", "source"):
            value = normalized.get(key)
            normalized[key] = str(value).strip() if value is not None else ""
        for key in ("frontier_expansion", "parent_subtask_id"):
            value = normalized.get(key)
            normalized[key] = str(value).strip() if value not in {None, ""} else None
        return normalized

    def _finalize_source_statuses(
        self,
        initial_statuses: dict[str, str],
        counters: dict[str, dict[str, int]],
    ) -> dict[str, str]:
        statuses = dict(initial_statuses)
        for source_name, counter in counters.items():
            if statuses.get(source_name, "").startswith("skipped"):
                continue
            attempted = counter["attempted"]
            succeeded = counter["succeeded"]
            failed = counter["failed"]
            if attempted == 0:
                statuses[source_name] = "idle"
            elif succeeded and failed:
                statuses[source_name] = "partial_failure"
            elif succeeded:
                statuses[source_name] = "ok"
            else:
                statuses[source_name] = "failed"
        return statuses

    @staticmethod
    def _build_source_notices(source_statuses: dict[str, str]) -> list[str]:
        notices: list[str] = []
        for source_name, status in source_statuses.items():
            label = {
                "openalex": "OpenAlex",
                "arxiv": "arXiv",
                "semantic_scholar": "Semantic Scholar",
            }.get(source_name, source_name)
            if status == "skipped_missing_api_key":
                notices.append(f"{label} 已跳过：缺少 API key。")
            elif status == "failed":
                notices.append(f"{label} 当前检索失败，已降级到其他数据源。")
            elif status == "partial_failure":
                notices.append(f"{label} 部分查询失败，结果已降级。")
        return notices

    @staticmethod
    def _variant_status(variant: dict[str, Any]) -> str:
        if variant.get("sources_succeeded") and variant.get("sources_failed"):
            return "partial"
        if variant.get("sources_succeeded"):
            return "ok"
        if variant.get("sources_failed"):
            return "failed"
        if variant.get("sources_skipped"):
            return "skipped"
        return "idle"

    @staticmethod
    def _summarize_variant_statuses(statuses: list[str]) -> str:
        unique = set(statuses)
        if "ok" in unique and len(unique) == 1:
            return "ok"
        if "partial" in unique or ("ok" in unique and "failed" in unique):
            return "partial"
        if "ok" in unique:
            return "ok"
        if "failed" in unique:
            return "failed"
        if "skipped" in unique:
            return "skipped"
        return "idle"

    @staticmethod
    def _format_request_error(exc: requests.RequestException) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            return f"http_{response.status_code}"
        return exc.__class__.__name__.lower()

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | list[Any] | None:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _text(node: ET.Element | None) -> str:
        if node is None or node.text is None:
            return ""
        return html.unescape(re.sub(r"\s+", " ", node.text)).strip()

    @staticmethod
    def _year(value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r"\d{4}", value)
        return int(match.group(0)) if match else None

    @staticmethod
    def _clean_doi(value: str | None) -> str | None:
        if not value:
            return None
        return value.replace("https://doi.org/", "").strip()

    @staticmethod
    def _openalex_abstract(index: dict[str, list[int]] | None) -> str:
        if not index:
            return ""
        words: list[tuple[int, str]] = []
        for word, positions in index.items():
            for position in positions:
                words.append((position, word))
        return " ".join(word for _, word in sorted(words))

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
