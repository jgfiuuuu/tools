# ruff: noqa: D202

"""Stable metadata and metrics contracts for scholarly workflows."""

from __future__ import annotations

from typing import Any

WORKFLOW_METRIC_DEFAULTS: dict[str, int | float] = {
    "raw_paper_count": 0,
    "deduped_paper_count": 0,
    "coarse_candidate_count": 0,
    "final_candidate_count": 0,
    "selected_count": 0,
    "high_relevance_count": 0,
    "strict_relevance_count": 0,
    "average_top_coarse_score": 0.0,
    "core_task_hits": 0,
    "core_task_total": 0,
    "direct_query_count": 0,
    "direct_core_query_count": 0,
    "frontier_query_count": 0,
    "frontier_adjacent_query_count": 0,
    "frontier_broader_query_count": 0,
    "frontier_recent_query_count": 0,
    "frontier_added_raw_count": 0,
    "candidate_pool_purity": 0.0,
    "candidate_drift_score": 0.0,
    "direct_hit_coverage": 0.0,
    "frontier_contribution_rate": 0.0,
    "frontier_selected_count": 0,
    "dedupe_ratio": 0.0,
}


def default_workflow_metrics(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the stable scholarly workflow metrics map."""

    metrics: dict[str, Any] = dict(WORKFLOW_METRIC_DEFAULTS)
    if not isinstance(overrides, dict):
        return metrics

    for key in WORKFLOW_METRIC_DEFAULTS:
        value = overrides.get(key)
        if value is None:
            continue
        metrics[key] = value
    return metrics


def default_session_metadata(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return normalized scholarly session metadata with stable keys."""

    normalized = dict(overrides) if isinstance(overrides, dict) else {}
    source_statuses = normalized.get("source_statuses")
    skipped_sources = normalized.get("skipped_sources")
    degradation_notices = normalized.get("degradation_notices")
    frontier_reason = normalized.get("frontier_reason")

    normalized["source_statuses"] = (
        dict(source_statuses) if isinstance(source_statuses, dict) else {}
    )
    normalized["skipped_sources"] = (
        list(skipped_sources) if isinstance(skipped_sources, list) else []
    )
    normalized["degradation_notices"] = (
        list(degradation_notices) if isinstance(degradation_notices, list) else []
    )
    normalized["frontier_mode"] = bool(normalized.get("frontier_mode"))
    normalized["frontier_reason"] = (
        frontier_reason if isinstance(frontier_reason, str) else None
    )
    normalized["metrics"] = default_workflow_metrics(normalized.get("metrics"))
    normalized["source_contributions"] = (
        dict(normalized.get("source_contributions"))
        if isinstance(normalized.get("source_contributions"), dict)
        else {}
    )
    return normalized
