from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .domain import CorrectionPayload, JobStatus, ProjectState, utc_now


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'project_data',
                    proposal_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    reviewed_by TEXT,
                    review_comment TEXT,
                    reviewed_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(corrections)").fetchall()}
            migrations = {
                "category": "ALTER TABLE corrections ADD COLUMN category TEXT NOT NULL DEFAULT 'project_data'",
                "proposal_json": "ALTER TABLE corrections ADD COLUMN proposal_json TEXT NOT NULL DEFAULT '{}'",
                "reviewed_by": "ALTER TABLE corrections ADD COLUMN reviewed_by TEXT",
                "review_comment": "ALTER TABLE corrections ADD COLUMN review_comment TEXT",
                "reviewed_at": "ALTER TABLE corrections ADD COLUMN reviewed_at TEXT",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    conn.execute(statement)

    def create(self, state: ProjectState) -> None:
        payload = state.model_dump_json()
        with self._lock, self.connect() as conn:
            conn.execute(
                "INSERT INTO jobs(id,status,revision,state_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (state.job_id, state.status, state.revision, payload, state.created_at, state.updated_at),
            )

    def save(self, state: ProjectState) -> None:
        state.touch()
        with self._lock, self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, revision=?, state_json=?, updated_at=? WHERE id=?",
                (state.status, state.revision, state.model_dump_json(), state.updated_at, state.job_id),
            )

    def get(self, job_id: str) -> ProjectState | None:
        with self.connect() as conn:
            row = conn.execute("SELECT state_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        return ProjectState.model_validate_json(row["state_json"]) if row else None

    def list(self, limit: int = 50) -> list[ProjectState]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT state_json FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ProjectState.model_validate_json(row["state_json"]) for row in rows]

    def delete(self, job_id: str) -> None:
        with self._lock, self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def add_corrections(self, job_id: str, revision: int, corrections: list[CorrectionPayload]) -> None:
        now = utc_now()
        rows = []
        for item in corrections:
            category = self._classify_correction(item)
            proposal = {
                "category": category,
                "scope": item.scope,
                "trigger": {"artifact": item.artifact, "location": item.location, "reason": item.reason},
                "proposed_change": f"Use {item.expected_value!r} instead of {item.current_value!r} at {item.location}",
                "automatic_knowledge_edit": False,
                "regression_required": item.scope != "project",
            }
            rows.append((job_id, revision, item.model_dump_json(), category, json.dumps(proposal, ensure_ascii=False), now))
        with self._lock, self.connect() as conn:
            conn.executemany(
                "INSERT INTO corrections(job_id,revision,payload_json,category,proposal_json,created_at) VALUES(?,?,?,?,?,?)",
                rows,
            )

    @staticmethod
    def _classify_correction(item: CorrectionPayload) -> str:
        text = f"{item.artifact} {item.location} {item.reason}".lower()
        if any(token in text for token in ("шаблон", "excel", "xlsx", "формул")):
            return "template_defect"
        if any(token in text for token in ("извлеч", "распоз", "ocr", "прочитал")):
            return "extraction_defect"
        if item.scope == "customer":
            return "customer_or_branch_rule"
        if item.scope == "global":
            return "general_rule"
        return "project_data"

    def list_corrections(self, job_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM corrections"
        params: tuple[Any, ...] = ()
        if job_id:
            query += " WHERE job_id=?"
            params = (job_id,)
        query += " ORDER BY id DESC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "revision": row["revision"],
                "payload": json.loads(row["payload_json"]),
                "category": row["category"],
                "proposal": json.loads(row["proposal_json"]),
                "status": row["status"],
                "reviewed_by": row["reviewed_by"],
                "review_comment": row["review_comment"],
                "reviewed_at": row["reviewed_at"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def review_correction(
        self,
        correction_id: int,
        *,
        status: str,
        reviewed_by: str,
        comment: str,
        regression_passed: bool,
    ) -> dict[str, Any] | None:
        with self._lock, self.connect() as conn:
            row = conn.execute("SELECT * FROM corrections WHERE id=?", (correction_id,)).fetchone()
            if not row:
                return None
            proposal = json.loads(row["proposal_json"])
            if status == "APPROVED" and proposal.get("regression_required") and not regression_passed:
                raise ValueError("Для customer/global proposal требуется подтверждённый регрессионный прогон")
            conn.execute(
                "UPDATE corrections SET status=?, reviewed_by=?, review_comment=?, reviewed_at=? WHERE id=?",
                (status, reviewed_by, comment, utc_now(), correction_id),
            )
        return next((item for item in self.list_corrections() if item["id"] == correction_id), None)

    def recoverable_jobs(self) -> list[str]:
        terminal = {
            JobStatus.APPROVED_FINAL,
            JobStatus.CANCELLED,
            JobStatus.NEEDS_INPUT,
            JobStatus.READY_FOR_REVIEW,
            JobStatus.FAILED_ANALYSIS,
            JobStatus.FAILED_GENERATION,
            JobStatus.FAILED_VALIDATION,
        }
        return [job.job_id for job in self.list(500) if job.status not in terminal]
