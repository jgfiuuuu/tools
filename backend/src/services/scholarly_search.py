"""Scholarly literature planning, search, and screening services."""

from __future__ import annotations

import html
import json
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests
from openai import OpenAI

from config import Configuration
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

    def generate_query_plan(self, topic: str) -> tuple[list[dict[str, Any]], list[str]]:
        """Build concept-first scholarly query subtasks."""

        notices: list[str] = []
        rule_plan = self._rule_query_plan(topic)

        if not self._should_try_llm(topic):
            return rule_plan, notices

        llm_plan = self._llm_query_plan(topic, rule_plan)
        if llm_plan:
            return llm_plan, notices

        notices.append("LLM 检索式规划不可用，已回退到规则拆词。")
        return rule_plan, notices

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
        per_variant = max(6, min(12, math.ceil(target / 6)))
        notices = list(planner_notices or [])
        if query_tasks is None:
            query_tasks, generated_notices = self.generate_query_plan(topic)
            notices.extend(generated_notices)
        raw_papers: list[dict[str, Any]] = []
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

        for task in query_tasks:
            task_results = 0
            variant_statuses = []
            for variant in task.get("variants") or []:
                variant_results = self._run_variant(
                    task=task,
                    variant=variant,
                    per_variant=per_variant,
                    raw_papers=raw_papers,
                    source_counters=source_counters,
                    source_statuses=source_statuses,
                )
                task_results += variant_results
                variant_statuses.append(str(variant.get("status") or "idle"))
            task["result_count"] = task_results
            task["status"] = self._summarize_variant_statuses(variant_statuses)

        deduped = self._dedupe(raw_papers)
        final_statuses = self._finalize_source_statuses(source_statuses, source_counters)
        notices.extend(self._build_source_notices(final_statuses))
        return {
            "queries": query_tasks,
            "papers": deduped[:target],
            "degradation_notices": unique_strings(notices),
            "source_statuses": final_statuses,
            "skipped_sources": skipped_sources,
        }

    def _run_variant(
        self,
        *,
        task: dict[str, Any],
        variant: dict[str, Any],
        per_variant: int,
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
            results, error = self._search_source(source_name, query_text, per_variant)
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
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query={search_query}"
            f"&start=0&max_results={limit}"
            "&sortBy=relevance&sortOrder=descending"
        )
        response, error = self._request(url)
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
    ) -> tuple[requests.Response, str | None]:
        error_message = ""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
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
    ) -> list[dict[str, Any]] | None:
        client = self._build_llm_client()
        model = self.config.resolved_model()
        if client is None or not model:
            return None

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
            response = client.chat.completions.create(
                model=model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"topic": topic, "seed_plan": seed_payload},
                            ensure_ascii=False,
                        ),
                    },
                ],
            )
        except Exception as exc:  # pragma: no cover - depends on external LLM
            logger.warning("LLM query planning failed: %s", exc)
            return None

        content = response.choices[0].message.content if response.choices else None
        if not content:
            return None

        payload = self._extract_json_payload(content)
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(tasks, list):
            return None

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
        return planned[:5] or None

    def _build_llm_client(self) -> OpenAI | None:
        model = self.config.resolved_model()
        if not model:
            return None

        provider = (self.config.llm_provider or "").strip().lower()
        api_key = self.config.llm_api_key
        base_url = self.config.llm_base_url
        if provider == "ollama":
            base_url = self.config.sanitized_ollama_url()
            api_key = api_key or "ollama"
        elif provider == "lmstudio":
            base_url = self.config.lmstudio_base_url
            api_key = api_key or "lmstudio"
        elif not base_url:
            return None

        try:
            return OpenAI(base_url=base_url, api_key=api_key or "placeholder")
        except Exception:  # pragma: no cover - client init is trivial
            return None

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
                    "status": "pending",
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
            "status": "pending",
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

    def _build_arxiv_query(self, query: str) -> str:
        tokens = query.split()
        if len(tokens) <= 2:
            return quote_plus(f'all:"{query}"')

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
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

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
        """Score papers with transparent relevance and frontier heuristics."""

        query_tasks = query_tasks or []
        topic_tokens = Counter(
            tokenize(
                " ".join(
                    [
                        topic,
                        *[
                            " ".join(task.get("base_terms") or [])
                            for task in query_tasks
                        ],
                    ]
                )
            )
        )
        scored: list[dict[str, Any]] = []
        for paper in papers:
            title = str(paper.get("title") or "")
            abstract = str(paper.get("abstract") or "")
            combined_tokens = Counter(tokenize(f"{title} {abstract}"))
            overlap = sum(
                min(count, combined_tokens[token])
                for token, count in topic_tokens.items()
            )
            relevance = overlap / max(1, len(topic_tokens))
            title_tokens = tokenize(title)
            title_overlap = sum(
                1 for token in topic_tokens if token in title_tokens
            )
            relevance += min(0.22, title_overlap * 0.04)

            query_matches = paper.get("query_matches") or []
            query_bonus = self._query_match_bonus(query_matches)
            year = paper.get("year")
            novelty = self._novelty_score(year)
            citation = min(
                0.12,
                math.log10((paper.get("citation_count") or 0) + 1) / 12,
            )
            final = min(
                1.0,
                relevance * 0.72 + query_bonus + novelty * 0.10 + citation,
            )

            label = self._label(relevance, final)
            tags = self._tags(paper, relevance, novelty, query_matches)
            reason = self._reason(paper, relevance, novelty, label, query_matches)
            item = dict(paper)
            item.update(
                {
                    "relevance_score": round(relevance, 3),
                    "novelty_score": round(novelty, 3),
                    "final_score": round(final, 3),
                    "relevance_label": label,
                    "ai_reason": reason,
                    "tags": tags,
                }
            )
            scored.append(item)

        scored.sort(
            key=lambda item: (item["final_score"], item.get("year") or 0),
            reverse=True,
        )
        selected_limit = self.config.scholarly_selection_limit
        strict = [
            item
            for item in scored
            if item["relevance_label"] in {"must_read", "frontier"}
        ]
        if len(strict) >= selected_limit:
            selected_keys = {paper_key(item) for item in strict[:selected_limit]}
        else:
            selected_keys = {paper_key(item) for item in scored[:selected_limit]}

        for rank, item in enumerate(scored, start=1):
            item["rank"] = rank
            item["selected"] = paper_key(item) in selected_keys
            item["user_status"] = "included" if item["selected"] else "candidate"
            if item["selected"] and item["relevance_label"] == "candidate":
                item["relevance_label"] = "adjacent"
                item["tags"] = sorted(set(item["tags"] + ["旁支补充"]))
        return scored

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
            tags.append("高被引")
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
            "must_read": "与问题高度贴合，可作为核心阅读对象。",
            "frontier": "与主题相关且有较强的新近性信号。",
            "background": "适合作为背景或技术脉络补充。",
            "candidate": "直接相关性有限，暂作为候选材料。",
        }.get(label, "可作为候选材料。")
        return (
            f"{title}（{year}）{label_text}{concept_text}"
            f"相关性={relevance:.2f}，前沿性={novelty:.2f}。"
        )
