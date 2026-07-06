"""Orchestrator coordinating the general research workflow."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from hello_agents.core.exceptions import HelloAgentsException
from hello_agents.tools import ToolRegistry
from hello_agents.tools.builtin.note_tool import NoteTool
from langgraph.graph import END, START, StateGraph

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.text_processing import strip_tool_calls
from services.tool_events import ToolCallTracker
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM(HelloAgentsLLM):
    """Normalize OpenAI-compatible responses before HelloAgents stores messages."""

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        for attempt in range(3):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=kwargs.get("temperature", self.temperature),
                    max_tokens=kwargs.get("max_tokens", self.max_tokens),
                    **{
                        key: value
                        for key, value in kwargs.items()
                        if key not in ["temperature", "max_tokens"]
                    },
                )
            except Exception as exc:
                raise HelloAgentsException(f"LLM调用失败: {exc}") from exc

            message = response.choices[0].message
            content = message.content
            if content is not None:
                return content

            if attempt < 2:
                time.sleep(attempt + 1)

        raise HelloAgentsException(
            "LLM连续返回空的 message.content。当前中转站响应不稳定，"
            "请更换模型名、检查中转站 OpenAI-compatible 转换，或稍后重试。"
        )


    def stream_invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> Iterator[str]:
        """Stream text while tolerating empty OpenAI-compatible chunks."""
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=True,
                **{
                    key: value
                    for key, value in kwargs.items()
                    if key not in ["temperature", "max_tokens"]
                },
            )

            emitted = False
            for chunk in response:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None)
                if not content:
                    continue

                emitted = True
                yield content

            if not emitted:
                fallback = self.invoke(messages, **kwargs)
                if fallback:
                    yield fallback
        except Exception as exc:
            if isinstance(exc, HelloAgentsException):
                raise
            raise HelloAgentsException(f"LLM call failed: {exc}") from exc


class DeepResearchAgent:
    """Coordinator orchestrating TODO-based research workflow using HelloAgents."""

    def __init__(self, config: Configuration | None = None) -> None:
        """Initialise the coordinator with configuration and shared tools."""
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self._tool_event_sink_enabled = False
        self._state_lock = Lock()

        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
        )
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
        )

        self._summarizer_factory: Callable[[], ToolAwareSimpleAgent] = lambda: self._create_tool_aware_agent(  # noqa: E501
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
        )

        self.planner = PlanningService(self.todo_agent, self.config)
        self.summarizer = SummarizationService(self._summarizer_factory, self.config)
        self.reporting = ReportingService(self.report_agent, self.config)
        workflow = StateGraph(SummaryState)
        workflow.add_node("writer", self.writer_node)
        workflow.add_node("reviewer", self.reviewer_node)
        workflow.add_edge(START, "writer")
        workflow.add_edge("writer", "reviewer")
        workflow.add_conditional_edges(
            "reviewer",
            self.should_rewrite,
            {"writer": "writer", "end": END},
        )
        self.graph = workflow.compile()
        self._last_search_notices: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _init_llm(self) -> HelloAgentsLLM:
        """Instantiate HelloAgentsLLM following configuration preferences."""
        llm_kwargs: dict[str, Any] = {"temperature": 0.0}

        model_id = self.config.llm_model_id or self.config.local_llm
        if model_id:
            llm_kwargs["model"] = model_id

        provider = (self.config.llm_provider or "").strip()
        if provider:
            llm_kwargs["provider"] = provider

        if provider == "ollama":
            llm_kwargs["base_url"] = self.config.sanitized_ollama_url()
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif provider == "lmstudio":
            llm_kwargs["base_url"] = self.config.lmstudio_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key
        else:
            if self.config.llm_base_url:
                llm_kwargs["base_url"] = self.config.llm_base_url
            if self.config.llm_api_key:
                llm_kwargs["api_key"] = self.config.llm_api_key

        return OpenAICompatibleLLM(**llm_kwargs)

    def _create_tool_aware_agent(self, *, name: str, system_prompt: str) -> ToolAwareSimpleAgent:
        """Instantiate a ToolAwareSimpleAgent sharing tool registry and tracker."""
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=self.tools_registry is not None,
            tool_registry=self.tools_registry,
            tool_call_listener=self._tool_tracker.record,
        )

    def _set_tool_event_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None:
        """Enable or disable immediate tool event callbacks."""
        self._tool_event_sink_enabled = sink is not None
        self._tool_tracker.set_event_sink(sink)

    def _free_tier_safe_mode(self) -> bool:
        return True

    def _max_rewrite_rounds(self) -> int:
        return 1 if self._free_tier_safe_mode() else 3

    def _apply_task_budget(self, state: SummaryState) -> None:
        if self._free_tier_safe_mode() and len(state.todo_items) > 3:
            state.todo_items = state.todo_items[:3]

    def _extract_retry_delay(self, text: str) -> int:
        match = re.search(r"retry(?: in)?\s+(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    def _build_fallback_report(self, state: SummaryState) -> str:
        blocks = [f"# {state.research_topic}"]
        for task in state.todo_items:
            blocks.append(
                f"## {task.title}\n{task.summary or '暂无可用信息'}\n\n来源：\n{task.sources_summary or '暂无来源'}"
            )
        return "\n\n".join(blocks).strip() or "报告生成失败，请稍后重试。"

    def _call_agent(self, agent: ToolAwareSimpleAgent, prompt: str, fallback_text: str | None = None) -> str | None:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                return agent.run(prompt)
            except Exception as exc:
                last_exc = exc
                text = str(exc)
                lowered = text.lower()
                if "429" not in text:
                    raise
                if any(token in lowered for token in ("quota exceeded", "free tier", "per day", "resource_exhausted")):
                    return fallback_text
                if attempt == 2:
                    raise
                delay = self._extract_retry_delay(text) or min(2 * (attempt + 1), 20)
                time.sleep(delay)
        if fallback_text is not None:
            return fallback_text
        if last_exc is not None:
            raise last_exc
        return None

    def writer_node(self, state: SummaryState) -> SummaryState:
        feedback = (state.review_feedback or "").strip()
        fallback_report = self._build_fallback_report(state)
        if not feedback:
            draft = self.reporting.generate_report(state)
        else:
            tasks_block = []
            for task in state.todo_items:
                tasks_block.append(
                    f"### 任务 {task.id}: {task.title}\n"
                    f"- 任务目标：{task.intent}\n"
                    f"- 检索查询：{task.query}\n"
                    f"- 执行状态：{task.status}\n"
                    f"- 任务总结：\n{task.summary or '暂无可用信息'}\n"
                    f"- 来源概览：\n{task.sources_summary or '暂无来源'}\n"
                )
            note_refs = "\n".join(
                f"- 任务 {task.id}《{task.title}》：note_id={task.note_id}"
                for task in state.todo_items
                if task.note_id
            ) or "- 暂无可用任务笔记"
            read_template = json.dumps({"action": "read", "note_id": "<note_id>"}, ensure_ascii=False)
            create_template = json.dumps({"action": "create", "title": f"研究报告：{state.research_topic}", "note_type": "conclusion", "tags": ["deep_research", "report"], "content": "请在此沉淀最终报告要点"}, ensure_ascii=False)
            prompt = (
                f"最高优先级修改指令：这是来自评估专家的批评意见：{feedback}。你必须在本次重写中严格解决这些问题！\n"
                f"研究主题：{state.research_topic}\n"
                f"任务概览：\n{''.join(tasks_block)}\n"
                f"可用任务笔记：\n{note_refs}\n"
                f"请针对每条任务笔记使用格式：[TOOL_CALL:note:{read_template}] 读取内容，整合所有信息后撰写报告。\n"
                f"如需输出汇总结论，可追加调用：[TOOL_CALL:note:{create_template}] 保存报告要点。"
            )
            response = self._call_agent(self.report_agent, prompt, fallback_report)
            self.report_agent.clear_history()
            draft = (response or fallback_report).strip()
            if self.config.strip_thinking_tokens:
                draft = strip_thinking_tokens(draft)
            draft = strip_tool_calls(draft).strip()
            draft = draft or "报告生成失败，请检查输入。"
        state.structured_report = draft
        state.running_summary = draft
        return state

    def reviewer_node(self, state: SummaryState) -> SummaryState:
        outline = "\n".join(
            f"{task.id}. {task.title}：{task.intent}" for task in state.todo_items
        ) or "暂无大纲"
        draft = (state.structured_report or state.running_summary or "").strip()
        reviewer = self._create_tool_aware_agent(
            name="报告评审专家",
            system_prompt="你是一名极其严苛的资深行业分析师，只负责审稿打分与提出可执行修改意见。",
        )
        prompt = (
            "请严格审查下面的研究报告草稿。你必须基于研究主题、任务大纲与草稿内容进行评分。"
            "评分范围为 0 到 100。仅输出 JSON 文本，不要输出 Markdown、不要加代码块、不要解释。\n"
            f"研究主题：{state.research_topic}\n"
            f"任务大纲：\n{outline}\n"
            f"当前草稿：\n{draft}\n"
            '输出格式：{"score": 0, "feedback": "具体修改建议"}'
        )
        response = self._call_agent(reviewer, prompt)
        reviewer.clear_history()
        if response is None:
            state.review_score = 80
            state.review_feedback = "评审节点因额度受限已跳过，直接输出当前草稿。"
            return state
        text = response.strip()
        if self.config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)
        match = re.search(r"\{[\s\S]*\}", text)
        payload: dict[str, Any] = {}
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = {}
        score = payload.get("score", 0)
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = 0
        feedback = str(
            payload.get("feedback")
            or "请补足结构完整性、证据充分性与结论严谨性。"
        )
        state.review_score = score
        state.review_feedback = feedback.strip()
        if score < 80:
            state.retry_count += 1
        return state

    def should_rewrite(self, state: SummaryState) -> str:
        if (state.review_score or 0) >= 80:
            return "end"
        if state.retry_count >= self._max_rewrite_rounds():
            return "end"
        return "writer"

    def _apply_graph_state(self, state: SummaryState, payload: Any) -> SummaryState:
        if isinstance(payload, SummaryState):
            return payload
        if isinstance(payload, dict):
            for key, value in payload.items():
                if hasattr(state, key):
                    setattr(state, key, value)
        return state

    def run(self, topic: str) -> SummaryStateOutput:
        """Execute the research workflow and return the final report."""
        state = SummaryState(research_topic=topic)
        state.todo_items = self.planner.plan_todo_list(state)
        self._drain_tool_events(state)

        if not state.todo_items:
            logger.info("No TODO items generated; falling back to single task")
            state.todo_items = [self.planner.create_fallback_task(state)]
        self._apply_task_budget(state)

        for task in state.todo_items:
            self._execute_task(state, task, emit_stream=False)

        state = self._apply_graph_state(state, self.graph.invoke(state))
        self._drain_tool_events(state)
        report = (state.structured_report or state.running_summary or "报告生成失败，请检查输入。").strip()
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Execute the workflow yielding incremental progress events."""
        state = SummaryState(research_topic=topic)
        logger.debug("Starting streaming research: topic=%s", topic)
        yield {"type": "status", "message": "初始化研究流程"}

        state.todo_items = self.planner.plan_todo_list(state)
        for event in self._drain_tool_events(state, step=0):
            yield event
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state)]
        self._apply_task_budget(state)

        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step": index, "token": token}

        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        for event in self._run_tasks_stream(state, channel_map):
            yield event

        final_step = len(state.todo_items) + 1
        for event in self._drain_tool_events(state, step=final_step):
            yield event

        latest_report = (state.structured_report or state.running_summary or "").strip()
        for update in self.graph.stream(state, stream_mode="updates"):
            if not isinstance(update, dict) or not update:
                continue
            node_name, node_payload = next(iter(update.items()))
            state = self._apply_graph_state(state, node_payload)

            if node_name == "writer":
                report = (state.structured_report or state.running_summary or "").strip()
                if report and report != latest_report:
                    latest_report = report
                    yield {"type": "status", "message": f"报告草稿第 {state.retry_count + 1} 轮已生成，进入评审", "step": final_step}
                continue

            if node_name == "reviewer":
                score = state.review_score or 0
                feedback = (state.review_feedback or "").strip()

                yield {
                    "type": "status",
                    "message": f"报告评审得分：{score}",
                    "step": final_step,
                }

                if score >= 80:
                    yield {
                        "type": "status",
                        "message": "报告评审通过，输出最终结果",
                        "step": final_step,
                    }
                elif state.retry_count >= 3:
                    if feedback:
                        yield {
                            "type": "status",
                            "message": f"评审意见：{feedback}",
                            "step": final_step,
                        }
                    yield {
                        "type": "status",
                        "message": "已触发 3 次重试熔断，输出当前最佳结果",
                        "step": final_step,
                    }
                else:
                    if feedback:
                        yield {
                            "type": "status",
                            "message": f"评审意见：{feedback}",
                            "step": final_step,
                        }
                    yield {
                        "type": "status",
                        "message": "低于通过阈值，回退到 Writer 重写",
                        "step": final_step,
                    }

        report = (state.structured_report or state.running_summary or "报告生成失败，请检查输入。").strip()
        state.structured_report = report
        state.running_summary = report

        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event

        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
        }
        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------
    def _run_tasks_stream(
        self,
        state: SummaryState,
        channel_map: dict[int, dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        for task in state.todo_items:
            step = channel_map.get(task.id, {}).get("step", 0)
            token = channel_map.get(task.id, {}).get("token")
            yield {"type": "task_status", "task_id": task.id, "status": "in_progress", "title": task.title, "intent": task.intent, "note_id": task.note_id, "step": step, "stream_token": token}
            try:
                for event in self._execute_task(state, task, emit_stream=True, step=step):
                    payload = dict(event)
                    payload.setdefault("step", step)
                    payload["stream_token"] = token
                    yield payload
            except Exception as exc:
                logger.exception("Task execution failed", exc_info=exc)
                yield {"type": "task_status", "task_id": task.id, "status": "failed", "detail": str(exc), "title": task.title, "intent": task.intent, "note_id": task.note_id, "step": step, "stream_token": token}

    def _execute_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Run search + summarization for a single task."""
        task.status = "in_progress"

        search_result, notices, answer_text, backend = dispatch_search(
            task.query,
            self.config,
            state.research_loop_count,
        )
        self._last_search_notices = notices
        task.notices = notices

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
        else:
            self._drain_tool_events(state)

        if notices and emit_stream:
            for notice in notices:
                if notice:
                    yield {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "intent": task.intent,
                    "note_id": task.note_id,
                    "step": step,
                }
            else:
                self._drain_tool_events(state)
            return
        else:
            if not emit_stream:
                self._drain_tool_events(state)

        sources_summary, context = prepare_research_context(
            search_result,
            answer_text,
            self.config,
        )

        task.sources_summary = sources_summary

        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        summary_text: str | None = None

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
                "note_id": task.note_id,
            }

            summary_stream, summary_getter = self.summarizer.stream_task_summary(state, task, context)
            try:
                for event in self._drain_tool_events(state, step=step):
                    yield event
                for chunk in summary_stream:
                    if chunk:
                        yield {
                            "type": "task_summary_chunk",
                            "task_id": task.id,
                            "content": chunk,
                            "note_id": task.note_id,
                            "step": step,
                        }
                    for event in self._drain_tool_events(state, step=step):
                        yield event
            finally:
                summary_text = summary_getter()
        else:
            summary_text = self.summarizer.summarize_task(state, task, context)
            self._drain_tool_events(state)

        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

        if emit_stream:
            for event in self._drain_tool_events(state, step=step):
                yield event
            yield {
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "step": step,
            }
        else:
            self._drain_tool_events(state)

    def _drain_tool_events(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]:
        """Proxy to the shared tool call tracker."""
        events = self._tool_tracker.drain(state, step=step)
        if self._tool_event_sink_enabled:
            return []
        return events

    @property
    def _tool_call_events(self) -> list[dict[str, Any]]:
        """Expose recorded tool events for legacy integrations."""
        return self._tool_tracker.as_dicts()

    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        """Convert task dataclass to serializable dict for frontend."""
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "stream_token": task.stream_token,
        }

    def _persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        note_id = self._find_existing_report_note_id(state)
        response = ""

        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None

        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        if self.config.notes_workspace:
            note_path = Path(self.config.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }

        return payload

    def _find_existing_report_note_id(self, state: SummaryState) -> str | None:
        if state.report_note_id:
            return state.report_note_id

        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue

            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            action = parameters.get("action")
            if action not in {"create", "update"}:
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))  # type: ignore[attr-defined]

            if note_id:
                return note_id

        return None

    @staticmethod
    def _extract_note_id_from_text(response: str) -> str | None:
        if not response:
            return None

        match = re.search(r"ID:\s*([^\n]+)", response)
        if not match:
            return None

        return match.group(1).strip()


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function mirroring the class-based API."""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)
