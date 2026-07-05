"""SQLite persistence for scholarly research sessions."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.scholarly_contracts import default_session_metadata


def utc_now() -> str:
    """Return an ISO timestamp in UTC."""

    return datetime.now(timezone.utc).isoformat()


def make_id(prefix: str) -> str:
    """Create a compact identifier with a readable prefix."""

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_title(title: str) -> str:
    """Normalize a paper title for fallback de-duplication."""

    text = re.sub(r"\s+", " ", (title or "").strip().lower())
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", text)
    return text


def paper_key(paper: dict[str, Any]) -> str:
    """Build a stable cross-source key for a paper."""

    doi = str(paper.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"

    arxiv_id = str(paper.get("arxiv_id") or "").strip().lower()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"

    semantic_id = str(paper.get("semantic_scholar_id") or "").strip()
    if semantic_id:
        return f"s2:{semantic_id}"

    return f"title:{normalize_title(str(paper.get('title') or 'untitled'))}"


class ScholarlyStore:
    """Small repository wrapping session, paper, and report persistence."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if self.db_path.parent and str(self.db_path.parent) not in {"", "."}:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_sessions (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    queries_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    parent_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    paper_key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    year INTEGER,
                    authors_json TEXT NOT NULL DEFAULT '[]',
                    venue TEXT,
                    doi TEXT,
                    arxiv_id TEXT,
                    semantic_scholar_id TEXT,
                    openalex_id TEXT,
                    url TEXT,
                    pdf_url TEXT,
                    source TEXT,
                    citation_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_papers (
                    session_id TEXT NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
                    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                    rank INTEGER NOT NULL DEFAULT 9999,
                    selected INTEGER NOT NULL DEFAULT 0,
                    relevance_score REAL NOT NULL DEFAULT 0,
                    novelty_score REAL NOT NULL DEFAULT 0,
                    final_score REAL NOT NULL DEFAULT 0,
                    relevance_label TEXT NOT NULL DEFAULT 'candidate',
                    ai_reason TEXT NOT NULL DEFAULT '',
                    origin_json TEXT NOT NULL DEFAULT '[]',
                    user_status TEXT NOT NULL DEFAULT 'candidate',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, paper_id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
                    content_markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(
                conn,
                table="research_sessions",
                column="metadata_json",
                definition="TEXT NOT NULL DEFAULT '{}'",
            )
            self._ensure_column(
                conn,
                table="session_papers",
                column="origin_json",
                definition="TEXT NOT NULL DEFAULT '[]'",
            )

    def create_session(self, topic: str, parent_session_id: str | None = None) -> dict[str, Any]:
        session_id = make_id("ses")
        now = utc_now()
        metadata = json.dumps(default_session_metadata(), ensure_ascii=False)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO research_sessions
                    (id, topic, status, queries_json, metadata_json, parent_session_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, topic, "created", "[]", metadata, parent_session_id, now, now),
            )
        return self.get_session(session_id)

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        queries: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        parts: list[str] = ["updated_at = ?"]
        values: list[Any] = [utc_now()]
        if status is not None:
            parts.append("status = ?")
            values.append(status)
        if queries is not None:
            parts.append("queries_json = ?")
            values.append(json.dumps(queries, ensure_ascii=False))
        if metadata is not None:
            parts.append("metadata_json = ?")
            values.append(
                json.dumps(default_session_metadata(metadata), ensure_ascii=False)
            )
        values.append(session_id)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"UPDATE research_sessions SET {', '.join(parts)} WHERE id = ?",
                values,
            )

    def list_sessions(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT s.*,
                    (SELECT COUNT(*) FROM session_papers sp WHERE sp.session_id = s.id) AS paper_count,
                    (SELECT COUNT(*) FROM session_papers sp WHERE sp.session_id = s.id AND sp.selected = 1) AS selected_count,
                    (SELECT COUNT(*) FROM reports r WHERE r.session_id = s.id) AS report_count
                FROM research_sessions s
                ORDER BY s.created_at DESC
                """
            ).fetchall()
        return [self._session_row_to_dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                """
                SELECT s.*,
                    (SELECT COUNT(*) FROM session_papers sp WHERE sp.session_id = s.id) AS paper_count,
                    (SELECT COUNT(*) FROM session_papers sp WHERE sp.session_id = s.id AND sp.selected = 1) AS selected_count,
                    (SELECT COUNT(*) FROM reports r WHERE r.session_id = s.id) AS report_count
                FROM research_sessions s
                WHERE s.id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._session_row_to_dict(row)

    def get_session_detail(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        session["papers"] = self.list_session_papers(session_id)
        session["reports"] = self.list_reports(session_id)
        return session

    def delete_session(self, session_id: str) -> None:
        self.get_session(session_id)
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))

    def upsert_session_papers(
        self,
        session_id: str,
        papers: list[dict[str, Any]],
        *,
        clear_existing: bool = False,
    ) -> None:
        now = utc_now()
        with closing(self._connect()) as conn, conn:
            if clear_existing:
                conn.execute("DELETE FROM session_papers WHERE session_id = ?", (session_id,))

            for paper in papers:
                key = paper_key(paper)
                existing = conn.execute(
                    "SELECT id FROM papers WHERE paper_key = ?",
                    (key,),
                ).fetchone()
                paper_id = existing["id"] if existing else make_id("pap")
                authors = paper.get("authors") or []
                tags = paper.get("tags") or []
                origins = paper.get("query_matches") or paper.get("origins") or []
                values = (
                    paper_id,
                    key,
                    str(paper.get("title") or "Untitled").strip(),
                    str(paper.get("abstract") or "").strip(),
                    self._to_int(paper.get("year")),
                    json.dumps(authors, ensure_ascii=False),
                    paper.get("venue"),
                    paper.get("doi"),
                    paper.get("arxiv_id"),
                    paper.get("semantic_scholar_id"),
                    paper.get("openalex_id"),
                    paper.get("url"),
                    paper.get("pdf_url"),
                    paper.get("source"),
                    self._to_int(paper.get("citation_count")) or 0,
                    now,
                    now,
                )
                if existing:
                    conn.execute(
                        """
                        UPDATE papers SET
                            title = ?, abstract = COALESCE(NULLIF(?, ''), abstract),
                            year = COALESCE(?, year), authors_json = ?,
                            venue = COALESCE(?, venue), doi = COALESCE(?, doi),
                            arxiv_id = COALESCE(?, arxiv_id),
                            semantic_scholar_id = COALESCE(?, semantic_scholar_id),
                            openalex_id = COALESCE(?, openalex_id),
                            url = COALESCE(?, url), pdf_url = COALESCE(?, pdf_url),
                            source = COALESCE(?, source),
                            citation_count = MAX(COALESCE(citation_count, 0), ?),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        values[2:15] + (now, paper_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO papers (
                            id, paper_key, title, abstract, year, authors_json, venue,
                            doi, arxiv_id, semantic_scholar_id, openalex_id, url, pdf_url,
                            source, citation_count, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        values,
                    )

                conn.execute(
                    """
                    INSERT INTO session_papers (
                        session_id, paper_id, rank, selected, relevance_score, novelty_score,
                        final_score, relevance_label, ai_reason, origin_json, user_status, tags_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, paper_id) DO UPDATE SET
                        rank = excluded.rank,
                        selected = excluded.selected,
                        relevance_score = excluded.relevance_score,
                        novelty_score = excluded.novelty_score,
                        final_score = excluded.final_score,
                        relevance_label = excluded.relevance_label,
                        ai_reason = excluded.ai_reason,
                        origin_json = excluded.origin_json,
                        tags_json = excluded.tags_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session_id,
                        paper_id,
                        self._to_int(paper.get("rank")) or 9999,
                        1 if paper.get("selected") else 0,
                        float(paper.get("relevance_score") or 0),
                        float(paper.get("novelty_score") or 0),
                        float(paper.get("final_score") or 0),
                        str(paper.get("relevance_label") or "candidate"),
                        str(paper.get("ai_reason") or ""),
                        json.dumps(origins, ensure_ascii=False),
                        str(paper.get("user_status") or ("included" if paper.get("selected") else "candidate")),
                        json.dumps(tags, ensure_ascii=False),
                        now,
                        now,
                    ),
                )

    def list_session_papers(self, session_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                """
                SELECT p.*, sp.rank, sp.selected, sp.relevance_score, sp.novelty_score,
                       sp.final_score, sp.relevance_label, sp.ai_reason, sp.origin_json, sp.user_status,
                       sp.tags_json
                FROM session_papers sp
                JOIN papers p ON p.id = sp.paper_id
                WHERE sp.session_id = ?
                ORDER BY sp.selected DESC, sp.final_score DESC, sp.rank ASC, p.year DESC
                """,
                (session_id,),
            ).fetchall()
        return [self._paper_row_to_dict(row) for row in rows]

    def update_session_paper(
        self,
        session_id: str,
        paper_id: str,
        *,
        user_status: str | None = None,
        selected: bool | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        parts = ["updated_at = ?"]
        values: list[Any] = [utc_now()]
        if user_status is not None:
            parts.append("user_status = ?")
            values.append(user_status)
        if selected is not None:
            parts.append("selected = ?")
            values.append(1 if selected else 0)
        if tags is not None:
            parts.append("tags_json = ?")
            values.append(json.dumps(tags, ensure_ascii=False))
        values.extend([session_id, paper_id])
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"""
                UPDATE session_papers
                SET {', '.join(parts)}
                WHERE session_id = ? AND paper_id = ?
                """,
                values,
            )
        paper = next(
            (item for item in self.list_session_papers(session_id) if item["id"] == paper_id),
            None,
        )
        if paper is None:
            raise KeyError(paper_id)
        return paper

    def create_report(self, session_id: str, content_markdown: str) -> dict[str, Any]:
        report_id = make_id("rep")
        now = utc_now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO reports (id, session_id, content_markdown, created_at) VALUES (?, ?, ?, ?)",
                (report_id, session_id, content_markdown, now),
            )
            conn.execute(
                "UPDATE research_sessions SET status = ?, updated_at = ? WHERE id = ?",
                ("reported", now, session_id),
            )
        return {"id": report_id, "session_id": session_id, "content_markdown": content_markdown, "created_at": now}

    def list_reports(self, session_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn, conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_report(self, session_id: str) -> dict[str, Any] | None:
        reports = self.list_reports(session_id)
        return reports[0] if reports else None

    def derive_session(self, parent_session_id: str, topic: str) -> dict[str, Any]:
        self.get_session(parent_session_id)
        return self.create_session(topic, parent_session_id=parent_session_id)

    def _session_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata = default_session_metadata(metadata if isinstance(metadata, dict) else {})
        return {
            "id": row["id"],
            "topic": row["topic"],
            "status": row["status"],
            "queries": json.loads(row["queries_json"] or "[]"),
            "metadata": metadata,
            "source_statuses": metadata["source_statuses"],
            "skipped_sources": metadata["skipped_sources"],
            "degradation_notices": metadata["degradation_notices"],
            "frontier_mode": bool(metadata["frontier_mode"]),
            "frontier_reason": metadata["frontier_reason"],
            "metrics": metadata["metrics"],
            "parent_session_id": row["parent_session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "paper_count": row["paper_count"] if "paper_count" in row.keys() else 0,
            "selected_count": row["selected_count"] if "selected_count" in row.keys() else 0,
            "report_count": row["report_count"] if "report_count" in row.keys() else 0,
        }

    def _paper_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "abstract": row["abstract"] or "",
            "year": row["year"],
            "authors": json.loads(row["authors_json"] or "[]"),
            "venue": row["venue"],
            "doi": row["doi"],
            "arxiv_id": row["arxiv_id"],
            "semantic_scholar_id": row["semantic_scholar_id"],
            "openalex_id": row["openalex_id"],
            "url": row["url"],
            "pdf_url": row["pdf_url"],
            "source": row["source"],
            "citation_count": row["citation_count"] or 0,
            "rank": row["rank"],
            "selected": bool(row["selected"]),
            "relevance_score": row["relevance_score"],
            "novelty_score": row["novelty_score"],
            "final_score": row["final_score"],
            "relevance_label": row["relevance_label"],
            "ai_reason": row["ai_reason"],
            "query_matches": json.loads(row["origin_json"] or "[]"),
            "user_status": row["user_status"],
            "tags": json.loads(row["tags_json"] or "[]"),
        }

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        known = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}
        if column not in known:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
