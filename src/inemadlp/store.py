"""Persistência dos jobs em SQLite. Nenhuma regra de negócio aqui."""

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

PENDING = "pending"
RUNNING = "running"
READY = "ready"
ERROR = "error"
EXPIRED = "expired"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    format TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    title TEXT,
    filename TEXT,
    size INTEGER,
    error TEXT,
    created_at INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Job:
    id: str
    url: str
    format: str
    status: str
    progress: float
    title: str | None
    filename: str | None
    size: int | None
    error: str | None
    created_at: int


class Store:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(**{campo: row[campo] for campo in Job.__dataclass_fields__})

    def create(self, url: str, fmt: str, now: int) -> Job:
        job_id = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (id, url, format, status, progress, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (job_id, url, fmt, PENDING, now),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> Job | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_all(self) -> list[Job]:
        with self._conn() as conn:
            linhas = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [self._row_to_job(linha) for linha in linhas]

    def claim_next(self, now: int) -> Job | None:
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1",
                (PENDING,),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (RUNNING, row["id"]))
            conn.execute("COMMIT")
        return self.get(row["id"])

    def _update(self, job_id: str, **campos) -> None:
        atribuicoes = ", ".join(f"{nome} = ?" for nome in campos)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE jobs SET {atribuicoes} WHERE id = ?",
                (*campos.values(), job_id),
            )

    def set_progress(self, job_id: str, progress: float) -> None:
        self._update(job_id, progress=progress)

    def set_title(self, job_id: str, title: str) -> None:
        self._update(job_id, title=title)

    def mark_ready(self, job_id: str, filename: str, size: int) -> None:
        self._update(job_id, status=READY, filename=filename, size=size, progress=100.0)

    def mark_error(self, job_id: str, message: str) -> None:
        self._update(job_id, status=ERROR, error=message)

    def mark_expired(self, job_id: str) -> None:
        self._update(job_id, status=EXPIRED, filename=None, size=None)

    def reset_running_to_error(self, message: str) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, error = ? WHERE status = ?",
                (ERROR, message, RUNNING),
            )
        return cursor.rowcount

    def list_expirable(self, cutoff: int) -> list[Job]:
        with self._conn() as conn:
            linhas = conn.execute(
                "SELECT * FROM jobs WHERE status IN (?, ?) AND created_at < ?",
                (READY, ERROR, cutoff),
            ).fetchall()
        return [self._row_to_job(linha) for linha in linhas]

    def known_ids(self) -> set[str]:
        """Todos os IDs de jobs que ainda têm linha no banco (qualquer status)."""
        with self._conn() as conn:
            linhas = conn.execute("SELECT id FROM jobs").fetchall()
        return {linha["id"] for linha in linhas}

    def delete_older_than(self, cutoff: int) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM jobs WHERE status IN (?, ?) AND created_at < ?",
                (EXPIRED, ERROR, cutoff),
            )
        return cursor.rowcount
