# ruff: noqa: E402,D103

"""Offline regression metrics for scholarly retrieval and reranking."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import Configuration
from services.scholarly_rerank import ScholarlyScreeningService
from services.scholarly_search import ScholarlySearchService
from services.scholarly_store import normalize_title


def load_samples() -> list[dict[str, Any]]:
    benchmark_path = (
        Path(__file__).resolve().parent / "benchmarks" / "scholarly_retrieval_sample.json"
    )
    return json.loads(benchmark_path.read_text(encoding="utf-8"))


def recall_at_k(titles: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for title in titles[:k] if title in relevant)
    return hits / len(relevant)


def ndcg_at_k(titles: list[str], gains: dict[str, int], k: int) -> float:
    def dcg(items: list[str]) -> float:
        score = 0.0
        for index, title in enumerate(items[:k], start=1):
            gain = gains.get(title, 0)
            if gain:
                score += gain / math.log2(index + 1)
        return score

    ideal_titles = [
        title
        for title, _ in sorted(gains.items(), key=lambda item: item[1], reverse=True)
    ]
    actual = dcg(titles)
    ideal = dcg(ideal_titles)
    return actual / ideal if ideal else 0.0


def frontier_contribution_quality(
    papers: list[dict[str, Any]],
    relevant: set[str],
    *,
    k: int = 20,
) -> float:
    frontier_titles = [
        normalize_title(str(paper.get("title") or ""))
        for paper in papers[:k]
        if any(
            match.get("frontier_expansion")
            for match in paper.get("query_matches") or []
        )
    ]
    if not frontier_titles:
        return 0.0
    hits = sum(1 for title in frontier_titles if title in relevant)
    return hits / len(frontier_titles)


def evaluate_sample(
    sample: dict[str, Any],
    search: ScholarlySearchService,
    screening: ScholarlyScreeningService,
) -> dict[str, Any]:
    topic = sample["topic"]
    category = str(sample.get("category") or "uncategorized")
    query_tasks = sample.get("query_tasks") or []
    deduped = search.dedupe_and_normalize(sample.get("papers") or [], limit=50)
    coarse = screening.coarse_rerank(topic, deduped, query_tasks, limit=50)
    decision = screening.frontier_decision(topic, coarse, query_tasks)
    final_ranked = screening.finalize_rerank(topic, coarse, query_tasks, limit=50)

    titles = [normalize_title(str(paper.get("title") or "")) for paper in final_ranked]
    gains: dict[str, int] = {}
    for title in sample.get("must_include_titles") or []:
        gains[normalize_title(title)] = 3
    for title in sample.get("acceptable_titles") or []:
        gains.setdefault(normalize_title(title), 1)

    relevant = set(gains)
    frontier_expected = bool(sample.get("frontier_expected"))
    recall_20 = round(recall_at_k(titles, relevant, 20), 3)
    pool_metrics = search.candidate_pool_metrics(
        topic,
        final_ranked,
        query_tasks,
        selected_papers=[paper for paper in final_ranked if paper.get("selected")],
        limit=20,
    )
    source_contributions = search.source_contribution_summary(
        sample.get("papers") or [],
        deduped,
        final_ranked[:20],
        [paper for paper in final_ranked if paper.get("selected")],
    )
    metrics = {
        "topic": topic,
        "category": category,
        "frontier_mode": bool(decision["frontier_mode"]),
        "frontier_reason": decision["frontier_reason"],
        "frontier_expected": frontier_expected,
        "frontier_expected_hit": frontier_expected and bool(decision["frontier_mode"]),
        "recall@20": recall_20,
        "recall@50": round(recall_at_k(titles, relevant, 50), 3),
        "ndcg@20": round(ndcg_at_k(titles, gains, 20), 3),
        "candidate_pool_purity": pool_metrics["candidate_pool_purity"],
        "candidate_drift_score": pool_metrics["candidate_drift_score"],
        "direct_hit_coverage": pool_metrics["direct_hit_coverage"],
        "frontier_contribution_rate": pool_metrics["frontier_contribution_rate"],
        "frontier_contribution_quality": round(
            frontier_contribution_quality(final_ranked, relevant),
            3,
        ),
        "source_contributions": source_contributions,
    }
    metrics["frontier_hit_recall@20"] = (
        recall_20 if metrics["frontier_expected_hit"] else 0.0
    )
    return metrics


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    frontier_expected = [result for result in results if result["frontier_expected"]]
    frontier_triggered = [result for result in results if result["frontier_mode"]]
    categories = sorted({str(result.get("category") or "uncategorized") for result in results})
    category_summary: dict[str, Any] = {}
    for category in categories:
        bucket = [result for result in results if result.get("category") == category]
        category_summary[category] = {
            "sample_count": len(bucket),
            "Recall@20": round(
                sum(result["recall@20"] for result in bucket) / max(1, len(bucket)),
                3,
            ),
            "nDCG@20": round(
                sum(result["ndcg@20"] for result in bucket) / max(1, len(bucket)),
                3,
            ),
            "CandidatePoolPurity@20": round(
                sum(result["candidate_pool_purity"] for result in bucket)
                / max(1, len(bucket)),
                3,
            ),
            "CandidateDrift@20": round(
                sum(result["candidate_drift_score"] for result in bucket)
                / max(1, len(bucket)),
                3,
            ),
        }

    source_names = sorted(
        {
            source_name
            for result in results
            for source_name in result.get("source_contributions", {})
        }
    )
    source_summary = {}
    for source_name in source_names:
        totals = {
            "avg_raw_hits": 0.0,
            "avg_top_pool_hits": 0.0,
            "avg_selected_hits": 0.0,
            "avg_direct_top_hits": 0.0,
            "avg_frontier_top_hits": 0.0,
        }
        for result in results:
            payload = result.get("source_contributions", {}).get(source_name, {})
            totals["avg_raw_hits"] += float(payload.get("raw_hits") or 0)
            totals["avg_top_pool_hits"] += float(payload.get("top_pool_hits") or 0)
            totals["avg_selected_hits"] += float(payload.get("selected_hits") or 0)
            totals["avg_direct_top_hits"] += float(payload.get("direct_top_hits") or 0)
            totals["avg_frontier_top_hits"] += float(payload.get("frontier_top_hits") or 0)
        source_summary[source_name] = {
            key: round(value / max(1, len(results)), 3)
            for key, value in totals.items()
        }

    return {
        "sample_count": len(results),
        "Recall@20": round(
            sum(result["recall@20"] for result in results) / max(1, len(results)),
            3,
        ),
        "Recall@50": round(
            sum(result["recall@50"] for result in results) / max(1, len(results)),
            3,
        ),
        "nDCG@20": round(
            sum(result["ndcg@20"] for result in results) / max(1, len(results)),
            3,
        ),
        "FrontierTriggerRate": round(
            len(frontier_triggered) / max(1, len(results)),
            3,
        ),
        "FrontierExpectedHitRate": round(
            sum(1 for result in frontier_expected if result["frontier_mode"])
            / max(1, len(frontier_expected)),
            3,
        ),
        "FrontierHitRecall@20": round(
            sum(result["frontier_hit_recall@20"] for result in frontier_expected)
            / max(1, len(frontier_expected)),
            3,
        ),
        "CandidatePoolPurity@20": round(
            sum(result["candidate_pool_purity"] for result in results)
            / max(1, len(results)),
            3,
        ),
        "CandidateDrift@20": round(
            sum(result["candidate_drift_score"] for result in results)
            / max(1, len(results)),
            3,
        ),
        "DirectHitCoverage": round(
            sum(result["direct_hit_coverage"] for result in results)
            / max(1, len(results)),
            3,
        ),
        "FrontierContributionRate@20": round(
            sum(result["frontier_contribution_rate"] for result in results)
            / max(1, len(results)),
            3,
        ),
        "FrontierContributionQuality@20": round(
            sum(result["frontier_contribution_quality"] for result in results)
            / max(1, len(results)),
            3,
        ),
        "CategorySummary": category_summary,
        "SourceContributionSummary": source_summary,
    }


def main() -> None:
    config = Configuration.from_env(
        overrides={
            "scholarly_candidate_limit": 50,
            "scholarly_selection_limit": 20,
        }
    )
    search = ScholarlySearchService(config)
    screening = ScholarlyScreeningService(config)
    samples = load_samples()
    results = [evaluate_sample(sample, search, screening) for sample in samples]

    sys.stdout.write(
        json.dumps(
            {"summary": summarize(results), "samples": results},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
