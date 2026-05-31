from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

UNSET = object()


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ProgressStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT,
                    username TEXT,
                    chat_type TEXT,
                    indexed_at TEXT,
                    index_complete INTEGER DEFAULT 0,
                    newest_indexed_message_id INTEGER,
                    next_oldest_message_id INTEGER,
                    status TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    message_date TEXT,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'deleted', 'failed')),
                    last_error TEXT,
                    updated_at TEXT,
                    PRIMARY KEY(chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    phase TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    indexed_count INTEGER DEFAULT 0,
                    deleted_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    status TEXT
                );

                CREATE TABLE IF NOT EXISTS failed_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_ids TEXT NOT NULL,
                    error TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_messages_chat_status
                ON messages (chat_id, status);

                CREATE INDEX IF NOT EXISTS idx_runs_chat_started
                ON runs (chat_id, started_at DESC);
                """
            )
            self._ensure_schema_migrations(conn)

    def _ensure_schema_migrations(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(chats)").fetchall()}
        if "index_complete" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN index_complete INTEGER DEFAULT 0")
        if "newest_indexed_message_id" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN newest_indexed_message_id INTEGER")
        if "next_oldest_message_id" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN next_oldest_message_id INTEGER")

    def upsert_chat(
        self,
        chat_id: str,
        title: str,
        username: str | None,
        chat_type: str,
        status: str,
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chats (
                    chat_id,
                    title,
                    username,
                    chat_type,
                    indexed_at,
                    index_complete,
                    newest_indexed_message_id,
                    next_oldest_message_id,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    username = excluded.username,
                    chat_type = excluded.chat_type,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (chat_id, title, username, chat_type, status, now),
            )

    def update_chat_status(self, chat_id: str, status: str, indexed: bool = False) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            if indexed:
                conn.execute(
                    """
                    UPDATE chats
                    SET status = ?, indexed_at = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (status, now, now, chat_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE chats
                    SET status = ?, updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (status, now, chat_id),
                )

    def get_chat_index_state(self, chat_id: str) -> dict[str, int | bool | None]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT index_complete, newest_indexed_message_id, next_oldest_message_id
                FROM chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if not row:
            return {
                "index_complete": False,
                "newest_indexed_message_id": None,
                "next_oldest_message_id": None,
            }
        return {
            "index_complete": bool(row["index_complete"]),
            "newest_indexed_message_id": row["newest_indexed_message_id"],
            "next_oldest_message_id": row["next_oldest_message_id"],
        }

    def update_chat_index_state(
        self,
        chat_id: str,
        *,
        newest_indexed_message_id: int | None | object = UNSET,
        next_oldest_message_id: int | None | object = UNSET,
        index_complete: bool | None = None,
    ) -> None:
        current = self.get_chat_index_state(chat_id)
        next_state = {
            "newest_indexed_message_id": (
                newest_indexed_message_id
                if newest_indexed_message_id is not UNSET
                else current["newest_indexed_message_id"]
            ),
            "next_oldest_message_id": (
                next_oldest_message_id
                if next_oldest_message_id is not UNSET
                else current["next_oldest_message_id"]
            ),
            "index_complete": current["index_complete"] if index_complete is None else index_complete,
        }
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE chats
                SET newest_indexed_message_id = ?,
                    next_oldest_message_id = ?,
                    index_complete = ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (
                    next_state["newest_indexed_message_id"],
                    next_state["next_oldest_message_id"],
                    1 if next_state["index_complete"] else 0,
                    now,
                    chat_id,
                ),
            )

    def create_run(self, chat_id: str, phase: str, status: str = "running") -> int:
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs (chat_id, phase, started_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, phase, now, status),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, counts: dict[str, int]) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, indexed_count = ?, deleted_count = ?, failed_count = ?, status = ?
                WHERE run_id = ?
                """,
                (
                    now,
                    counts.get("indexed", 0),
                    counts.get("deleted", 0),
                    counts.get("failed", 0),
                    status,
                    run_id,
                ),
            )

    def set_run_status(self, run_id: int, status: str, counts: dict[str, int]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET indexed_count = ?, deleted_count = ?, failed_count = ?, status = ?
                WHERE run_id = ?
                """,
                (
                    counts.get("indexed", 0),
                    counts.get("deleted", 0),
                    counts.get("failed", 0),
                    status,
                    run_id,
                ),
            )

    def bulk_upsert_messages(self, chat_id: str, rows: Iterable[tuple[int, str | None]]) -> int:
        rows = list(rows)
        if not rows:
            return 0

        now = utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO messages (chat_id, message_id, message_date, status, last_error, updated_at)
                VALUES (?, ?, ?, 'pending', NULL, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    message_date = COALESCE(messages.message_date, excluded.message_date),
                    updated_at = excluded.updated_at
                """,
                [(chat_id, message_id, message_date, now) for message_id, message_date in rows],
            )
        return len(rows)

    def get_status_counts(self, chat_id: str) -> dict[str, int | str | None]:
        with self._connect() as conn:
            counts_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS indexed,
                    SUM(CASE WHEN status = 'deleted' THEN 1 ELSE 0 END) AS deleted,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    MAX(updated_at) AS last_update
                FROM messages
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()

            chat_row = conn.execute(
                """
                SELECT
                    title,
                    username,
                    chat_type,
                    indexed_at,
                    index_complete,
                    newest_indexed_message_id,
                    next_oldest_message_id,
                    status,
                    updated_at
                FROM chats
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()

        indexed = int(counts_row["indexed"] or 0)
        deleted = int(counts_row["deleted"] or 0)
        pending = int(counts_row["pending"] or 0)
        failed = int(counts_row["failed"] or 0)
        data = {
            "chat_id": chat_id,
            "indexed": indexed,
            "deleted": deleted,
            "pending": pending,
            "failed": failed,
            "last_update": counts_row["last_update"],
            "title": None,
            "username": None,
            "chat_type": None,
            "indexed_at": None,
            "index_complete": False,
            "newest_indexed_message_id": None,
            "next_oldest_message_id": None,
            "status": None,
            "chat_updated_at": None,
        }
        if chat_row:
            data.update(
                {
                    "title": chat_row["title"],
                    "username": chat_row["username"],
                    "chat_type": chat_row["chat_type"],
                    "indexed_at": chat_row["indexed_at"],
                    "index_complete": bool(chat_row["index_complete"]),
                    "newest_indexed_message_id": chat_row["newest_indexed_message_id"],
                    "next_oldest_message_id": chat_row["next_oldest_message_id"],
                    "status": chat_row["status"],
                    "chat_updated_at": chat_row["updated_at"],
                }
            )
        return data

    def get_message_ids_by_status(self, chat_id: str, status: str, limit: int | None = None) -> list[int]:
        sql = """
            SELECT message_id
            FROM messages
            WHERE chat_id = ? AND status = ?
            ORDER BY message_id ASC
        """
        parameters: list[object] = [chat_id, status]
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, parameters).fetchall()
        return [int(row["message_id"]) for row in rows]

    def get_message_dates(self, chat_id: str, message_ids: Iterable[int]) -> dict[int, str | None]:
        message_ids = list(message_ids)
        if not message_ids:
            return {}

        placeholders = ", ".join("?" for _ in message_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT message_id, message_date
                FROM messages
                WHERE chat_id = ? AND message_id IN ({placeholders})
                """,
                [chat_id, *message_ids],
            ).fetchall()
        return {int(row["message_id"]): row["message_date"] for row in rows}

    def mark_messages_deleted(self, chat_id: str, message_ids: Iterable[int]) -> None:
        self._set_message_status(chat_id, message_ids, "deleted", None)

    def mark_messages_failed(self, chat_id: str, message_ids: Iterable[int], error: str) -> None:
        self._set_message_status(chat_id, message_ids, "failed", error)

    def _set_message_status(
        self,
        chat_id: str,
        message_ids: Iterable[int],
        status: str,
        error: str | None,
    ) -> None:
        message_ids = list(message_ids)
        if not message_ids:
            return

        now = utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE messages
                SET status = ?, last_error = ?, updated_at = ?
                WHERE chat_id = ? AND message_id = ?
                """,
                [(status, error, now, chat_id, message_id) for message_id in message_ids],
            )

    def record_failed_batch(
        self,
        chat_id: str,
        message_ids: Iterable[int],
        error_type: str,
        error_message: str,
    ) -> None:
        now = utc_now_iso()
        ids_text = ",".join(str(message_id) for message_id in message_ids)
        full_error = f"{error_type}: {error_message}".strip(": ")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failed_batches (chat_id, message_ids, error, error_type, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, ids_text, full_error, error_type, error_message, now),
            )

    def clear_failed_batch_records(self, chat_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM failed_batches WHERE chat_id = ?", (chat_id,))

    def reset_failed_to_pending(self, chat_id: str) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE messages
                SET status = 'pending', last_error = NULL, updated_at = ?
                WHERE chat_id = ? AND status = 'failed'
                """,
                (now, chat_id),
            )

    def get_recent_run(self, chat_id: str) -> dict[str, str | int | None] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, phase, started_at, finished_at, indexed_count, deleted_count, failed_count, status
                FROM runs
                WHERE chat_id = ?
                ORDER BY run_id DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_app_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_app_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else None
