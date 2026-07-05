# ruff: noqa: D202,D107

"""LangGraph-driven scholarly retrieval workflow."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from config import Configuration
from services.scholarly_contracts import default_workflow_metrics
from services.scholarly_rerank import ScholarlyScreeningService
from services.scholarly_search import ScholarlySearchService, unique_strings
from services.scholarly_store import ScholarlyStore


class ScholarlyWorkflowState(TypedDict, total=False):
    """Mutable state for the scholarly retrieval graph."""

    session_id: str
    topic: str
    parent_session_id: str | None
    status: str
    query_tasks: list[dict[str, Any]]
    frontier_query_tasks: list[dict[str, Any]]
    planner_notices: list[str]
    source_statuses: dict[str, str]
    skipped_sources: list[str]
    degradation_notices: list[str]
    raw_papers: list[dict[str, Any]]
    deduped_papers: list[dict[str, Any]]
    coarse_ranked_papers: list[dict[str, Any]]
    final_ranked_papers: list[dict[str, Any]]
    selected_papers: list[dict[str, Any]]
    frontier_mode: bool
    frontier_reason: str | None
    metrics: dict[str, Any]
    events: list[dict[str, Any]]
    error: str | None


class ScholarlyWorkflowGraph:
    """Coordinate scholarly recall and rerank via LangGraph."""

    def __init__(
        self,
        config: Configuration,
        store: ScholarlyStore,
        search: ScholarlySearchService,
        screening: ScholarlyScreeningService,
    ) -> None:
        self.config = config
        self.store = store
        self.search = search
        self.screening = screening
        workflow = StateGraph(ScholarlyWorkflowState)
        workflow.add_node("bootstrap_session", self._guard(self.bootstrap_session))
        workflow.add_node("plan_queries", self._guard(self.plan_queries))
        workflow.add_node("retrieve_candidates", self._guard(self.retrieve_candidates))
        workflow.add_node("dedupe_and_normalize", self._guard(self.dedupe_and_normalize))
        workflow.add_node("coarse_rerank", self._guard(self.coarse_rerank))
        workflow.add_node("frontier_decision", self._guard(self.frontier_decision))
        workflow.add_node("frontier_expand", self._guard(self.frontier_expand))
        workflow.add_node("finalize_rerank", self._guard(self.finalize_rerank))
        workflow.add_node("persist_results", self._guard(self.persist_results))
        workflow.add_node("handle_error", self.handle_error)

        workflow.add_edge(START, "bootstrap_session")
        workflow.add_conditional_edges(
            "bootstrap_session",
            self._route_after_bootstrap,
            {
                "plan_queries": "plan_queries",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "plan_queries",
            self._route_after_plan,
            {
                "retrieve_candidates": "retrieve_candidates",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "retrieve_candidates",
            self._route_after_retrieve,
            {
                "dedupe_and_normalize": "dedupe_and_normalize",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "dedupe_and_normalize",
            self._route_after_dedupe,
            {
                "coarse_rerank": "coarse_rerank",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "coarse_rerank",
            self._route_after_coarse,
            {
                "frontier_decision": "frontier_decision",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "frontier_decision",
            self._route_after_frontier_decision,
            {
                "frontier_expand": "frontier_expand",
                "finalize_rerank": "finalize_rerank",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "frontier_expand",
            self._route_after_frontier_expand,
            {
                "finalize_rerank": "finalize_rerank",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "finalize_rerank",
            self._route_after_finalize,
            {
                "persist_results": "persist_results",
                "handle_error": "handle_error",
            },
        )
        workflow.add_conditional_edges(
            "persist_results",
            self._route_after_persist,
            {
                "end": END,
                "handle_error": "handle_error",
            },
        )
        workflow.add_edge("handle_error", END)
        self.graph = workflow.compile()

    def invoke(
        self,
        topic: str,
        parent_session_id: str | None = None,
    ) -> ScholarlyWorkflowState:
        """Run the graph to completion and return the final state."""

        return self.graph.invoke(self._initial_state(topic, parent_session_id))

    def stream(
        self,
        topic: str,
        parent_session_id: str | None = None,
    ):
        """Stream node updates for the scholarly workflow."""

        return self.graph.stream(
            self._initial_state(topic, parent_session_id),
            stream_mode="updates",
        )

    def bootstrap_session(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Create a persisted session and initialize graph state."""

        session = self.store.create_session(
            state["topic"],
            parent_session_id=state.get("parent_session_id"),
        )
        return {
            "session_id": session["id"],
            "status": "created",
            "query_tasks": [],
            "frontier_query_tasks": [],
            "planner_notices": [],
            "source_statuses": {},
            "skipped_sources": [],
            "degradation_notices": [],
            "raw_papers": [],
            "deduped_papers": [],
            "coarse_ranked_papers": [],
            "final_ranked_papers": [],
            "selected_papers": [],
            "frontier_mode": False,
            "frontier_reason": None,
            "metrics": default_workflow_metrics(),
            "events": [{"type": "session_created", "session": session}],
            "error": None,
        }

    def plan_queries(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Generate concept-first query subtasks and persist them."""

        query_tasks, planner_notices = self.search.generate_query_plan(state["topic"])
        metadata = self._metadata_from_state(
            {
                **state,
                "query_tasks": query_tasks,
                "degradation_notices": list(planner_notices),
            }
        )
        self.store.update_session(
            state["session_id"],
            status="searching",
            queries=query_tasks,
            metadata=metadata,
        )
        return {
            "status": "searching",
            "query_tasks": query_tasks,
            "planner_notices": planner_notices,
            "degradation_notices": list(planner_notices),
            "events": [
                {
                    "type": "query_plan_generated",
                    "session_id": state["session_id"],
                    "queries": query_tasks,
                },
                {
                    "type": "query_generated",
                    "session_id": state["session_id"],
                    "queries": query_tasks,
                },
            ],
        }

    def retrieve_candidates(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Recall raw candidates and emit source/task completion events."""

        query_tasks = deepcopy(state.get("query_tasks") or [])
        retrieved = self.search.retrieve_candidates(
            state["topic"],
            self.config.scholarly_candidate_limit,
            query_tasks=query_tasks,
            planner_notices=state.get("planner_notices") or [],
        )
        deduped_preview = self.search.dedupe_and_normalize(
            retrieved["raw_papers"],
            limit=self.config.scholarly_candidate_limit,
        )
        metrics = {
            **default_workflow_metrics(state.get("metrics")),
            "raw_paper_count": len(retrieved["raw_papers"]),
        }
        metadata = self._metadata_from_state(
            {
                **state,
                "source_statuses": retrieved["source_statuses"],
                "skipped_sources": retrieved["skipped_sources"],
                "degradation_notices": retrieved["degradation_notices"],
                "metrics": metrics,
            }
        )
        self.store.update_session(
            state["session_id"],
            queries=retrieved["queries"],
            metadata=metadata,
        )

        events: list[dict[str, Any]] = []
        for source_name, status in metadata["source_statuses"].items():
            if status.startswith("skipped"):
                events.append(
                    {
                        "type": "source_skipped",
                        "session_id": state["session_id"],
                        "source": source_name,
                        "reason": status,
                    }
                )
            elif status in {"failed", "partial_failure"}:
                events.append(
                    {
                        "type": "source_failed",
                        "session_id": state["session_id"],
                        "source": source_name,
                        "reason": status,
                    }
                )
        for task in retrieved["queries"]:
            events.append(
                {
                    "type": "subtask_completed",
                    "session_id": state["session_id"],
                    "subtask": task,
                }
            )
        for notice in metadata["degradation_notices"]:
            events.append(
                {
                    "type": "status",
                    "session_id": state["session_id"],
                    "message": notice,
                }
            )
        events.append(
            {
                "type": "papers_recalled",
                "session_id": state["session_id"],
                "count": len(deduped_preview),
            }
        )
        return {
            "query_tasks": retrieved["queries"],
            "raw_papers": retrieved["raw_papers"],
            "source_statuses": metadata["source_statuses"],
            "skipped_sources": metadata["skipped_sources"],
            "degradation_notices": metadata["degradation_notices"],
            "metrics": metrics,
            "events": events,
        }

    def dedupe_and_normalize(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Normalize and trim the cross-source candidate pool."""

        deduped = self.search.dedupe_and_normalize(
            state.get("raw_papers") or [],
            limit=self.config.scholarly_candidate_limit,
        )
        return {
            "deduped_papers": deduped,
            "metrics": {
                **default_workflow_metrics(state.get("metrics")),
                "deduped_paper_count": len(deduped),
            },
            "events": [],
        }

    def coarse_rerank(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Score the candidate pool and keep a stable top-50."""

        self.store.update_session(state["session_id"], status="screening")
        coarse_ranked = self.screening.coarse_rerank(
            state["topic"],
            state.get("deduped_papers") or [],
            state.get("query_tasks"),
            limit=self.config.scholarly_candidate_limit,
        )
        return {
            "status": "screening",
            "coarse_ranked_papers": coarse_ranked,
            "metrics": {
                **default_workflow_metrics(state.get("metrics")),
                "coarse_candidate_count": len(coarse_ranked),
            },
            "events": [
                {
                    "type": "status",
                    "session_id": state["session_id"],
                    "message": f"Coarse rerank kept {len(coarse_ranked)} candidates",
                }
            ],
        }

    def frontier_decision(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Trigger a conservative fallback pass for sparse topics."""

        decision = self.screening.frontier_decision(
            state["topic"],
            state.get("coarse_ranked_papers") or [],
            state.get("query_tasks"),
        )
        events: list[dict[str, Any]] = []
        if decision["frontier_mode"]:
            events.append(
                {
                    "type": "status",
                    "session_id": state["session_id"],
                    "message": (
                        "Frontier fallback triggered"
                        if not decision["frontier_reason"]
                        else f"Frontier fallback triggered: {decision['frontier_reason']}"
                    ),
                }
            )
        return {
            "frontier_mode": decision["frontier_mode"],
            "frontier_reason": decision["frontier_reason"],
            "metrics": {
                **default_workflow_metrics(state.get("metrics")),
                **decision["metrics"],
            },
            "events": events,
        }

    def frontier_expand(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Run a small-budget adjacent/broader expansion pass when needed."""

        frontier_tasks = self.search.build_frontier_expansion_tasks(
            state["topic"],
            state.get("query_tasks") or [],
        )
        if not frontier_tasks:
            return {
                "frontier_query_tasks": [],
                "metrics": default_workflow_metrics(state.get("metrics")),
                "events": [
                    {
                        "type": "status",
                        "session_id": state["session_id"],
                        "message": "Frontier fallback skipped: no expansion tasks generated",
                    }
                ],
            }

        frontier_budget = max(12, min(24, self.config.scholarly_candidate_limit // 2))
        frontier_retrieved = self.search.retrieve_candidates(
            state["topic"],
            frontier_budget,
            query_tasks=deepcopy(frontier_tasks),
            planner_notices=[],
        )
        combined_raw = [
            *(state.get("raw_papers") or []),
            *frontier_retrieved["raw_papers"],
        ]
        deduped = self.search.dedupe_and_normalize(
            combined_raw,
            limit=self.config.scholarly_candidate_limit,
        )
        coarse_ranked = self.screening.coarse_rerank(
            state["topic"],
            deduped,
            state.get("query_tasks"),
            limit=self.config.scholarly_candidate_limit,
        )
        source_statuses = self.search.merge_source_statuses(
            state.get("source_statuses") or {},
            frontier_retrieved["source_statuses"],
        )
        skipped_sources = unique_strings(
            [
                *(state.get("skipped_sources") or []),
                *frontier_retrieved["skipped_sources"],
            ]
        )
        degradation_notices = unique_strings(
            [
                *(state.get("degradation_notices") or []),
                *frontier_retrieved["degradation_notices"],
            ]
        )
        existing_notices = set(state.get("degradation_notices") or [])
        new_notices = [
            notice
            for notice in degradation_notices
            if notice not in existing_notices
        ]
        events: list[dict[str, Any]] = [
            {
                "type": "status",
                "session_id": state["session_id"],
                "message": f"Frontier fallback merged {len(deduped)} candidates",
            }
        ]
        for notice in new_notices:
            events.append(
                {
                    "type": "status",
                    "session_id": state["session_id"],
                    "message": notice,
                }
            )
        return {
            "frontier_query_tasks": frontier_tasks,
            "raw_papers": combined_raw,
            "deduped_papers": deduped,
            "coarse_ranked_papers": coarse_ranked,
            "source_statuses": source_statuses,
            "skipped_sources": skipped_sources,
            "degradation_notices": degradation_notices,
            "metrics": {
                **default_workflow_metrics(state.get("metrics")),
                "raw_paper_count": len(combined_raw),
                "deduped_paper_count": len(deduped),
                "frontier_added_raw_count": len(frontier_retrieved["raw_papers"]),
                "frontier_query_count": len(frontier_tasks),
                "coarse_candidate_count": len(coarse_ranked),
            },
            "events": events,
        }

    def finalize_rerank(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Produce final paper ranking and paper_ranked events."""

        final_ranked = self.screening.finalize_rerank(
            state["topic"],
            state.get("coarse_ranked_papers") or [],
            state.get("query_tasks"),
            limit=self.config.scholarly_candidate_limit,
        )
        selected = [
            paper
            for paper in final_ranked
            if paper.get("selected")
        ][: self.config.scholarly_selection_limit]
        events = [
            {
                "type": "paper_ranked",
                "session_id": state["session_id"],
                "paper": compact_paper_event(paper),
            }
            for paper in selected
        ]
        return {
            "final_ranked_papers": final_ranked,
            "selected_papers": selected,
            "metrics": {
                **default_workflow_metrics(state.get("metrics")),
                "final_candidate_count": len(final_ranked),
                "selected_count": len(selected),
            },
            "events": events,
        }

    def persist_results(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Persist ranked papers and emit the final screening_done event."""

        self.store.upsert_session_papers(
            state["session_id"],
            state.get("final_ranked_papers") or [],
            clear_existing=True,
        )
        self.store.update_session(
            state["session_id"],
            status="ready",
            queries=state.get("query_tasks") or [],
            metadata=self._metadata_from_state(state),
        )
        detail = self.store.get_session_detail(state["session_id"])
        return {
            "status": "ready",
            "events": [{"type": "screening_done", "session": detail}],
        }

    def handle_error(self, state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
        """Persist error status and emit a terminal error event."""

        session_id = state.get("session_id")
        if session_id:
            self.store.update_session(
                session_id,
                status="error",
                queries=state.get("query_tasks") or [],
                metadata=self._metadata_from_state(state),
            )
        return {
            "status": "error",
            "events": [
                {
                    "type": "error",
                    "session_id": session_id,
                    "detail": state.get("error") or "workflow_failed",
                }
            ],
        }

    def _guard(self, func):
        def _wrapped(state: ScholarlyWorkflowState) -> ScholarlyWorkflowState:
            if state.get("error"):
                return {"events": []}
            try:
                return func(state)
            except Exception as exc:  # pragma: no cover - defensive catch for graph routing
                return {
                    "error": str(exc),
                    "events": [],
                }

        return _wrapped

    def _initial_state(
        self,
        topic: str,
        parent_session_id: str | None,
    ) -> ScholarlyWorkflowState:
        return {
            "topic": topic,
            "parent_session_id": parent_session_id,
            "status": "created",
            "query_tasks": [],
            "frontier_query_tasks": [],
            "planner_notices": [],
            "source_statuses": {},
            "skipped_sources": [],
            "degradation_notices": [],
            "raw_papers": [],
            "deduped_papers": [],
            "coarse_ranked_papers": [],
            "final_ranked_papers": [],
            "selected_papers": [],
            "frontier_mode": False,
            "frontier_reason": None,
            "metrics": default_workflow_metrics(),
            "events": [],
            "error": None,
        }

    def _metadata_from_state(self, state: ScholarlyWorkflowState) -> dict[str, Any]:
        return self.search.build_session_metadata(
            topic=state["topic"],
            query_tasks=state.get("query_tasks"),
            frontier_query_tasks=state.get("frontier_query_tasks"),
            raw_papers=state.get("raw_papers"),
            deduped_papers=state.get("deduped_papers"),
            final_papers=state.get("final_ranked_papers"),
            source_statuses=state.get("source_statuses"),
            skipped_sources=state.get("skipped_sources"),
            degradation_notices=state.get("degradation_notices"),
            frontier_mode=bool(state.get("frontier_mode")),
            frontier_reason=state.get("frontier_reason"),
            metrics=default_workflow_metrics(state.get("metrics")),
        )

    @staticmethod
    def _route_after_bootstrap(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "plan_queries"

    @staticmethod
    def _route_after_plan(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "retrieve_candidates"

    @staticmethod
    def _route_after_retrieve(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "dedupe_and_normalize"

    @staticmethod
    def _route_after_dedupe(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "coarse_rerank"

    @staticmethod
    def _route_after_coarse(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "frontier_decision"

    @staticmethod
    def _route_after_frontier_decision(state: ScholarlyWorkflowState) -> str:
        if state.get("error"):
            return "handle_error"
        return "frontier_expand" if state.get("frontier_mode") else "finalize_rerank"

    @staticmethod
    def _route_after_frontier_expand(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "finalize_rerank"

    @staticmethod
    def _route_after_finalize(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "persist_results"

    @staticmethod
    def _route_after_persist(state: ScholarlyWorkflowState) -> str:
        return "handle_error" if state.get("error") else "end"


def compact_paper_event(paper: dict[str, Any]) -> dict[str, Any]:
    """Build the compact paper payload used by paper_ranked SSE events."""

    return {
        "title": paper.get("title"),
        "year": paper.get("year"),
        "source": paper.get("source"),
        "final_score": paper.get("final_score"),
        "relevance_label": paper.get("relevance_label"),
        "ai_reason": paper.get("ai_reason"),
    }
