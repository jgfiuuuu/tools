"""Service that consolidates task results into the final report."""

from __future__ import annotations

import json
import logging
import re
import time

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState
from config import Configuration
from utils import strip_thinking_tokens
from services.text_processing import strip_tool_calls

class ReportingService:
    """Generates the final structured report."""

    def __init__(self, report_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = report_agent
        self._config = config
        self._logger = logging.getLogger(__name__)

    def generate_report(self, state: SummaryState) -> str:
        prompt = self._build_prompt(state)
        fallback_report = self._build_fallback_report(state)
        response = self._call_report_agent(prompt, fallback_report)
        self._agent.clear_history()

        report_text = (response or fallback_report).strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)

        report_text = strip_tool_calls(report_text).strip()

        return report_text or fallback_report

    def _build_prompt(self, state: SummaryState) -> str:
        tasks_block = []
        for task in state.todo_items:
            summary_block = task.summary or "暂无可用信息"
            sources_block = task.sources_summary or "暂无来源"
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n"
                f"- 任务总结：\n{summary_block}\n"
                f"- 来源概览：\n{sources_block}\n"
            )

        note_references = []
        for task in state.todo_items:
            if task.note_id:
                note_references.append(
                    f"- 任务 {task.id}《{task.title}》：note_id={task.note_id}"
                )

        notes_section = "\n".join(note_references) if note_references else "- 暂无可用任务笔记"

        read_template = json.dumps(
            {"action": "read", "note_id": "<note_id>"},
            ensure_ascii=False,
        )
        create_conclusion_template = json.dumps(
            {
                "action": "create",
                "title": f"研究报告：{state.research_topic}",
                "note_type": "conclusion",
                "tags": ["deep_research", "report"],
                "content": "请在此沉淀最终报告要点",
            },
            ensure_ascii=False,
        )

        return (
            f"研究主题：{state.research_topic}\n"
            f"任务概览：\n{''.join(tasks_block)}\n"
            f"可用任务笔记：\n{notes_section}\n"
            f"请针对每条任务笔记使用格式：[TOOL_CALL:note:{read_template}] 读取内容，整合所有信息后撰写报告。\n"
            f"如需输出汇总结论，可追加调用：[TOOL_CALL:note:{create_conclusion_template}] 保存报告要点。"
        )

    def _build_fallback_report(self, state: SummaryState) -> str:
        sections = [f"# {state.research_topic or '研究报告'}"]

        if not state.todo_items:
            sections.append("暂无任务结果，未能生成结构化研究内容。")
            return "\n\n".join(sections).strip()

        for task in state.todo_items:
            sections.append(
                f"## 任务 {task.id}: {task.title}\n"
                f"- 任务目标：{task.intent}\n"
                f"- 检索查询：{task.query}\n"
                f"- 执行状态：{task.status}\n\n"
                f"### 任务总结\n"
                f"{task.summary or '暂无可用信息'}\n\n"
                f"### 来源概览\n"
                f"{task.sources_summary or '暂无来源'}"
            )

        return "\n\n".join(sections).strip()

    def _call_report_agent(self, prompt: str, fallback_text: str) -> str | None:
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                return self._agent.run(prompt)
            except Exception as exc:
                last_exc = exc
                error_text = str(exc)
                lowered = error_text.lower()

                if "429" not in error_text:
                    raise

                if any(
                    token in lowered
                    for token in (
                        "quota exceeded",
                        "free tier",
                        "per day",
                        "resource_exhausted",
                    )
                ):
                    self._logger.warning("Writer hard quota hit, fallback to template report: %s", error_text)
                    return fallback_text

                if attempt == 2:
                    raise

                delay = self._extract_retry_delay(error_text) or min(2 * (attempt + 1), 20)
                self._logger.warning(
                    "Writer rate limited, retry after %s seconds (attempt %s/3)",
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)

        if last_exc is not None:
            self._logger.warning("Writer failed after retries, fallback to template report: %s", last_exc)
        return fallback_text

    def _extract_retry_delay(self, text: str) -> int:
        match = re.search(r"retry(?: in)?\s+(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

