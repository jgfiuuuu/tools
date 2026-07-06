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

LLM_USAGE_STAGES: tuple[str, ...] = (
    "screening",
    "paper_card_extraction",
    "report_synthesis",
)


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


def default_llm_usage(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the stable LLM usage map for a scholarly session."""

    normalized = dict(overrides) if isinstance(overrides, dict) else {}
    by_stage = normalized.get("by_stage")
    stage_map: dict[str, Any] = {}
    if isinstance(by_stage, dict):
        for stage in LLM_USAGE_STAGES:
            payload = by_stage.get(stage)
            stage_map[stage] = {
                "input_tokens": int(payload.get("input_tokens") or 0)
                if isinstance(payload, dict)
                else 0,
                "output_tokens": int(payload.get("output_tokens") or 0)
                if isinstance(payload, dict)
                else 0,
                "total_tokens": int(payload.get("total_tokens") or 0)
                if isinstance(payload, dict)
                else 0,
            }
    else:
        for stage in LLM_USAGE_STAGES:
            stage_map[stage] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

    return {
        "input_tokens": int(normalized.get("input_tokens") or 0),
        "output_tokens": int(normalized.get("output_tokens") or 0),
        "total_tokens": int(normalized.get("total_tokens") or 0),
        "by_stage": stage_map,
    }


def merge_llm_usage(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    """Merge one or more usage payloads into the stable contract shape."""

    merged = default_llm_usage()
    for payload in payloads:
        normalized = default_llm_usage(payload)
        merged["input_tokens"] += int(normalized["input_tokens"])
        merged["output_tokens"] += int(normalized["output_tokens"])
        merged["total_tokens"] += int(normalized["total_tokens"])
        for stage in LLM_USAGE_STAGES:
            merged["by_stage"][stage]["input_tokens"] += int(
                normalized["by_stage"][stage]["input_tokens"]
            )
            merged["by_stage"][stage]["output_tokens"] += int(
                normalized["by_stage"][stage]["output_tokens"]
            )
            merged["by_stage"][stage]["total_tokens"] += int(
                normalized["by_stage"][stage]["total_tokens"]
            )
    return merged


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
    normalized["report_context"] = (
        dict(normalized.get("report_context"))
        if isinstance(normalized.get("report_context"), dict)
        else {}
    )
    normalized["llm_usage"] = default_llm_usage(normalized.get("llm_usage"))
    report_artifacts = normalized.get("report_artifacts")
    if isinstance(report_artifacts, dict):
        evidence_buckets = report_artifacts.get("evidence_buckets")
        normalized["report_artifacts"] = {
            "tasks": [
                {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "intent": task.get("intent"),
                    "summary": task.get("summary"),
                    "note_id": task.get("note_id"),
                }
                for task in (report_artifacts.get("tasks") or [])
                if isinstance(task, dict)
            ],
            "supporting_notes": [
                {
                    "id": note.get("id"),
                    "title": note.get("title"),
                    "type": note.get("type"),
                    "created_at": note.get("created_at"),
                }
                for note in (report_artifacts.get("supporting_notes") or [])
                if isinstance(note, dict)
            ],
            "paper_cards": list(report_artifacts.get("paper_cards") or []),
            "memo_sections": list(report_artifacts.get("memo_sections") or []),
            "review_sections": list(report_artifacts.get("review_sections") or []),
            "section_generation": list(report_artifacts.get("section_generation") or []),
            "evidence_buckets": {
                "core": list(evidence_buckets.get("core") or [])
                if isinstance(evidence_buckets, dict)
                else [],
                "adjacent_transfer": list(evidence_buckets.get("adjacent_transfer") or [])
                if isinstance(evidence_buckets, dict)
                else [],
                "off_target": list(evidence_buckets.get("off_target") or [])
                if isinstance(evidence_buckets, dict)
                else [],
            },
        }
    else:
        normalized["report_artifacts"] = {
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
    return normalized
