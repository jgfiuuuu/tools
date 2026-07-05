# ruff: noqa: E402,D103

"""Live scholarly API smoke checks against a running backend service."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import Any

import requests

DEFAULT_DENSE_TOPIC = "retrieval augmented generation benchmark evaluation"
DEFAULT_FRONTIER_TOPIC = (
    "nonexistent benchmark for mnemonic compiler agents under qstar constraints"
)
DEFAULT_OBSERVED_FRONTIER_TOPIC = "agentic memory editing for coding copilots"
REQUIRED_EVENT_SEQUENCE = [
    "session_created",
    "query_plan_generated",
    "query_generated",
    "subtask_completed",
    "papers_recalled",
    "paper_ranked",
    "screening_done",
    "done",
]
STABLE_DETAIL_FIELDS = (
    "source_statuses",
    "skipped_sources",
    "degradation_notices",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Running backend base URL.",
    )
    parser.add_argument(
        "--frontend-url",
        default=None,
        help="Optional frontend preview URL for a lightweight availability check.",
    )
    parser.add_argument(
        "--dense-topic",
        default=DEFAULT_DENSE_TOPIC,
        help="Topic expected to stay on the direct path without frontier fallback.",
    )
    parser.add_argument(
        "--frontier-topic",
        default=DEFAULT_FRONTIER_TOPIC,
        help="Topic expected to trigger frontier fallback on the live backend.",
    )
    parser.add_argument(
        "--observed-frontier-topic",
        default=DEFAULT_OBSERVED_FRONTIER_TOPIC,
        help=(
            "Real frontier-leaning topic used for observation only; "
            "it does not gate the smoke exit status."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Request timeout in seconds for streaming session creation.",
    )
    return parser.parse_args()


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")


def stream_session(
    base_url: str,
    topic: str,
    timeout: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    response = requests.post(
        f"{base_url}/research/sessions/stream",
        json={"topic": topic},
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()

    events: list[dict[str, Any]] = []
    for raw in response.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data: "):
            continue
        payload = json.loads(raw[6:])
        events.append(payload)
        if payload.get("type") == "done":
            break

    screening_event = next(
        (event for event in events if event.get("type") == "screening_done"),
        None,
    )
    if screening_event is None:
        raise RuntimeError(f"screening_done missing for topic: {topic}")

    session = screening_event["session"]
    detail = requests.get(
        f"{base_url}/research/sessions/{session['id']}",
        timeout=60,
    )
    detail.raise_for_status()
    return events, session, detail.json()


def contains_subsequence(items: Iterable[str], expected: list[str]) -> bool:
    iterator = iter(items)
    return all(any(item == needle for item in iterator) for needle in expected)


def has_query_contract(detail: dict[str, Any]) -> dict[str, bool | int]:
    queries = detail.get("queries") or []
    task_fields_ok = all(
        isinstance(task, dict)
        and "frontier_expansion" in task
        and "parent_subtask_id" in task
        for task in queries
    )
    variant_fields_ok = all(
        isinstance(variant, dict)
        and "frontier_expansion" in variant
        and "parent_subtask_id" in variant
        for task in queries
        if isinstance(task, dict)
        for variant in task.get("variants") or []
    )
    return {
        "query_count": len(queries),
        "task_fields_ok": task_fields_ok,
        "variant_fields_ok": variant_fields_ok,
    }


def collect_failures(
    *,
    expected_frontier: bool | None,
    event_types: list[str],
    session: dict[str, Any],
    detail: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if not contains_subsequence(event_types, REQUIRED_EVENT_SEQUENCE):
        failures.append("event_sequence_incompatible")

    actual_frontier = bool(detail["metadata"]["frontier_mode"])
    if expected_frontier is not None and actual_frontier != expected_frontier:
        failures.append(
            f"unexpected_frontier_mode(expected={expected_frontier}, actual={actual_frontier})"
        )

    for field in STABLE_DETAIL_FIELDS:
        if session.get(field) != detail.get(field):
            failures.append(f"detail_mismatch:{field}")

    if session["metadata"].get("frontier_mode") != detail["metadata"].get("frontier_mode"):
        failures.append("detail_mismatch:frontier_mode")
    if session["metadata"].get("frontier_reason") != detail["metadata"].get("frontier_reason"):
        failures.append("detail_mismatch:frontier_reason")
    if session["metadata"].get("metrics") != detail["metadata"].get("metrics"):
        failures.append("detail_mismatch:metrics")

    query_contract = has_query_contract(detail)
    if not query_contract["task_fields_ok"]:
        failures.append("query_contract_missing_task_fields")
    if not query_contract["variant_fields_ok"]:
        failures.append("query_contract_missing_variant_fields")
    return failures


def summarize_case(
    *,
    label: str,
    topic: str,
    expected_frontier: bool | None,
    gating: bool,
    events: list[dict[str, Any]],
    session: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    event_types = [str(event.get("type")) for event in events]
    failures = collect_failures(
        expected_frontier=expected_frontier,
        event_types=event_types,
        session=session,
        detail=detail,
    )
    return {
        "label": label,
        "topic": topic,
        "gating": gating,
        "expected_frontier": expected_frontier,
        "frontier_mode": bool(detail["metadata"]["frontier_mode"]),
        "frontier_reason": detail["metadata"]["frontier_reason"],
        "event_types": event_types,
        "metrics": detail["metrics"],
        "source_contributions": detail["metadata"].get("source_contributions", {}),
        "query_contract": has_query_contract(detail),
        "failures": failures,
    }


def check_frontend(frontend_url: str | None) -> dict[str, Any] | None:
    if not frontend_url:
        return None

    response = requests.get(frontend_url, timeout=20)
    response.raise_for_status()
    html = response.text
    return {
        "url": frontend_url,
        "status_code": response.status_code,
        "contains_app_root": 'id="app"' in html or "id='app'" in html,
        "contains_module_script": 'type="module"' in html or "type='module'" in html,
    }


def main() -> None:
    args = parse_args()
    base_url = normalize_base_url(args.base_url)
    cases = [
        ("dense", args.dense_topic, False, True),
        ("frontier", args.frontier_topic, True, True),
        ("observed_frontier", args.observed_frontier_topic, None, False),
    ]

    results: list[dict[str, Any]] = []
    for label, topic, expected_frontier, gating in cases:
        events, session, detail = stream_session(base_url, topic, args.timeout)
        results.append(
            summarize_case(
                label=label,
                topic=topic,
                expected_frontier=expected_frontier,
                gating=gating,
                events=events,
                session=session,
                detail=detail,
            )
        )

    frontend = check_frontend(args.frontend_url)
    payload = {
        "base_url": base_url,
        "frontend": frontend,
        "cases": results,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    failures = [
        failure
        for result in results
        if result["gating"]
        for failure in result["failures"]
    ]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
