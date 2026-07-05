# ruff: noqa: D202,D107

"""Transparent reranking utilities for scholarly candidate papers."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from config import Configuration
from services.scholarly_search import tokenize, unique_strings
from services.scholarly_store import paper_key


class ScholarlyScreeningService:
    """Rank recalled papers and select a compact review set."""

    def __init__(self, config: Configuration) -> None:
        self.config = config
        self.current_year = datetime.now().year

    def screen(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        query_tasks: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run the coarse->final ranking chain with backward-compatible fields."""

        coarse_ranked = self.coarse_rerank(
            topic,
            papers,
            query_tasks,
            limit=self.config.scholarly_candidate_limit,
        )
        return self.finalize_rerank(
            topic,
            coarse_ranked,
            query_tasks,
            limit=self.config.scholarly_candidate_limit,
        )

    def coarse_rerank(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        query_tasks: list[dict[str, Any]] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Compute transparent feature scores for the top-50 candidate pool."""

        target = limit or self.config.scholarly_candidate_limit
        topic_tokens = self._topic_tokens(topic, query_tasks or [])
        scored = [self._score_paper(paper, topic_tokens) for paper in papers]
        scored.sort(
            key=lambda item: (
                item["coarse_score"],
                item["relevance_score"],
                item["query_match_score"],
                item.get("year") or 0,
            ),
            reverse=True,
        )
        trimmed = scored[:target]
        for index, item in enumerate(trimmed, start=1):
            item["coarse_rank"] = index
        return trimmed

    def frontier_decision(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        query_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Decide whether fallback expansion is needed for sparse frontier topics."""

        del topic
        query_tasks = query_tasks or []
        top_slice = papers[: min(len(papers), max(10, self.config.scholarly_selection_limit))]
        if not top_slice:
            return {
                "frontier_mode": True,
                "frontier_reason": "empty_candidate_pool",
                "metrics": {
                    "high_relevance_count": 0,
                    "strict_relevance_count": 0,
                    "average_top_coarse_score": 0.0,
                    "core_task_hits": 0,
                    "core_task_total": 0,
                    "direct_hit_coverage": 0.0,
                },
            }

        high_relevance = [
            paper
            for paper in top_slice
            if paper.get("relevance_score", 0.0) >= 0.30
            or paper.get("coarse_score", 0.0) >= 0.46
        ]
        strict_relevance = [
            paper
            for paper in top_slice
            if self._label(
                float(paper.get("relevance_score") or 0.0),
                float(paper.get("coarse_score") or 0.0),
            )
            in {"must_read", "frontier"}
        ]
        average_top_coarse = sum(
            float(paper.get("coarse_score") or 0.0) for paper in top_slice
        ) / max(1, len(top_slice))
        core_task_ids = {
            str(task.get("subtask_id"))
            for task in query_tasks
            if task.get("subtask_id")
            and (
                "core" in (task.get("query_types") or [])
                or any(
                    variant.get("query_type") == "core"
                    for variant in task.get("variants") or []
                )
            )
        }
        core_hits = {
            str(match.get("subtask_id"))
            for paper in top_slice
            for match in paper.get("query_matches") or []
            if match.get("subtask_id") in core_task_ids and not match.get("frontier_expansion")
        }
        min_high_relevance = max(2, min(5, math.ceil(len(top_slice) * 0.35)))

        reasons: list[str] = []
        if len(high_relevance) < min_high_relevance:
            reasons.append("high_relevance_sparse")
        if average_top_coarse < 0.38:
            reasons.append("low_average_coarse_score")
        if core_task_ids and len(core_hits) < max(1, min(2, len(core_task_ids))):
            reasons.append("weak_core_query_hits")

        return {
            "frontier_mode": bool(reasons),
            "frontier_reason": ", ".join(reasons) or None,
            "metrics": {
                "high_relevance_count": len(high_relevance),
                "strict_relevance_count": len(strict_relevance),
                "average_top_coarse_score": round(average_top_coarse, 3),
                "core_task_hits": len(core_hits),
                "core_task_total": len(core_task_ids),
                "direct_hit_coverage": round(
                    len(core_hits) / max(1, len(core_task_ids)),
                    3,
                ),
            },
        }

    def finalize_rerank(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        query_tasks: list[dict[str, Any]] | None = None,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Produce the final rank order and default top-20 selection set."""

        target = limit or self.config.scholarly_candidate_limit
        if papers and "coarse_score" not in papers[0]:
            finalists = self.coarse_rerank(topic, papers, query_tasks, limit=target)
        else:
            finalists = [dict(item) for item in papers[:target]]

        for item in finalists:
            relevance = float(item.get("relevance_score") or 0.0)
            novelty = float(
                item.get("freshness_score")
                or item.get("novelty_score")
                or self._novelty_score(item.get("year"))
            )
            citation = float(
                item.get("citation_score")
                or min(0.12, math.log10((item.get("citation_count") or 0) + 1) / 12)
            )
            query_match_score = float(
                item.get("query_match_score")
                or self._query_match_bonus(item.get("query_matches") or [])
            )
            recall_score = float(
                item.get("recall_score")
                or min(1.0, relevance * 0.35 + query_match_score * 1.9 + citation)
            )
            frontier_penalty = 0.04 if item.get("frontier_only") else 0.0
            final = max(
                0.0,
                min(
                    1.0,
                    relevance * 0.60
                    + query_match_score
                    + novelty * 0.10
                    + citation
                    + min(0.12, recall_score * 0.18)
                    - frontier_penalty,
                ),
            )
            label = self._label(relevance, final)
            if item.get("frontier_only") and label == "must_read" and relevance < 0.56:
                label = "frontier"
            tags = self._tags(item, relevance, novelty, item.get("query_matches") or [])
            reason = self._reason(
                item,
                relevance,
                novelty,
                label,
                item.get("query_matches") or [],
            )
            item.update(
                {
                    "relevance_score": round(relevance, 3),
                    "novelty_score": round(novelty, 3),
                    "freshness_score": round(novelty, 3),
                    "citation_score": round(citation, 3),
                    "query_match_score": round(query_match_score, 3),
                    "recall_score": round(recall_score, 3),
                    "final_score": round(final, 3),
                    "relevance_label": label,
                    "ai_reason": reason,
                    "tags": tags,
                }
            )

        finalists.sort(
            key=lambda item: (
                item["final_score"],
                item.get("coarse_score") or 0.0,
                item.get("year") or 0,
            ),
            reverse=True,
        )
        selected_limit = self.config.scholarly_selection_limit
        strict = [
            item
            for item in finalists
            if item["relevance_label"] in {"must_read", "frontier"}
        ]
        if len(strict) >= selected_limit:
            selected_keys = {paper_key(item) for item in strict[:selected_limit]}
        else:
            selected_keys = {paper_key(item) for item in finalists[:selected_limit]}

        for rank, item in enumerate(finalists, start=1):
            item["rank"] = rank
            item["selected"] = paper_key(item) in selected_keys
            item["user_status"] = "included" if item["selected"] else "candidate"
            if item["selected"] and item["relevance_label"] == "candidate":
                item["relevance_label"] = "adjacent"
                item["tags"] = sorted(set(item["tags"] + ["旁支补充"]))
        return finalists

    def _topic_tokens(
        self,
        topic: str,
        query_tasks: list[dict[str, Any]],
    ) -> Counter[str]:
        return Counter(
            tokenize(
                " ".join(
                    [
                        topic,
                        *[
                            " ".join(task.get("base_terms") or [])
                            for task in query_tasks
                            if isinstance(task, dict)
                        ],
                    ]
                )
            )
        )

    def _score_paper(
        self,
        paper: dict[str, Any],
        topic_tokens: Counter[str],
    ) -> dict[str, Any]:
        title = str(paper.get("title") or "")
        abstract = str(paper.get("abstract") or "")
        query_matches = paper.get("query_matches") or []
        combined_tokens = Counter(tokenize(f"{title} {abstract}"))
        overlap = sum(
            min(count, combined_tokens[token])
            for token, count in topic_tokens.items()
        )
        relevance = overlap / max(1, len(topic_tokens))
        title_tokens = tokenize(title)
        title_overlap = sum(1 for token in topic_tokens if token in title_tokens)
        relevance += min(0.22, title_overlap * 0.04)

        query_match_score = self._query_match_bonus(query_matches)
        freshness = self._novelty_score(paper.get("year"))
        citation_score = min(
            0.12,
            math.log10((paper.get("citation_count") or 0) + 1) / 12,
        )
        source_count = len(
            [item for item in str(paper.get("source") or "").split("+") if item]
        )
        source_bonus = min(0.10, source_count * 0.02)
        frontier_hits = [
            item for item in query_matches if item.get("frontier_expansion")
        ]
        frontier_only = bool(frontier_hits) and len(frontier_hits) == len(query_matches)
        frontier_penalty = 0.04 if frontier_only else 0.0
        recall_score = min(
            1.0,
            relevance * 0.35
            + query_match_score * 1.9
            + freshness * 0.10
            + citation_score
            + source_bonus,
        )
        coarse_score = max(
            0.0,
            min(
                1.0,
                relevance * 0.58
                + query_match_score
                + freshness * 0.08
                + citation_score
                + source_bonus
                - frontier_penalty / 2,
            ),
        )
        item = dict(paper)
        item.update(
            {
                "relevance_score": round(relevance, 3),
                "novelty_score": round(freshness, 3),
                "freshness_score": round(freshness, 3),
                "citation_score": round(citation_score, 3),
                "query_match_score": round(query_match_score, 3),
                "recall_score": round(recall_score, 3),
                "coarse_score": round(coarse_score, 3),
                "frontier_only": frontier_only,
                "frontier_hit_count": len(frontier_hits),
            }
        )
        return item

    def _query_match_bonus(self, query_matches: list[dict[str, Any]]) -> float:
        if not query_matches:
            return 0.0
        unique_subtasks = len(
            {str(item.get("subtask_id")) for item in query_matches if item.get("subtask_id")}
        )
        unique_sources = len(
            {str(item.get("source")) for item in query_matches if item.get("source")}
        )
        core_hits = sum(
            1 for item in query_matches if item.get("query_type") == "core"
        )
        return min(
            0.24,
            unique_subtasks * 0.04 + unique_sources * 0.03 + core_hits * 0.02,
        )

    def _novelty_score(self, year: Any) -> float:
        try:
            value = int(year)
        except (TypeError, ValueError):
            return 0.18
        age = max(0, self.current_year - value)
        if age <= 1:
            return 1.0
        if age <= 3:
            return 0.76
        if age <= 5:
            return 0.52
        if age <= 10:
            return 0.28
        return 0.16

    @staticmethod
    def _label(relevance: float, final: float) -> str:
        if relevance >= 0.50 and final >= 0.58:
            return "must_read"
        if relevance >= 0.30 or final >= 0.46:
            return "frontier"
        if relevance >= 0.18:
            return "background"
        return "candidate"

    def _tags(
        self,
        paper: dict[str, Any],
        relevance: float,
        novelty: float,
        query_matches: list[dict[str, Any]],
    ) -> list[str]:
        tags: list[str] = []
        if relevance >= 0.45:
            tags.append("高相关")
        if novelty >= 0.75:
            tags.append("前沿")
        if (paper.get("citation_count") or 0) >= 100:
            tags.append("高引用")
        if "arxiv" in str(paper.get("source") or ""):
            tags.append("预印本")
        concepts = unique_strings(
            [str(item.get("concept") or "") for item in query_matches]
        )
        tags.extend(concepts[:2])
        return unique_strings(tags or ["候选"])

    @staticmethod
    def _reason(
        paper: dict[str, Any],
        relevance: float,
        novelty: float,
        label: str,
        query_matches: list[dict[str, Any]],
    ) -> str:
        title = str(paper.get("title") or "该论文")
        year = paper.get("year") or "未知年份"
        concepts = unique_strings(
            [str(item.get("concept") or "") for item in query_matches]
        )
        concept_text = f"命中子任务：{', '.join(concepts[:2])}。" if concepts else ""
        label_text = {
            "must_read": "与当前问题高度贴合，可作为核心阅读对象。",
            "frontier": "与主题相关且带有较强的新近性信号。",
            "background": "适合作为背景或技术脉络补充。",
            "candidate": "直接相关性有限，暂作为候选材料。",
        }.get(label, "可作为候选材料。")
        return (
            f"{title}（{year}）。{label_text}{concept_text}"
            f"相关性 {relevance:.2f}，前沿度 {novelty:.2f}。"
        )
