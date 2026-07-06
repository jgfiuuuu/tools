"""Fulltext acquisition, PDF upload handling, and text extraction for scholarly reports."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from config import Configuration
from services.scholarly_store import ScholarlyStore, utc_now

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency at runtime
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency at runtime
    PdfReader = None


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text from HTML while skipping scripts and styles."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if data and data.strip():
            self._parts.append(data.strip())
            self._parts.append(" ")

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()


@dataclass(slots=True)
class ResolvedPaperFulltext:
    """Normalized paper text used for downstream evidence-card extraction."""

    paper_id: str
    title: str
    evidence_level: str
    fulltext_source: str
    text: str
    extraction_status: str
    original_filename: str | None = None


class ScholarlyFulltextService:
    """Resolve uploaded or open-access fulltext content for one paper."""

    def __init__(self, config: Configuration, store: ScholarlyStore) -> None:
        self.config = config
        self.store = store
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "CiteWeave Scholarly Fulltext/0.1",
                "Accept": "text/html,application/pdf,application/xhtml+xml,*/*",
            }
        )
        self.timeout = 20
        self.artifact_root = self._resolve_artifact_root(
            Path(config.scholarly_artifact_dir),
            Path(config.scholarly_db_path),
        )
        self.upload_root = self.artifact_root / "uploads"
        self.cache_root = self.artifact_root / "cache"
        self.text_root = self.artifact_root / "text"
        for path in (self.upload_root, self.cache_root, self.text_root):
            path.mkdir(parents=True, exist_ok=True)

    def upload_pdf(
        self,
        *,
        paper_id: str,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        """Persist an uploaded PDF and its extracted text for one paper."""

        safe_name = self._sanitize_filename(filename or f"{paper_id}.pdf")
        target_dir = self.upload_root / paper_id
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / safe_name
        file_path.write_bytes(content)

        extracted = self._extract_pdf_text(content)
        text_path: Path | None = None
        status = "completed" if extracted else "parse_failed"
        if extracted:
            text_path = self._write_text_artifact(paper_id, "uploaded_pdf", extracted)

        self.store.upsert_paper_fulltext(
            paper_id,
            source_type="uploaded_pdf",
            extraction_status=status,
            original_filename=safe_name,
            file_path=str(file_path),
            text_path=str(text_path) if text_path else None,
            source_ref=safe_name,
            text_char_count=len(extracted),
        )
        record = self.store.get_paper_fulltext(paper_id)
        return record or {}

    def ensure_fulltext(self, paper: dict[str, Any]) -> ResolvedPaperFulltext:
        """Ensure one paper has usable fulltext without falling back to abstracts."""

        paper_id = str(paper.get("id") or "")
        title = str(paper.get("title") or "Untitled")
        resolved = self._resolve_available_fulltext(paper, paper_id, title)
        if resolved is not None:
            return resolved
        if self._has_open_access_candidate(paper):
            raise ValueError("未能获取可用的开放全文。")
        raise ValueError("当前论文没有可用的开放全文入口。")

    def resolve_paper(self, paper: dict[str, Any]) -> ResolvedPaperFulltext:
        """Resolve the best available text for a paper with fallback ordering."""

        paper_id = str(paper.get("id") or "")
        title = str(paper.get("title") or "Untitled")
        resolved = self._resolve_available_fulltext(paper, paper_id, title)
        if resolved is not None:
            return resolved

        record = self.store.get_paper_fulltext(paper_id)
        if record and record.get("source_type") == "uploaded_pdf":
            original_filename = record.get("original_filename")
        elif isinstance(record, dict):
            original_filename = record.get("original_filename")
        else:
            original_filename = None
        fallback_text = str(paper.get("abstract") or "").strip()
        if not fallback_text:
            fallback_text = str(paper.get("ai_reason") or "").strip()
        return ResolvedPaperFulltext(
            paper_id=paper_id,
            title=title,
            evidence_level="abstract",
            fulltext_source="abstract_only",
            text=fallback_text,
            extraction_status="missing",
            original_filename=original_filename,
        )

    def _resolve_available_fulltext(
        self,
        paper: dict[str, Any],
        paper_id: str,
        title: str,
    ) -> ResolvedPaperFulltext | None:
        """Resolve uploaded, cached, or remote fulltext in priority order."""

        record = self.store.get_paper_fulltext(paper_id)
        if record and record.get("source_type") == "uploaded_pdf":
            uploaded = self._resolve_uploaded_record(record, paper_id, title)
            if uploaded is not None:
                return uploaded

        if record and record.get("source_type") != "uploaded_pdf":
            cached = self._read_cached_record(record, paper_id, title)
            if cached is not None:
                return cached

        auto_fulltext = self._resolve_open_access_fulltext(paper)
        if auto_fulltext is not None:
            return auto_fulltext
        return None

    def close(self) -> None:
        """Release the shared HTTP session."""

        self.session.close()

    def _resolve_uploaded_record(
        self,
        record: dict[str, Any],
        paper_id: str,
        title: str,
    ) -> ResolvedPaperFulltext | None:
        text = self._read_text(record.get("text_path"))
        if text:
            return ResolvedPaperFulltext(
                paper_id=paper_id,
                title=title,
                evidence_level="fulltext",
                fulltext_source="uploaded_pdf",
                text=text,
                extraction_status=str(record.get("extraction_status") or "completed"),
                original_filename=record.get("original_filename"),
            )

        file_path = record.get("file_path")
        if file_path and Path(file_path).exists():
            extracted = self._extract_pdf_text(Path(file_path).read_bytes())
            if extracted:
                text_path = self._write_text_artifact(paper_id, "uploaded_pdf", extracted)
                self.store.upsert_paper_fulltext(
                    paper_id,
                    source_type="uploaded_pdf",
                    extraction_status="completed",
                    original_filename=record.get("original_filename"),
                    file_path=file_path,
                    text_path=str(text_path),
                    source_ref=record.get("source_ref"),
                    text_char_count=len(extracted),
                )
                return ResolvedPaperFulltext(
                    paper_id=paper_id,
                    title=title,
                    evidence_level="fulltext",
                    fulltext_source="uploaded_pdf",
                    text=extracted,
                    extraction_status="completed",
                    original_filename=record.get("original_filename"),
                )
        return None

    def _read_cached_record(
        self,
        record: dict[str, Any],
        paper_id: str,
        title: str,
    ) -> ResolvedPaperFulltext | None:
        text = self._read_text(record.get("text_path"))
        if not text:
            return None
        return ResolvedPaperFulltext(
            paper_id=paper_id,
            title=title,
            evidence_level="fulltext",
            fulltext_source=str(record.get("source_type") or "open_web"),
            text=text,
            extraction_status=str(record.get("extraction_status") or "completed"),
            original_filename=record.get("original_filename"),
        )

    def _resolve_open_access_fulltext(
        self,
        paper: dict[str, Any],
    ) -> ResolvedPaperFulltext | None:
        paper_id = str(paper.get("id") or "")
        title = str(paper.get("title") or "Untitled")

        pdf_url = str(paper.get("pdf_url") or "").strip()
        if pdf_url:
            extracted = self._fetch_pdf_text(pdf_url, paper_id)
            if extracted:
                return ResolvedPaperFulltext(
                    paper_id=paper_id,
                    title=title,
                    evidence_level="fulltext",
                    fulltext_source="open_pdf",
                    text=extracted,
                    extraction_status="completed",
                )

        if paper.get("arxiv_id"):
            arxiv_url = f"https://arxiv.org/html/{paper['arxiv_id']}"
            extracted = self._fetch_html_text(arxiv_url)
            if extracted:
                self._persist_auto_fulltext(
                    paper_id,
                    source_type="arxiv_html",
                    source_ref=arxiv_url,
                    text=extracted,
                )
                return ResolvedPaperFulltext(
                    paper_id=paper_id,
                    title=title,
                    evidence_level="fulltext",
                    fulltext_source="arxiv_html",
                    text=extracted,
                    extraction_status="completed",
                )

        paper_url = str(paper.get("url") or "").strip()
        if paper_url:
            extracted = self._fetch_open_url(paper_url, paper_id)
            if extracted is not None:
                return ResolvedPaperFulltext(
                    paper_id=paper_id,
                    title=title,
                    evidence_level="fulltext",
                    fulltext_source=extracted["source_type"],
                    text=extracted["text"],
                    extraction_status="completed",
                )

        return None

    @staticmethod
    def _has_open_access_candidate(paper: dict[str, Any]) -> bool:
        return any(
            str(paper.get(field) or "").strip()
            for field in ("pdf_url", "url", "arxiv_id")
        )

    def _fetch_open_url(
        self,
        url: str,
        paper_id: str,
    ) -> dict[str, str] | None:
        if self._should_skip_remote_fetch(url):
            return None
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            logger.info("Open webpage fetch failed for %s: %s", url, exc)
            return None

        content_type = str(response.headers.get("content-type") or "").lower()
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            text = self._extract_pdf_text(response.content)
            if text:
                self._persist_auto_fulltext(
                    paper_id,
                    source_type="open_pdf",
                    source_ref=url,
                    text=text,
                    binary=response.content,
                )
                return {"source_type": "open_pdf", "text": text}
            return None

        text = self._extract_html_text(response.text)
        if not text:
            return None
        self._persist_auto_fulltext(
            paper_id,
            source_type="open_web",
            source_ref=url,
            text=text,
        )
        return {"source_type": "open_web", "text": text}

    def _fetch_pdf_text(self, url: str, paper_id: str) -> str | None:
        if self._should_skip_remote_fetch(url):
            return None
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            logger.info("Open PDF fetch failed for %s: %s", url, exc)
            return None

        text = self._extract_pdf_text(response.content)
        if not text:
            return None
        self._persist_auto_fulltext(
            paper_id,
            source_type="open_pdf",
            source_ref=url,
            text=text,
            binary=response.content,
        )
        return text

    def _persist_auto_fulltext(
        self,
        paper_id: str,
        *,
        source_type: str,
        source_ref: str,
        text: str,
        binary: bytes | None = None,
    ) -> None:
        file_path: str | None = None
        if binary:
            suffix = Path(urlparse(source_ref).path).suffix or ".pdf"
            file_path = str(self._write_binary_artifact(paper_id, source_type, binary, suffix))
        text_path = self._write_text_artifact(paper_id, source_type, text)
        self.store.upsert_paper_fulltext(
            paper_id,
            source_type=source_type,
            extraction_status="completed",
            original_filename=Path(urlparse(source_ref).path).name or None,
            file_path=file_path,
            text_path=str(text_path),
            source_ref=source_ref,
            text_char_count=len(text),
        )

    @staticmethod
    def _resolve_artifact_root(path: Path, db_path: Path) -> Path:
        if path.is_absolute():
            return path
        db_root = db_path.parent.resolve()
        candidate = (Path.cwd() / path).resolve()
        if candidate.exists():
            return candidate
        return (db_root / path).resolve()

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "paper.pdf").strip("._")
        if not cleaned.lower().endswith(".pdf"):
            cleaned = f"{cleaned or 'paper'}.pdf"
        return cleaned or "paper.pdf"

    @staticmethod
    def _should_skip_remote_fetch(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in {"example.com", "www.example.com", "localhost", "127.0.0.1"}

    def _write_binary_artifact(
        self,
        paper_id: str,
        source_type: str,
        content: bytes,
        suffix: str,
    ) -> Path:
        target_dir = self.cache_root / paper_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{source_type}{suffix}"
        target_path.write_bytes(content)
        return target_path

    def _write_text_artifact(self, paper_id: str, source_type: str, text: str) -> Path:
        target_dir = self.text_root / paper_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{source_type}.txt"
        target_path.write_text(text.strip() + "\n", encoding="utf-8")
        return target_path

    @staticmethod
    def _read_text(path_value: Any) -> str:
        path_text = str(path_value or "").strip()
        if not path_text:
            return ""
        path = Path(path_text)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _extract_pdf_text(self, content: bytes) -> str:
        extracted = self._extract_pdf_text_with_pypdf(content)
        if extracted:
            return extracted
        return self._extract_pdf_text_with_regex(content)

    def _extract_pdf_text_with_pypdf(self, content: bytes) -> str:
        if PdfReader is None:
            return ""
        try:  # pragma: no cover - depends on optional runtime dependency
            reader = PdfReader(io.BytesIO(content))
            chunks = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            logger.info("pypdf extraction failed: %s", exc)
            return ""
        return self._normalize_text("\n\n".join(chunks), min_length=20)

    def _extract_pdf_text_with_regex(self, content: bytes) -> str:
        decoded = content.decode("latin-1", errors="ignore")
        matches = re.findall(r"\(([^()]*)\)\s*Tj", decoded)
        if not matches:
            array_matches = re.findall(r"\[(.*?)\]\s*TJ", decoded, flags=re.DOTALL)
            for entry in array_matches:
                matches.extend(re.findall(r"\(([^()]*)\)", entry))
        return self._normalize_text(
            " ".join(self._decode_pdf_literal(item) for item in matches),
            min_length=20,
        )

    @staticmethod
    def _decode_pdf_literal(value: str) -> str:
        text = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\n", " ")
        text = text.replace(r"\r", " ").replace(r"\t", " ").replace(r"\\", "\\")
        return text

    def _fetch_html_text(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - network dependent
            logger.info("HTML fulltext fetch failed for %s: %s", url, exc)
            return ""
        return self._extract_html_text(response.text)

    def _extract_html_text(self, html: str) -> str:
        parser = _HTMLTextExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return self._normalize_text(parser.text())

    @staticmethod
    def _normalize_text(text: str, min_length: int = 120) -> str:
        compact = re.sub(r"[ \t]+", " ", text or "")
        compact = re.sub(r"\n{3,}", "\n\n", compact)
        compact = compact.replace("\x00", " ").strip()
        if len(compact) < min_length:
            return ""
        return compact
