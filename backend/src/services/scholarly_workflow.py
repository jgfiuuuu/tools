"""High-level scholarly research session workflow."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from config import Configuration
from services.scholarly_search import ScholarlyScreeningService, ScholarlySearchService
from services.scholarly_store import ScholarlyStore


class ScholarlyResearchService:
    """Coordinate scholarly recall, screening, reporting, and exports."""

    def __init__(self, config: Configuration) -> None:
        self.config = config
        self.store = ScholarlyStore(config.scholarly_db_path)
        self.search = ScholarlySearchService(config)
        self.screening = ScholarlyScreeningService(config)

    def create_session(self, topic: str, parent_session_id: str | None = None) -> dict[str, Any]:
        """Create a session and run the full recall/screening pipeline."""

        session = self.store.create_session(topic, parent_session_id=parent_session_id)
        self._recall_and_screen(session["id"], topic)
        return self.store.get_session_detail(session["id"])

    def create_session_stream(
        self,
        topic: str,
        parent_session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream session creation progress events."""

        session = self.store.create_session(topic, parent_session_id=parent_session_id)
        yield {"type": "session_created", "session": session}
        try:
            self.store.update_session(session["id"], status="searching")
            query_tasks, planner_notices = self.search.generate_query_plan(topic)
            self.store.update_session(
                session["id"],
                queries=query_tasks,
                metadata={
                    "source_statuses": {},
                    "skipped_sources": [],
                    "degradation_notices": planner_notices,
                },
            )
            yield {
                "type": "query_plan_generated",
                "session_id": session["id"],
                "queries": query_tasks,
            }
            yield {
                "type": "query_generated",
                "session_id": session["id"],
                "queries": query_tasks,
            }

            recall_result = self.search.recall(
                topic,
                self.config.scholarly_candidate_limit,
                query_tasks=query_tasks,
                planner_notices=planner_notices,
            )
            papers = recall_result["papers"]
            metadata = {
                "source_statuses": recall_result["source_statuses"],
                "skipped_sources": recall_result["skipped_sources"],
                "degradation_notices": recall_result["degradation_notices"],
            }
            self.store.update_session(
                session["id"],
                queries=recall_result["queries"],
                metadata=metadata,
            )
            for source_name, status in metadata["source_statuses"].items():
                if status.startswith("skipped"):
                    yield {
                        "type": "source_skipped",
                        "session_id": session["id"],
                        "source": source_name,
                        "reason": status,
                    }
                elif status in {"failed", "partial_failure"}:
                    yield {
                        "type": "source_failed",
                        "session_id": session["id"],
                        "source": source_name,
                        "reason": status,
                    }
            for task in recall_result["queries"]:
                yield {
                    "type": "subtask_completed",
                    "session_id": session["id"],
                    "subtask": task,
                }
            for notice in recall_result["degradation_notices"]:
                yield {"type": "status", "session_id": session["id"], "message": notice}
            yield {
                "type": "papers_recalled",
                "session_id": session["id"],
                "count": len(papers),
            }

            self.store.update_session(session["id"], status="screening")
            screened = self.screening.screen(topic, papers, recall_result["queries"])
            self.store.upsert_session_papers(session["id"], screened, clear_existing=True)
            for paper in screened[: self.config.scholarly_selection_limit]:
                yield {"type": "paper_ranked", "session_id": session["id"], "paper": self._compact_paper_event(paper)}
            self.store.update_session(session["id"], status="ready")
            yield {
                "type": "screening_done",
                "session": self.store.get_session_detail(session["id"]),
            }
        except Exception as exc:
            self.store.update_session(session["id"], status="error")
            yield {"type": "error", "session_id": session["id"], "detail": str(exc)}

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.store.list_sessions()

    def get_session_detail(self, session_id: str) -> dict[str, Any]:
        return self.store.get_session_detail(session_id)

    def delete_session(self, session_id: str) -> None:
        self.store.delete_session(session_id)

    def rescreen_session(self, session_id: str) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        papers = detail["papers"]
        screened = self.screening.screen(detail["topic"], papers, detail.get("queries"))
        self.store.upsert_session_papers(session_id, screened, clear_existing=True)
        self.store.update_session(session_id, status="ready")
        return self.store.get_session_detail(session_id)

    def update_paper(
        self,
        session_id: str,
        paper_id: str,
        *,
        user_status: str | None = None,
        selected: bool | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if user_status == "excluded":
            selected = False
        elif user_status in {"included", "saved", "to_read"} and selected is None:
            selected = True
        return self.store.update_session_paper(
            session_id,
            paper_id,
            user_status=user_status,
            selected=selected,
            tags=tags,
        )

    def generate_report(self, session_id: str) -> dict[str, Any]:
        detail = self.store.get_session_detail(session_id)
        papers = self._included_papers(detail["papers"])
        content = self._build_report(detail, papers)
        return self.store.create_report(session_id, content)

    def generate_report_stream(self, session_id: str) -> Iterator[dict[str, Any]]:
        detail = self.store.get_session_detail(session_id)
        papers = self._included_papers(detail["papers"])
        content = self._build_report(detail, papers)
        for chunk in self._chunk_text(content, 900):
            yield {"type": "report_chunk", "session_id": session_id, "content": chunk}
        report = self.store.create_report(session_id, content)
        yield {"type": "report_done", "session_id": session_id, "report": report}

    def derive_session(self, parent_session_id: str, topic: str) -> dict[str, Any]:
        parent = self.store.get_session(parent_session_id)
        child = self.store.create_session(topic, parent_session_id=parent["id"])
        return child

    def export_markdown(self, session_id: str) -> str:
        detail = self.store.get_session_detail(session_id)
        report = self.store.latest_report(session_id)
        if report:
            return report["content_markdown"]
        return self._build_report(detail, self._included_papers(detail["papers"]))

    def export_bibtex(self, session_id: str) -> str:
        detail = self.store.get_session_detail(session_id)
        entries = [self._bibtex_entry(paper) for paper in self._included_papers(detail["papers"])]
        return "\n\n".join(entry for entry in entries if entry).strip() + "\n"

    def _recall_and_screen(self, session_id: str, topic: str) -> None:
        self.store.update_session(session_id, status="searching")
        query_tasks, planner_notices = self.search.generate_query_plan(topic)
        recall_result = self.search.recall(
            topic,
            self.config.scholarly_candidate_limit,
            query_tasks=query_tasks,
            planner_notices=planner_notices,
        )
        self.store.update_session(
            session_id,
            queries=recall_result["queries"],
            metadata={
                "source_statuses": recall_result["source_statuses"],
                "skipped_sources": recall_result["skipped_sources"],
                "degradation_notices": recall_result["degradation_notices"],
            },
            status="screening",
        )
        screened = self.screening.screen(
            topic,
            recall_result["papers"],
            recall_result["queries"],
        )
        self.store.upsert_session_papers(session_id, screened, clear_existing=True)
        self.store.update_session(session_id, status="ready")

    def _included_papers(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        included = [
            paper
            for paper in papers
            if paper.get("selected") and paper.get("user_status") != "excluded"
        ]
        return sorted(included, key=lambda item: item.get("rank") or 9999)[: self.config.scholarly_selection_limit]

    def _build_report(self, detail: dict[str, Any], papers: list[dict[str, Any]]) -> str:
        topic = detail["topic"]
        if not papers:
            return (
                f"# {topic}\n\n"
                "## Report Positioning / 报告定位\n"
                "- 说明：当前会话还没有确认纳入的文献，因此暂时无法生成研究备忘录。\n"
                "- 行动：请先在工作台中筛选并确认论文，再生成报告。\n"
            )

        recent = [paper for paper in papers if (paper.get("year") or 0) >= 2024]
        high_related = [paper for paper in papers if paper.get("relevance_label") in {"must_read", "frontier"}]
        adjacent = [paper for paper in papers if paper.get("relevance_label") == "adjacent"]
        sources = sorted({str(paper.get("source") or "unknown") for paper in papers})
        years = [paper.get("year") for paper in papers if paper.get("year")]
        year_text = f"{min(years)}-{max(years)}" if years else "未知年份"

        lines = [
            f"# {topic}",
            "",
            "## Report Positioning / 报告定位",
            "- 说明：这是基于已确认文献的标题、摘要、年份、来源和引用信号整理的 AI 初步研究备忘录，不替代阅读全文。",
            "- 说明：它适合帮助你判断该方向是否已有稳定研究、哪些论文值得先读、下一轮应该继续往哪里检索。",
            "",
            "## Core Takeaways / 核心判断",
            f"- 判断：{self._takeaway_judgment(topic, papers, high_related, adjacent)}",
            f"- 证据：本次确认纳入 {len(papers)} 篇文献，其中 {len(recent)} 篇发表于 2024 年及以后，{len(high_related)} 篇被筛为核心或前沿。",
            f"- 推测：{self._takeaway_speculation(topic, recent, adjacent)}",
            "",
            "## Evidence Base / 证据基础",
            f"- 证据：当前证据集覆盖 {year_text}，来源包括 {', '.join(sources)}。",
            f"- 证据：检索重点集中在 {self._query_summary(detail.get('queries') or [])}。",
            f"- 证据：高优先级文献里，近期论文占比为 {len(recent)}/{len(papers)}，说明该方向仍有明显的新近演化信号。",
            "",
            "## Key Evidence / 关键证据",
        ]
        for paper in papers[:6]:
            lines.append(f"- 证据：{self._paper_line(paper)}")

        lines.extend(
            [
                "",
                "## What Looks Established / 已相对明确",
                self._landscape_paragraph(topic, papers),
                "",
                "## Gaps and Tensions / 空白与分歧",
                f"- 判断：{self._gaps_paragraph(topic, papers, adjacent)}",
                f"- 证据：{self._routes_paragraph(papers)}",
                f"- 推测：{self._frontier_paragraph(recent or papers[:5])}",
                "",
                "## Reading Priority / 建议优先阅读",
            ]
        )
        for index, paper in enumerate(papers[:10], start=1):
            lines.append(
                f"{index}. {paper.get('title')} ({paper.get('year') or 'n.d.'}) - "
                f"{paper.get('ai_reason') or '优先阅读摘要并判断是否需要阅读全文。'}"
            )
        lines.extend(
            [
                "",
                "## Next Actions / 下一步建议",
                f"- 行动：{self._next_action(topic, papers, adjacent)}",
                "- 行动：优先精读排名最靠前的 3-5 篇论文的 introduction、related work、method 和 experiment。",
                "- 行动：若准备继续检索，优先从方法名、数据集名、benchmark 名和作者近期工作继续扩展。",
                "",
                "## Data Notes / 数据说明",
                f"- 说明：确认文献数为 {len(papers)}。",
                f"- 说明：数据源状态为 {self._source_status_summary(detail)}。",
                "- 说明：当前版本不会自动下载 PDF，请通过论文页或开放 PDF 链接阅读全文。",
            ]
        )
        for notice in detail.get("degradation_notices") or []:
            lines.append(f"- 说明：{notice}")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _paper_line(paper: dict[str, Any]) -> str:
        title = str(paper.get("title") or "Untitled")
        year = paper.get("year") or "n.d."
        source = paper.get("source") or "unknown"
        reason = str(paper.get("ai_reason") or "与当前问题相关。")
        return f"{title} ({year}, {source}) - {reason}"

    @staticmethod
    def _takeaway_judgment(
        topic: str,
        papers: list[dict[str, Any]],
        high_related: list[dict[str, Any]],
        adjacent: list[dict[str, Any]],
    ) -> str:
        if adjacent and len(high_related) <= max(3, len(papers) // 3):
            return (
                f"围绕 `{topic}` 的直接高匹配研究仍偏少，当前更像是一个跨主题拼接中的新问题，"
                "需要通过旁支文献反推稳定术语和主流任务定义。"
            )
        if len(high_related) >= max(5, len(papers) // 2):
            return (
                f"围绕 `{topic}` 已经可以形成一组较稳定的核心阅读集合，"
                "下一步重点应从“是否已有成熟路线”转向“哪条路线最值得继续深入”。"
            )
        return (
            f"围绕 `{topic}` 已有一定数量的相关工作，但证据密度还没有高到足以直接下强结论，"
            "更适合先做结构化精读，再判断真正的研究空白。"
        )

    @staticmethod
    def _takeaway_speculation(
        topic: str,
        recent: list[dict[str, Any]],
        adjacent: list[dict[str, Any]],
    ) -> str:
        if adjacent:
            return (
                f"`{topic}` 很可能存在术语尚未稳定、问题定义跨域迁移或近期开源工作先出现而规范论文仍在跟进的情况。"
            )
        if len(recent) >= 5:
            return (
                f"`{topic}` 相关路线近两年仍在快速迭代，后续最容易发生变化的不是大方向本身，而是具体架构和评测范式。"
            )
        return (
            f"`{topic}` 后续更值得关注不同论文之间的任务设定和评测口径是否一致，而不是只看标题上的相似性。"
        )

    def _landscape_paragraph(self, topic: str, papers: list[dict[str, Any]]) -> str:
        years = [paper.get("year") for paper in papers if paper.get("year")]
        year_text = f"{min(years)}-{max(years)}" if years else "未知年份"
        sources = sorted({str(paper.get("source") or "unknown") for paper in papers})
        return (
            f"围绕 `{topic}`，当前候选集覆盖 {year_text} 的论文，来源包括 {', '.join(sources)}。"
            "从摘要信号看，第一步应先区分核心方法论文、survey/review、benchmark/leaderboard、"
            "以及与主题相邻但非直接命中的迁移研究。"
        )

    def _frontier_paragraph(self, papers: list[dict[str, Any]]) -> str:
        items = [
            f"`{paper.get('title')}` ({paper.get('year') or 'n.d.'})"
            for paper in papers[:5]
        ]
        return (
            "前沿判断主要依据年份、arXiv/预印本来源和相关性得分。建议优先检查这些论文的 introduction、"
            "related work 与实验设置："
            + "；".join(items)
            + "。"
        )

    def _routes_paragraph(self, papers: list[dict[str, Any]]) -> str:
        tags = []
        for paper in papers:
            tags.extend(paper.get("tags") or [])
        counter = {tag: tags.count(tag) for tag in sorted(set(tags))}
        if not counter:
            return "当前摘要不足以稳定划分技术路线，建议补充更多候选文献或阅读全文。"
        return (
            "可先按工作台标签拆分路线："
            + "，".join(f"{tag} ({count})" for tag, count in counter.items())
            + "。后续精读时应补充 method、dataset、metric、baseline 和 code availability。"
        )

    def _gaps_paragraph(self, topic: str, papers: list[dict[str, Any]], adjacent: list[dict[str, Any]]) -> str:
        if adjacent:
            return (
                f"直接命中 `{topic}` 的高相关论文可能不足，因此系统纳入了 {len(adjacent)} 篇旁支文献。"
                "这通常意味着该问题可能较新、跨领域或术语尚未稳定。建议下一轮从旁支文献中的方法名、"
                "数据集名和 benchmark 名派生新会话。"
            )
        return (
            "当前确认文献已经形成初步证据集，但仍需要阅读全文确认：问题定义是否一致、实验是否可比、"
            "是否存在数据泄漏或 benchmark 过拟合，以及近两年是否出现尚未高被引的新路线。"
        )

    @staticmethod
    def _next_action(topic: str, papers: list[dict[str, Any]], adjacent: list[dict[str, Any]]) -> str:
        if adjacent:
            return (
                f"以 `{topic}` 为中心，优先从当前旁支文献中抽取方法关键词、数据集名和作者名，重开一轮更窄的精确检索。"
            )
        if len(papers) >= 8:
            return (
                "先把高优先级论文按方法、评测、应用三类分组阅读，再判断你真正缺的是方法创新、任务空白还是评测空白。"
            )
        return (
            f"继续补足 `{topic}` 的证据集，尤其需要增加更近两年的 survey、benchmark 或 strongly-related system papers。"
        )

    @staticmethod
    def _query_summary(queries: list[Any]) -> str:
        if not queries:
            return "暂无检索式"
        if queries and isinstance(queries[0], str):
            return ", ".join(str(item) for item in queries)
        concepts = []
        for item in queries:
            if not isinstance(item, dict):
                continue
            concept = str(item.get("concept") or "").strip()
            count = item.get("result_count") or 0
            if concept:
                concepts.append(f"{concept}({count})")
        return ", ".join(concepts) or "暂无检索式"

    @staticmethod
    def _source_status_summary(detail: dict[str, Any]) -> str:
        statuses = detail.get("source_statuses") or {}
        if not isinstance(statuses, dict) or not statuses:
            return "未知"
        parts = []
        for source_name, status in statuses.items():
            parts.append(f"{source_name}={status}")
        return ", ".join(parts)

    @staticmethod
    def _compact_paper_event(paper: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": paper.get("title"),
            "year": paper.get("year"),
            "source": paper.get("source"),
            "final_score": paper.get("final_score"),
            "relevance_label": paper.get("relevance_label"),
            "ai_reason": paper.get("ai_reason"),
        }

    @staticmethod
    def _chunk_text(text: str, size: int) -> Iterator[str]:
        for index in range(0, len(text), size):
            yield text[index : index + size]

    @staticmethod
    def _escape_table(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    def _bibtex_entry(self, paper: dict[str, Any]) -> str:
        title = str(paper.get("title") or "Untitled")
        key = self._bibtex_key(paper)
        authors = " and ".join(paper.get("authors") or [])
        fields = {
            "title": title,
            "author": authors,
            "year": paper.get("year"),
            "journal": paper.get("venue"),
            "doi": paper.get("doi"),
            "url": paper.get("url") or paper.get("pdf_url"),
        }
        body = []
        for name, value in fields.items():
            if value:
                body.append(f"  {name} = {{{self._bibtex_escape(str(value))}}}")
        return "@article{" + key + ",\n" + ",\n".join(body) + "\n}"

    @staticmethod
    def _bibtex_key(paper: dict[str, Any]) -> str:
        authors = paper.get("authors") or []
        first = re.sub(r"[^A-Za-z0-9]", "", authors[0].split()[-1] if authors else "paper")
        year = paper.get("year") or "nd"
        title_token = re.sub(r"[^A-Za-z0-9]", "", str(paper.get("title") or "work").split()[0])
        return f"{first}{year}{title_token}"[:48] or "paper"

    @staticmethod
    def _bibtex_escape(value: str) -> str:
        return value.replace("{", "\\{").replace("}", "\\}")
