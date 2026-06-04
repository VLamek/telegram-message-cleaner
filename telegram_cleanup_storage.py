from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

UNSET = object()


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class FailedStorage:
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
                CREATE TABLE IF NOT EXISTS failed_messages (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    message_date TEXT,
                    message_type TEXT,
                    status TEXT NOT NULL DEFAULT 'failed',
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY(chat_id, message_id)
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

                CREATE INDEX IF NOT EXISTS idx_failed_messages_chat_status
                ON failed_messages (chat_id, status);
                """
            )
            self._ensure_schema_migrations(conn)

    def _ensure_schema_migrations(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(failed_messages)").fetchall()}
        if "message_type" not in columns:
            conn.execute("ALTER TABLE failed_messages ADD COLUMN message_type TEXT")

    def add_failed_messages(
        self,
        chat_id: str,
        records: Iterable[tuple[int, str | None, str | None]],
        error_type: str,
        error_message: str,
    ) -> int:
        records = list(records)
        if not records:
            return 0

        now = utc_now_iso()
        new_count = 0
        with self._connect() as conn:
            for message_id, message_date, message_type in records:
                cursor = conn.execute(
                    """
                    INSERT INTO failed_messages (
                        chat_id, message_id, message_date, message_type, status,
                        error_type, error_message, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'failed', ?, ?, ?, ?)
                    ON CONFLICT(chat_id, message_id) DO UPDATE SET
                        message_date = COALESCE(failed_messages.message_date, excluded.message_date),
                        message_type = COALESCE(failed_messages.message_type, excluded.message_type),
                        status = 'failed',
                        error_type = excluded.error_type,
                        error_message = excluded.error_message,
                        updated_at = excluded.updated_at
                    """,
                    (chat_id, message_id, message_date, message_type, error_type, error_message, now, now),
                )
                if cursor.rowcount == 1:
                    existing = conn.execute(
                        """
                        SELECT created_at
                        FROM failed_messages
                        WHERE chat_id = ? AND message_id = ?
                        """,
                        (chat_id, message_id),
                    ).fetchone()
                    if existing and existing["created_at"] == now:
                        new_count += 1
        return new_count

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

    def get_failed_count(
        self,
        chat_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: Iterable[str] | None = None,
    ) -> int:
        filters, parameters = self._combined_filters(date_from, date_to, message_types)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM failed_messages
                WHERE chat_id = ? AND status = 'failed'
                {filters}
                """,
                [chat_id, *parameters],
            ).fetchone()
        return int(row["count"] or 0)

    def get_failed_records(
        self,
        chat_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: Iterable[str] | None = None,
    ) -> list[tuple[int, str | None, str | None]]:
        filters, parameters = self._combined_filters(date_from, date_to, message_types)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT message_id, message_date, message_type
                FROM failed_messages
                WHERE chat_id = ? AND status = 'failed'
                {filters}
                ORDER BY message_id ASC
                """,
                [chat_id, *parameters],
            ).fetchall()
        return [(int(row["message_id"]), row["message_date"], row["message_type"]) for row in rows]

    def _combined_filters(
        self,
        date_from: str | None,
        date_to: str | None,
        message_types: Iterable[str] | None,
    ) -> tuple[str, list[object]]:
        filters: list[str] = []
        parameters: list[object] = []
        if date_from is not None:
            filters.append("AND message_date IS NOT NULL AND message_date >= ?")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("AND message_date IS NOT NULL AND message_date <= ?")
            parameters.append(date_to)
        types = list(message_types or [])
        if types:
            placeholders = ", ".join("?" for _ in types)
            filters.append(f"AND message_type IN ({placeholders})")
            parameters.extend(types)
        return (" ".join(filters), parameters)

    def remove_failed_messages(self, chat_id: str, message_ids: Iterable[int]) -> int:
        message_ids = list(message_ids)
        if not message_ids:
            return 0
        removed = 0
        with self._connect() as conn:
            for message_id in message_ids:
                cursor = conn.execute(
                    """
                    DELETE FROM failed_messages
                    WHERE chat_id = ? AND message_id = ?
                    """,
                    (chat_id, message_id),
                )
                removed += int(cursor.rowcount or 0)
        return removed

    def clear_chat(self, chat_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM failed_batches WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM failed_messages WHERE chat_id = ?", (chat_id,))


class ProgressStorage:
    def __init__(self, db_path: Path, failed_db_path: Path | None = None) -> None:
        self.db_path = db_path
        self.failed_storage = FailedStorage(failed_db_path or db_path.with_name("telegram_message_cleaner_failed.sqlite3"))
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
                    indexed_total INTEGER DEFAULT 0,
                    deleted_total INTEGER DEFAULT 0,
                    failed_total INTEGER DEFAULT 0,
                    status TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    message_date TEXT,
                    message_type TEXT,
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
        if "indexed_total" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN indexed_total INTEGER DEFAULT 0")
        if "deleted_total" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN deleted_total INTEGER DEFAULT 0")
        if "failed_total" not in columns:
            conn.execute("ALTER TABLE chats ADD COLUMN failed_total INTEGER DEFAULT 0")
        message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "message_type" not in message_columns:
            conn.execute("ALTER TABLE messages ADD COLUMN message_type TEXT")

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
                    indexed_total,
                    deleted_total,
                    failed_total,
                    status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, NULL, 0, NULL, NULL, 0, 0, 0, ?, ?)
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

    def bulk_upsert_messages(self, chat_id: str, rows: Iterable[tuple[int, str | None, str | None]]) -> int:
        rows = list(rows)
        if not rows:
            return 0

        now = utc_now_iso()
        candidate_ids = [message_id for message_id, _message_date, _message_type in rows]
        with self._connect() as conn:
            existing_ids = self._get_existing_message_ids(conn, chat_id, candidate_ids)
            failed_ids = self._get_failed_message_ids(chat_id, candidate_ids)
            rows_to_write = [
                (message_id, message_date, message_type)
                for message_id, message_date, message_type in rows
                if message_id not in failed_ids
            ]
            new_rows = [
                (message_id, message_date, message_type)
                for message_id, message_date, message_type in rows_to_write
                if message_id not in existing_ids and message_id not in failed_ids
            ]
            conn.executemany(
                """
                INSERT INTO messages (chat_id, message_id, message_date, message_type, status, last_error, updated_at)
                VALUES (?, ?, ?, ?, 'pending', NULL, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    message_date = COALESCE(messages.message_date, excluded.message_date),
                    message_type = COALESCE(messages.message_type, excluded.message_type),
                    updated_at = excluded.updated_at
                """,
                [(chat_id, message_id, message_date, message_type, now) for message_id, message_date, message_type in rows_to_write],
            )
            if new_rows:
                conn.execute(
                    """
                    UPDATE chats
                    SET indexed_total = COALESCE(indexed_total, 0) + ?,
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (len(new_rows), now, chat_id),
                )
        return len(new_rows)

    def _get_existing_message_ids(self, conn: sqlite3.Connection, chat_id: str, message_ids: list[int]) -> set[int]:
        if not message_ids:
            return set()
        placeholders = ", ".join("?" for _ in message_ids)
        rows = conn.execute(
            f"""
            SELECT message_id
            FROM messages
            WHERE chat_id = ? AND message_id IN ({placeholders})
            """,
            [chat_id, *message_ids],
        ).fetchall()
        return {int(row["message_id"]) for row in rows}

    def _get_failed_message_ids(self, chat_id: str, message_ids: list[int]) -> set[int]:
        if not message_ids:
            return set()
        existing = self.failed_storage.get_failed_records(chat_id)
        target_ids = set(message_ids)
        return {message_id for message_id, _message_date, _message_type in existing if message_id in target_ids}

    def get_status_counts(
        self,
        chat_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: Iterable[str] | None = None,
    ) -> dict[str, int | str | None]:
        filters, parameters = self._combined_filters(date_from, date_to, message_types)
        with self._connect() as conn:
            counts_row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS indexed,
                    SUM(CASE WHEN status = 'deleted' THEN 1 ELSE 0 END) AS deleted,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    MAX(updated_at) AS last_update
                FROM messages
                WHERE chat_id = ?
                {filters}
                """,
                [chat_id, *parameters],
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
                    indexed_total,
                    deleted_total,
                    failed_total,
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
                    "indexed": indexed if date_from or date_to or message_types else int(chat_row["indexed_total"] or indexed),
                    "deleted": deleted if date_from or date_to or message_types else int(chat_row["deleted_total"] or deleted),
                    "failed": failed if date_from or date_to or message_types else int(chat_row["failed_total"] or failed),
                    "status": chat_row["status"],
                    "chat_updated_at": chat_row["updated_at"],
                }
            )
            data["failed"] = max(
                int(data["failed"] or 0),
                self.failed_storage.get_failed_count(chat_id, date_from, date_to, message_types),
            )
        return data

    def get_message_ids_by_status(
        self,
        chat_id: str,
        status: str,
        limit: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: Iterable[str] | None = None,
    ) -> list[int]:
        filters, date_parameters = self._combined_filters(date_from, date_to, message_types)
        sql = f"""
            SELECT message_id
            FROM messages
            WHERE chat_id = ? AND status = ?
            {filters}
            ORDER BY message_id ASC
        """
        parameters: list[object] = [chat_id, status, *date_parameters]
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, parameters).fetchall()
        return [int(row["message_id"]) for row in rows]

    def _combined_filters(
        self,
        date_from: str | None,
        date_to: str | None,
        message_types: Iterable[str] | None,
    ) -> tuple[str, list[object]]:
        filters: list[str] = []
        parameters: list[object] = []
        if date_from is not None:
            filters.append("AND message_date IS NOT NULL AND message_date >= ?")
            parameters.append(date_from)
        if date_to is not None:
            filters.append("AND message_date IS NOT NULL AND message_date <= ?")
            parameters.append(date_to)
        types = list(message_types or [])
        if types:
            placeholders = ", ".join("?" for _ in types)
            filters.append(f"AND message_type IN ({placeholders})")
            parameters.extend(types)
        return (" ".join(filters), parameters)

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

    def get_message_metadata(self, chat_id: str, message_ids: Iterable[int]) -> dict[int, tuple[str | None, str | None]]:
        message_ids = list(message_ids)
        if not message_ids:
            return {}

        placeholders = ", ".join("?" for _ in message_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT message_id, message_date, message_type
                FROM messages
                WHERE chat_id = ? AND message_id IN ({placeholders})
                """,
                [chat_id, *message_ids],
            ).fetchall()
        return {int(row["message_id"]): (row["message_date"], row["message_type"]) for row in rows}

    def mark_messages_deleted(self, chat_id: str, message_ids: Iterable[int]) -> None:
        message_ids = list(message_ids)
        if not message_ids:
            return
        now = utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                DELETE FROM messages
                WHERE chat_id = ? AND message_id = ?
                """,
                [(chat_id, message_id) for message_id in message_ids],
            )
            conn.execute(
                """
                UPDATE chats
                SET deleted_total = COALESCE(deleted_total, 0) + ?,
                    updated_at = ?
                WHERE chat_id = ?
                """,
                (len(message_ids), now, chat_id),
            )
        removed_failed = self.failed_storage.remove_failed_messages(chat_id, message_ids)
        if removed_failed:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE chats
                    SET failed_total = MAX(COALESCE(failed_total, 0) - ?, 0),
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (removed_failed, utc_now_iso(), chat_id),
                )

    def mark_messages_failed(self, chat_id: str, message_ids: Iterable[int], error: str) -> None:
        message_ids = list(message_ids)
        if not message_ids:
            return
        metadata = self.get_message_metadata(chat_id, message_ids)
        records = [
            (message_id, metadata.get(message_id, (None, None))[0], metadata.get(message_id, (None, None))[1])
            for message_id in message_ids
        ]
        new_failed = self.failed_storage.add_failed_messages(chat_id, records, "DeleteFailed", error)
        now = utc_now_iso()
        with self._connect() as conn:
            conn.executemany(
                """
                DELETE FROM messages
                WHERE chat_id = ? AND message_id = ?
                """,
                [(chat_id, message_id) for message_id in message_ids],
            )
            if new_failed:
                conn.execute(
                    """
                    UPDATE chats
                    SET failed_total = COALESCE(failed_total, 0) + ?,
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (new_failed, now, chat_id),
                )

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
        self.failed_storage.record_failed_batch(chat_id, message_ids, error_type, error_message)

    def clear_failed_batch_records(self, chat_id: str) -> None:
        self.failed_storage.clear_chat(chat_id)

    def reset_failed_to_pending(
        self,
        chat_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: Iterable[str] | None = None,
    ) -> None:
        records = self.failed_storage.get_failed_records(chat_id, date_from, date_to, message_types)
        now = utc_now_iso()
        with self._connect() as conn:
            if records:
                conn.executemany(
                    """
                    INSERT INTO messages (chat_id, message_id, message_date, message_type, status, last_error, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', NULL, ?)
                    ON CONFLICT(chat_id, message_id) DO UPDATE SET
                        message_date = COALESCE(messages.message_date, excluded.message_date),
                        message_type = COALESCE(messages.message_type, excluded.message_type),
                        status = 'pending',
                        last_error = NULL,
                        updated_at = excluded.updated_at
                    """,
                    [(chat_id, message_id, message_date, message_type, now) for message_id, message_date, message_type in records],
                )
            conn.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (now, chat_id))

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

    def get_resume_candidates(self, limit: int = 5) -> list[dict[str, int | str | bool | None]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id
                FROM chats
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, limit * 3),),
            ).fetchall()

        candidates: list[dict[str, int | str | bool | None]] = []
        for row in rows:
            chat_id = str(row["chat_id"])
            counts = self.get_status_counts(chat_id)
            recent_run = self.get_recent_run(chat_id) or {}
            indexed = int(counts.get("indexed") or 0)
            pending = int(counts.get("pending") or 0)
            failed = int(counts.get("failed") or 0)
            index_complete = bool(counts.get("index_complete"))
            has_partial_index = indexed > 0 and not index_complete
            has_deletion_work = pending > 0
            has_retry_work = recent_run.get("phase") == "retry_failed" and failed > 0

            if not (has_partial_index or has_deletion_work or has_retry_work):
                continue

            candidate = dict(counts)
            candidate.update(
                {
                    "recent_run_id": recent_run.get("run_id"),
                    "recent_phase": recent_run.get("phase"),
                    "recent_status": recent_run.get("status"),
                    "recent_started_at": recent_run.get("started_at"),
                    "recent_finished_at": recent_run.get("finished_at"),
                }
            )
            candidates.append(candidate)
            if len(candidates) >= limit:
                break

        return candidates

    def clear_chat_workspace(self, chat_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM failed_batches WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM runs WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))

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
