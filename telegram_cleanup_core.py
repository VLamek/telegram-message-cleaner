from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    from telethon import TelegramClient, errors, utils
    from telethon.tl import types
    TELETHON_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:
    TELETHON_IMPORT_ERROR = exc
    TelegramClient = Any  # type: ignore[assignment,misc]

    class _MissingErrors:
        pass

    class _MissingUtils:
        @staticmethod
        def get_peer_id(entity: Any) -> Any:
            return getattr(entity, "id", "unknown")

    errors = _MissingErrors()
    utils = _MissingUtils()
    types = Any  # type: ignore[assignment]

from telegram_cleanup_logging import format_exception_message, setup_app_logger
from telegram_cleanup_storage import ProgressStorage


APP_NAME = "Telegram Message Cleaner"
CONFIG_FILE_NAME = "telegram_message_cleaner_config.json"
SESSION_FILE_STEM = "telegram_message_cleaner"
DB_FILE_NAME = "telegram_message_cleaner.sqlite3"
FAILED_DB_FILE_NAME = "telegram_message_cleaner_failed.sqlite3"
DEV_DATA_DIR_NAME = "TelegramMessageCleaner"
SUPPORTED_LANGUAGES = ("en", "ru", "es", "zh-CN", "fr")
SUPPORTED_THEMES = ("Light", "Dark")
MESSAGE_TYPE_OPTIONS = (
    "text",
    "links",
    "photo",
    "video",
    "gif",
    "voice",
    "video_note",
    "file",
    "sticker",
    "poll",
    "other",
)

EventCallback = Callable[[dict[str, Any]], None]


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_runtime_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return get_app_dir()

    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app_data:
        data_dir = Path(local_app_data) / DEV_DATA_DIR_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    fallback = get_app_dir() / ".local_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def format_speed(speed_per_minute: float | None) -> str:
    if not speed_per_minute or speed_per_minute <= 0:
        return "calculating..."
    return f"{speed_per_minute:.1f} msg/min"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "calculating..."
    total_seconds = int(seconds)
    if total_seconds < 60:
        return f"~ {total_seconds} sec"
    minutes, seconds_remainder = divmod(total_seconds, 60)
    hours, minutes_remainder = divmod(minutes, 60)
    if hours:
        return f"~ {hours} h {minutes_remainder} min"
    if minutes:
        return f"~ {minutes} min"
    return f"~ {seconds_remainder} sec"


def safe_sleep_chunks(duration_seconds: float) -> list[float]:
    chunks: list[float] = []
    remaining = max(0.0, duration_seconds)
    while remaining > 0:
        chunk = 0.2 if remaining > 0.2 else remaining
        chunks.append(chunk)
        remaining -= chunk
    return chunks


@dataclass(frozen=True)
class MessageDateRange:
    start: datetime | None = None
    end: datetime | None = None

    @property
    def is_bounded(self) -> bool:
        return self.start is not None or self.end is not None

    @property
    def start_iso(self) -> str | None:
        return self.start.isoformat() if self.start else None

    @property
    def end_iso(self) -> str | None:
        return self.end.isoformat() if self.end else None

    def contains(self, value: datetime | None) -> bool:
        if value is None:
            return not self.is_bounded
        normalized = normalize_message_datetime(value)
        if self.start and normalized < self.start:
            return False
        if self.end and normalized > self.end:
            return False
        return True


@dataclass(frozen=True)
class MessageTypeFilter:
    selected: frozenset[str] = frozenset(MESSAGE_TYPE_OPTIONS)

    @property
    def is_all(self) -> bool:
        return self.selected == frozenset(MESSAGE_TYPE_OPTIONS)

    @property
    def storage_filter(self) -> tuple[str, ...] | None:
        return None if self.is_all else tuple(sorted(self.selected))

    def contains(self, message_type: str) -> bool:
        return message_type in self.selected


def parse_message_type_filter(value: str | Iterable[str] | None = None) -> MessageTypeFilter:
    if value is None:
        return MessageTypeFilter()
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.replace(";", ",").split(",")]
    else:
        raw_items = [str(item).strip() for item in value]

    items = [item for item in raw_items if item]
    if not items or any(item.lower() == "all" for item in items):
        return MessageTypeFilter()

    selected = frozenset(item for item in items if item in MESSAGE_TYPE_OPTIONS)
    unknown = sorted(set(items) - set(MESSAGE_TYPE_OPTIONS))
    if unknown:
        raise ValueError(f"Unsupported message type(s): {', '.join(unknown)}")
    if not selected:
        raise ValueError("Select at least one message type.")
    return MessageTypeFilter(selected=selected)


def normalize_message_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        value = value.replace(tzinfo=local_tz)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def parse_message_datetime(value: str | None, *, is_end: bool = False) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.lower() in {"first", "earliest", "start", "beginning", "last", "latest", "end"}:
        return None

    normalized = text.replace("T", " ")
    parsed: datetime
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("Date/time must use YYYY-MM-DD HH:MM or ISO format.") from exc
        parsed = datetime.combine(
            parsed_date,
            datetime_time(23, 59, 59) if is_end else datetime_time(0, 0, 0),
        )
        return normalize_message_datetime(parsed)

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("Date/time must use YYYY-MM-DD HH:MM or ISO format.") from exc
        parsed = datetime.combine(
            parsed_date,
            datetime_time(23, 59, 59) if is_end else datetime_time(0, 0, 0),
        )
    return normalize_message_datetime(parsed)


def parse_message_date_range(date_from: str | None = None, date_to: str | None = None) -> MessageDateRange:
    start = parse_message_datetime(date_from, is_end=False)
    end = parse_message_datetime(date_to, is_end=True)
    if start and end and start > end:
        raise ValueError("Date/time range is invalid: From must be earlier than To.")
    return MessageDateRange(start=start, end=end)


@dataclass
class RunControl:
    _pause_requested: threading.Event = field(default_factory=threading.Event)
    _stop_requested: threading.Event = field(default_factory=threading.Event)

    def reset(self) -> None:
        self._pause_requested.clear()
        self._stop_requested.clear()

    def request_pause(self) -> None:
        self._pause_requested.set()

    def request_stop(self) -> None:
        self._stop_requested.set()

    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    def pause_requested(self) -> bool:
        return self._pause_requested.is_set()

    def terminal_status(self) -> str | None:
        if self._stop_requested.is_set():
            return "stopped"
        if self._pause_requested.is_set():
            return "paused"
        return None


class ConfigStore:
    def __init__(self, config_dir: Path, env_fallback_dir: Path) -> None:
        self.config_dir = config_dir
        self.env_fallback_dir = env_fallback_dir
        self.config_path = config_dir / CONFIG_FILE_NAME
        load_dotenv(env_fallback_dir / ".env")

    def default_config(self) -> dict[str, Any]:
        return {
            "api_id": "",
            "api_hash": "",
            "phone_number": "",
            "language": "en",
            "theme": "Dark",
            "require_confirmation_before_deletion": True,
            "db_file": DB_FILE_NAME,
        }

    def load(self) -> dict[str, Any]:
        data = self.default_config()
        if self.config_path.exists():
            try:
                loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
            except json.JSONDecodeError:
                pass

        if not data.get("api_id"):
            data["api_id"] = str(os.environ.get("TELEGRAM_API_ID", "")).strip()
        if not data.get("api_hash"):
            data["api_hash"] = str(os.environ.get("TELEGRAM_API_HASH", "")).strip()
        if not data.get("phone_number"):
            data["phone_number"] = str(os.environ.get("TELEGRAM_PHONE_NUMBER", "")).strip()

        if data.get("language") not in SUPPORTED_LANGUAGES:
            data["language"] = "en"
        if data.get("theme") not in SUPPORTED_THEMES:
            data["theme"] = "Dark"
        if "require_confirmation_before_deletion" not in data:
            data["require_confirmation_before_deletion"] = True
        if not data.get("db_file"):
            data["db_file"] = DB_FILE_NAME
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class TelegramCleanupCore:
    def __init__(
        self,
        app_dir: Path | None = None,
        event_callback: EventCallback | None = None,
        db_file_override: str | None = None,
    ) -> None:
        self.app_dir = app_dir or get_app_dir()
        self.data_dir = get_runtime_data_dir()
        self._migrate_legacy_runtime_files()
        self.event_callback = event_callback
        self.config_store = ConfigStore(self.data_dir, self.app_dir)
        self.config = self.config_store.load()
        self.logger, self.log_dir = setup_app_logger(self.data_dir)
        self._db_file_override = db_file_override
        self.storage = ProgressStorage(self.get_database_path(), self.get_failed_database_path())
        self._pending_phone_number: str | None = None
        self._pending_phone_code_hash: str | None = None
        self._ensure_git_protection_for_local_files()

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def reload_config(self) -> dict[str, Any]:
        self.config = self.config_store.load()
        self.storage = ProgressStorage(self.get_database_path(), self.get_failed_database_path())
        self._ensure_git_protection_for_local_files()
        return self.get_config()

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        data = self.config_store.load()
        data.update(updates)
        self.config_store.save(data)
        self.config = data
        self.storage = ProgressStorage(self.get_database_path(), self.get_failed_database_path())
        self._ensure_git_protection_for_local_files()
        return self.get_config()

    def save_api_credentials(self, api_id: str, api_hash: str, phone_number: str) -> dict[str, Any]:
        if not api_id.strip() or not api_hash.strip():
            raise ValueError("API ID and API Hash are required.")
        self.save_config(
            {
                "api_id": api_id.strip(),
                "api_hash": api_hash.strip(),
                "phone_number": phone_number.strip(),
            }
        )
        self._log("info", "API credentials saved locally.")
        return self.get_config()

    def set_language(self, language: str) -> dict[str, Any]:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        return self.save_config({"language": language})

    def set_theme(self, theme: str) -> dict[str, Any]:
        if theme not in SUPPORTED_THEMES:
            raise ValueError(f"Unsupported theme: {theme}")
        return self.save_config({"theme": theme})

    def set_require_confirmation(self, enabled: bool) -> dict[str, Any]:
        return self.save_config({"require_confirmation_before_deletion": bool(enabled)})

    def set_db_file(self, db_file: str, persist: bool = True) -> Path:
        db_file = db_file.strip() or DB_FILE_NAME
        if persist:
            self.save_config({"db_file": db_file})
            self._db_file_override = None
        else:
            self._db_file_override = db_file
            self.storage = ProgressStorage(self.get_database_path(), self.get_failed_database_path())
        return self.get_database_path()

    def get_database_path(self) -> Path:
        db_value = self._db_file_override or self.config.get("db_file") or DB_FILE_NAME
        candidate = Path(str(db_value))
        if not candidate.is_absolute():
            candidate = self.data_dir / candidate
        return candidate.resolve()

    def get_failed_database_path(self) -> Path:
        return self.get_database_path().with_name(FAILED_DB_FILE_NAME).resolve()

    def get_config_path(self) -> Path:
        return self.config_store.config_path.resolve()

    def get_session_file_path(self) -> Path:
        return (self.data_dir / f"{SESSION_FILE_STEM}.session").resolve()

    def delete_local_progress_database(self) -> None:
        db_path = self.get_database_path()
        wal_path = db_path.with_suffix(f"{db_path.suffix}-wal")
        shm_path = db_path.with_suffix(f"{db_path.suffix}-shm")
        failed_db_path = self.get_failed_database_path()
        failed_wal_path = failed_db_path.with_suffix(f"{failed_db_path.suffix}-wal")
        failed_shm_path = failed_db_path.with_suffix(f"{failed_db_path.suffix}-shm")
        for path in (db_path, wal_path, shm_path, failed_db_path, failed_wal_path, failed_shm_path):
            if path.exists():
                path.unlink()
        self.storage = ProgressStorage(db_path, failed_db_path)
        self._log("info", f"Deleted local progress database: {db_path}")

    def get_auth_status(self) -> dict[str, Any]:
        return asyncio.run(self._get_auth_status_async())

    def send_code(self, phone_number: str | None = None) -> dict[str, Any]:
        return asyncio.run(self._send_code_async(phone_number))

    def sign_in(self, login_code: str, phone_number: str | None = None) -> dict[str, Any]:
        return asyncio.run(self._sign_in_async(login_code, phone_number))

    def submit_password(self, password: str) -> dict[str, Any]:
        return asyncio.run(self._submit_password_async(password))

    def logout(self) -> dict[str, Any]:
        return asyncio.run(self._logout_async())

    def list_groups(self) -> list[dict[str, Any]]:
        return asyncio.run(self._list_groups_async())

    def get_chat_overview(self, chat_input: str) -> dict[str, Any]:
        return asyncio.run(self._get_chat_overview_async(chat_input))

    def index_messages(
        self,
        chat_input: str,
        control: RunControl | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        date_range = parse_message_date_range(date_from, date_to)
        type_filter = parse_message_type_filter(message_types)
        return asyncio.run(self._index_messages_async(chat_input, control or RunControl(), date_range, type_filter))

    def start_cleanup(
        self,
        chat_input: str,
        batch_size: int = 100,
        pause_seconds: float = 2.0,
        control: RunControl | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        date_range = parse_message_date_range(date_from, date_to)
        type_filter = parse_message_type_filter(message_types)
        return asyncio.run(
            self._start_cleanup_async(
                chat_input=chat_input,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                control=control or RunControl(),
                date_range=date_range,
                type_filter=type_filter,
            )
        )

    def delete_indexed_only(
        self,
        chat_input: str,
        batch_size: int = 100,
        pause_seconds: float = 2.0,
        control: RunControl | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        date_range = parse_message_date_range(date_from, date_to)
        type_filter = parse_message_type_filter(message_types)
        return asyncio.run(
            self._delete_indexed_only_async(
                chat_input=chat_input,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                control=control or RunControl(),
                date_range=date_range,
                type_filter=type_filter,
            )
        )

    def retry_failed(
        self,
        chat_input: str,
        batch_size: int = 100,
        pause_seconds: float = 2.0,
        control: RunControl | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        message_types: str | Iterable[str] | None = None,
    ) -> dict[str, Any]:
        date_range = parse_message_date_range(date_from, date_to)
        type_filter = parse_message_type_filter(message_types)
        return asyncio.run(
            self._retry_failed_async(
                chat_input=chat_input,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                control=control or RunControl(),
                date_range=date_range,
                type_filter=type_filter,
            )
        )

    def request_pause(self, control: RunControl) -> None:
        control.request_pause()
        self._log("info", "Pause requested. Will pause after the current batch.")

    def request_stop(self, control: RunControl) -> None:
        control.request_stop()
        self._log("info", "Stop requested. Will stop after the current batch.")

    def _log(self, level: str, message: str, **context: Any) -> None:
        text = message
        if context:
            context_parts = [f"{key}={value}" for key, value in context.items() if value not in (None, "")]
            if context_parts:
                text = f"{message} | " + " | ".join(context_parts)
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(text)
        if self.event_callback:
            payload = {"type": "log", "level": level, "message": message}
            payload.update(context)
            self.event_callback(payload)

    def _emit(self, event_type: str, **payload: Any) -> None:
        if self.event_callback:
            data = {"type": event_type}
            data.update(payload)
            self.event_callback(data)

    def _require_api_credentials(self) -> tuple[int, str]:
        api_id_raw = str(self.config.get("api_id", "")).strip()
        api_hash = str(self.config.get("api_hash", "")).strip()
        if not api_id_raw or not api_hash:
            raise ValueError("API ID and API Hash are not configured.")
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise ValueError("API ID must be an integer.") from exc
        return api_id, api_hash

    def _ensure_telethon_available(self) -> None:
        if TELETHON_IMPORT_ERROR is not None:
            raise RuntimeError(
                "Telethon is not installed. Run 'pip install -r requirements.txt' first."
            ) from TELETHON_IMPORT_ERROR

    @asynccontextmanager
    async def _connected_client(self) -> Any:
        self._ensure_telethon_available()
        api_id, api_hash = self._require_api_credentials()
        session_base = (self.app_dir / SESSION_FILE_STEM).resolve()
        if not getattr(sys, "frozen", False):
            session_base = (self.data_dir / SESSION_FILE_STEM).resolve()
        client = TelegramClient(str(session_base), api_id, api_hash)
        await client.connect()
        try:
            yield client
        finally:
            await client.disconnect()

    def _ensure_git_protection_for_local_files(self) -> None:
        repo_git_dir = self.app_dir / ".git"
        if not repo_git_dir.exists():
            return

        exclude_path = repo_git_dir / "info" / "exclude"
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        existing_lines: set[str] = set()
        if exclude_path.exists():
            existing_lines = {line.strip() for line in exclude_path.read_text(encoding="utf-8").splitlines()}

        protected_paths = [
            self.get_config_path(),
            self.get_session_file_path(),
            self.get_session_file_path().with_name(f"{self.get_session_file_path().name}-journal"),
            self.get_database_path(),
            self.get_database_path().with_suffix(f"{self.get_database_path().suffix}-wal"),
            self.get_database_path().with_suffix(f"{self.get_database_path().suffix}-shm"),
            self.get_failed_database_path(),
            self.get_failed_database_path().with_suffix(f"{self.get_failed_database_path().suffix}-wal"),
            self.get_failed_database_path().with_suffix(f"{self.get_failed_database_path().suffix}-shm"),
            self.log_dir,
        ]

        new_lines: list[str] = []
        for protected_path in protected_paths:
            try:
                relative_path = protected_path.resolve().relative_to(self.app_dir.resolve())
            except ValueError:
                continue
            git_pattern = relative_path.as_posix()
            if protected_path.is_dir() and not git_pattern.endswith("/"):
                git_pattern += "/"
            if git_pattern not in existing_lines:
                new_lines.append(git_pattern)

        if new_lines:
            prefix = "\n# Telegram Message Cleaner local runtime files\n"
            with exclude_path.open("a", encoding="utf-8") as file:
                file.write(prefix)
                for line in new_lines:
                    file.write(f"{line}\n")

    def _migrate_legacy_runtime_files(self) -> None:
        if getattr(sys, "frozen", False):
            return
        if self.app_dir.resolve() == self.data_dir.resolve():
            return

        legacy_paths = [
            self.app_dir / CONFIG_FILE_NAME,
            self.app_dir / f"{SESSION_FILE_STEM}.session",
            self.app_dir / f"{SESSION_FILE_STEM}.session-journal",
            self.app_dir / DB_FILE_NAME,
            self.app_dir / f"{DB_FILE_NAME}-wal",
            self.app_dir / f"{DB_FILE_NAME}-shm",
            self.app_dir / FAILED_DB_FILE_NAME,
            self.app_dir / f"{FAILED_DB_FILE_NAME}-wal",
            self.app_dir / f"{FAILED_DB_FILE_NAME}-shm",
            self.app_dir / "TelegramMessageCleaner_Logs",
        ]

        for source_path in legacy_paths:
            if not source_path.exists():
                continue

            target_path = self.data_dir / source_path.name
            if source_path.is_dir():
                self._move_legacy_directory(source_path, target_path)
            else:
                self._move_legacy_file(source_path, target_path)

    def _move_legacy_file(self, source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            shutil.move(str(source_path), str(target_path))
            return

        if source_path.stat().st_size == 0:
            source_path.unlink()
            return

        backup_target = self._make_non_conflicting_target(target_path)
        shutil.move(str(source_path), str(backup_target))

    def _move_legacy_directory(self, source_path: Path, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            shutil.move(str(source_path), str(target_path))
            return

        for child in source_path.iterdir():
            child_target = target_path / child.name
            if child.is_dir():
                self._move_legacy_directory(child, child_target)
            else:
                self._move_legacy_file(child, child_target)

        if not any(source_path.iterdir()):
            source_path.rmdir()

    def _make_non_conflicting_target(self, target_path: Path) -> Path:
        counter = 1
        while True:
            candidate = target_path.with_name(f"{target_path.stem}_legacy_{counter}{target_path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _utc_now(self) -> Any:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)

    async def _get_auth_status_async(self) -> dict[str, Any]:
        try:
            self._require_api_credentials()
        except ValueError:
            return {"status": "not configured", "account": None}

        try:
            async with self._connected_client() as client:
                authorized = await client.is_user_authorized()
                if not authorized:
                    return {"status": "unauthorized", "account": None}
                me = await client.get_me()
                return {"status": "authorized", "account": self._serialize_account(me)}
        except Exception as exc:
            self._log("error", "Failed to fetch auth status.", error=format_exception_message(exc))
            return {"status": "auth error", "account": None, "error": format_exception_message(exc)}

    def _describe_code_delivery_type(self, sent_code_type: Any) -> str:
        if isinstance(sent_code_type, types.auth.SentCodeTypeApp):
            return "Telegram app"
        if isinstance(sent_code_type, types.auth.SentCodeTypeSms):
            return "SMS"
        if isinstance(sent_code_type, types.auth.SentCodeTypeFirebaseSms):
            return "Firebase SMS / device verification"
        if isinstance(sent_code_type, types.auth.SentCodeTypeCall):
            return "phone call"
        if isinstance(sent_code_type, types.auth.SentCodeTypeFlashCall):
            return "flash call"
        if isinstance(sent_code_type, types.auth.SentCodeTypeMissedCall):
            return "missed call"
        if isinstance(sent_code_type, types.auth.SentCodeTypeFragmentSms):
            return "Fragment SMS"
        if isinstance(sent_code_type, types.auth.SentCodeTypeEmailCode):
            return "email"
        if isinstance(sent_code_type, types.auth.SentCodeTypeSetUpEmailRequired):
            return "email setup required"
        if isinstance(sent_code_type, types.auth.SentCodeTypeSmsPhrase):
            return "SMS phrase"
        if isinstance(sent_code_type, types.auth.SentCodeTypeSmsWord):
            return "SMS word"
        return sent_code_type.__class__.__name__

    def _build_code_delivery_hint(self, result: Any) -> str:
        delivery = self._describe_code_delivery_type(getattr(result, "type", None))
        timeout = getattr(result, "timeout", None)
        next_type = getattr(result, "next_type", None)
        next_delivery = self._describe_code_delivery_type(next_type) if next_type is not None else None

        if delivery == "Telegram app":
            message = (
                "Telegram sent the login code to your Telegram app on an already signed-in device. "
                "This attempt was not sent by SMS."
            )
        elif delivery == "Firebase SMS / device verification":
            message = (
                "Telegram requested device-based verification / Firebase SMS. "
                "Check the phone linked to this account."
            )
        else:
            message = f"Telegram requested delivery by {delivery}."

        if next_delivery:
            message += f" If needed, the next fallback may be {next_delivery}."
        if timeout not in (None, 0):
            message += f" Approximate wait before retry: {timeout} sec."
        return message

    async def _send_code_async(self, phone_number: str | None) -> dict[str, Any]:
        phone = (phone_number or self.config.get("phone_number") or "").strip()
        if not phone:
            raise ValueError("Phone number is required.")

        self.save_config({"phone_number": phone})
        async with self._connected_client() as client:
            try:
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self._log("info", "Telegram account is already authorized on this device session.")
                    return {
                        "status": "authorized",
                        "account": self._serialize_account(me),
                        "info_message": "This app session is already authorized. You do not need a new login code.",
                    }
                result = await client.send_code_request(phone)
            except errors.ApiIdInvalidError as exc:
                raise ValueError("Invalid API ID or API Hash.") from exc
            except errors.PhoneNumberInvalidError as exc:
                raise ValueError("Invalid phone number.") from exc
            except errors.FloodWaitError as exc:
                raise ValueError(f"Telegram asked to wait {exc.seconds} sec before requesting another code.") from exc
            except errors.PhoneNumberFloodError as exc:
                raise ValueError("Too many code requests for this phone number. Please wait and try again later.") from exc
            except errors.PhoneNumberBannedError as exc:
                raise ValueError("This phone number is banned by Telegram.") from exc

        self._pending_phone_number = phone
        self._pending_phone_code_hash = result.phone_code_hash
        info_message = self._build_code_delivery_hint(result)
        self._log("info", "Telegram login code requested.", delivery=info_message)
        return {"status": "code sent", "info_message": info_message}

    async def _sign_in_async(self, login_code: str, phone_number: str | None) -> dict[str, Any]:
        phone = (phone_number or self._pending_phone_number or self.config.get("phone_number") or "").strip()
        if not phone:
            raise ValueError("Phone number is required before sign in.")
        if not login_code.strip():
            raise ValueError("Login code is required.")
        if not self._pending_phone_code_hash:
            raise ValueError("No pending login code request found. Send the code again.")

        async with self._connected_client() as client:
            try:
                await client.sign_in(
                    phone=phone,
                    code=login_code.strip(),
                    phone_code_hash=self._pending_phone_code_hash,
                )
                me = await client.get_me()
            except errors.SessionPasswordNeededError:
                self._log("info", "Telegram requested 2FA password.")
                return {"status": "2FA required"}
            except errors.PhoneCodeInvalidError as exc:
                raise ValueError("Invalid login code.") from exc
            except errors.PhoneCodeExpiredError as exc:
                raise ValueError("Login code expired. Send a new code.") from exc

        self._pending_phone_code_hash = None
        self._log("info", "Telegram sign in completed.")
        return {"status": "authorized", "account": self._serialize_account(me)}

    async def _submit_password_async(self, password: str) -> dict[str, Any]:
        if not password:
            raise ValueError("2FA password is required.")
        async with self._connected_client() as client:
            try:
                await client.sign_in(password=password)
                me = await client.get_me()
            except errors.PasswordHashInvalidError as exc:
                raise ValueError("Invalid 2FA password.") from exc

        self._pending_phone_code_hash = None
        self._log("info", "2FA sign in completed.")
        return {"status": "authorized", "account": self._serialize_account(me)}

    async def _logout_async(self) -> dict[str, Any]:
        try:
            async with self._connected_client() as client:
                if await client.is_user_authorized():
                    await client.log_out()
        except Exception as exc:
            self._log("warning", "Logout encountered a Telegram error.", error=format_exception_message(exc))

        for path in (
            self.get_session_file_path(),
            self.get_session_file_path().with_name(f"{self.get_session_file_path().name}-journal"),
        ):
            if path.exists():
                path.unlink()

        self._log("info", "Logged out and removed the local session file.")
        return {"status": "unauthorized", "account": None}

    async def _list_groups_async(self) -> list[dict[str, Any]]:
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")

            dialogs: list[dict[str, Any]] = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if getattr(entity, "megagroup", False):
                    chat_type = "megagroup"
                elif getattr(entity, "broadcast", False):
                    chat_type = "channel"
                elif getattr(entity, "first_name", None) or getattr(entity, "last_name", None):
                    chat_type = "user"
                else:
                    chat_type = "chat"

                info = {
                    "title": dialog.name,
                    "id": str(utils.get_peer_id(entity)),
                    "username": getattr(entity, "username", None),
                    "type": chat_type,
                }
                dialogs.append(info)
                self._log(
                    "info",
                    "Dialog found.",
                    title=info["title"],
                    chat_id=info["id"],
                    username=info["username"] or "",
                    chat_type=info["type"],
                )
            return dialogs

    async def _get_chat_overview_async(self, chat_input: str) -> dict[str, Any]:
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")

            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            username = getattr(entity, "username", None)
            chat_type = self._detect_chat_type(entity)
            self.storage.upsert_chat(chat_id, title, username, chat_type, "ready")
            state = self.storage.get_status_counts(chat_id)
            recent_run = self.storage.get_recent_run(chat_id)
            overview = {
                "chat_id": chat_id,
                "title": title,
                "username": username,
                "chat_type": chat_type,
                "counts": state,
                "index_state": self.storage.get_chat_index_state(chat_id),
                "recent_run": recent_run,
            }
            self._emit("chat_overview", overview=overview)
            return overview

    async def _index_messages_async(
        self,
        chat_input: str,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> dict[str, Any]:
        control.reset()
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")
            me = await client.get_me()
            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            username = getattr(entity, "username", None)
            chat_type = self._detect_chat_type(entity)
            self.storage.upsert_chat(chat_id, title, username, chat_type, "indexing")
            run_id = self.storage.create_run(chat_id, "index")
            index_state = self.storage.get_chat_index_state(chat_id)
            self._log(
                "info",
                "Indexing started.",
                chat_id=chat_id,
                title=title,
                resume_from_message_id=index_state.get("next_oldest_message_id"),
                newest_indexed_message_id=index_state.get("newest_indexed_message_id"),
            )
            try:
                indexed_count = await self._run_indexing(client, me.id, entity, chat_id, title, control, run_id, date_range, type_filter)
                final_counts = self._emit_progress(chat_id, title, "indexing-complete", run_id=run_id, date_range=date_range, type_filter=type_filter)
                final_status = control.terminal_status() or "completed"
                self.storage.update_chat_status(chat_id, final_status, indexed=bool(final_counts.get("index_complete")))
                self.storage.finish_run(run_id, final_status, final_counts)
                self._log("info", "Indexing finished.", chat_id=chat_id, title=title, indexed=indexed_count)
                return {
                    "status": final_status,
                    "chat_id": chat_id,
                    "title": title,
                    "counts": final_counts,
                }
            except Exception:
                error_counts = self.storage.get_status_counts(chat_id)
                self.storage.update_chat_status(chat_id, "error")
                self.storage.finish_run(run_id, "error", error_counts)
                raise

    async def _start_cleanup_async(
        self,
        chat_input: str,
        batch_size: int,
        pause_seconds: float,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> dict[str, Any]:
        control.reset()
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")
            me = await client.get_me()
            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            username = getattr(entity, "username", None)
            chat_type = self._detect_chat_type(entity)
            self.storage.upsert_chat(chat_id, title, username, chat_type, "indexing")
            run_id = self.storage.create_run(chat_id, "cleanup")
            self._log("info", "Cleanup started.", chat_id=chat_id, title=title, batch_size=batch_size, pause_seconds=pause_seconds)
            try:
                await self._run_indexing(client, me.id, entity, chat_id, title, control, run_id, date_range, type_filter)
                terminal = control.terminal_status()
                if terminal:
                    counts = self._emit_progress(chat_id, title, terminal, run_id=run_id, date_range=date_range, type_filter=type_filter)
                    self.storage.update_chat_status(chat_id, terminal, indexed=bool(counts.get("index_complete")))
                    self.storage.finish_run(run_id, terminal, counts)
                    self._log("info", f"Cleanup {terminal} after indexing.", chat_id=chat_id, title=title)
                    return {"status": terminal, "chat_id": chat_id, "title": title, "counts": counts}

                self.storage.update_chat_status(chat_id, "deleting", indexed=True)
                counts = await self._run_delete_loop(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    source_status="pending",
                    batch_size=batch_size,
                    pause_seconds=pause_seconds,
                    control=control,
                    run_id=run_id,
                    date_range=date_range,
                    type_filter=type_filter,
                )
                terminal = control.terminal_status()
                if terminal:
                    self.storage.update_chat_status(chat_id, terminal, indexed=True)
                    self.storage.finish_run(run_id, terminal, counts)
                    self._log("info", f"Cleanup {terminal}.", chat_id=chat_id, title=title)
                    return {"status": terminal, "chat_id": chat_id, "title": title, "counts": counts}

                final_status = "completed_with_failures" if counts["pending"] == 0 and counts["failed"] > 0 else "completed"
                self.storage.update_chat_status(chat_id, final_status, indexed=True)
                self.storage.finish_run(run_id, final_status, counts)
                self._log("info", "Cleanup finished.", chat_id=chat_id, title=title, status=final_status)
                self.storage.clear_chat_workspace(chat_id)
                self._log("info", "Main progress workspace cleared after cleanup.", chat_id=chat_id, title=title)
                return {"status": final_status, "chat_id": chat_id, "title": title, "counts": counts}
            except Exception:
                error_counts = self.storage.get_status_counts(chat_id)
                self.storage.update_chat_status(chat_id, "error")
                self.storage.finish_run(run_id, "error", error_counts)
                raise

    async def _delete_indexed_only_async(
        self,
        chat_input: str,
        batch_size: int,
        pause_seconds: float,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> dict[str, Any]:
        control.reset()
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")

            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            username = getattr(entity, "username", None)
            chat_type = self._detect_chat_type(entity)
            self.storage.upsert_chat(chat_id, title, username, chat_type, "deleting-indexed-only")
            run_id = self.storage.create_run(chat_id, "delete_indexed_only")
            counts_before = self.storage.get_status_counts(
                chat_id,
                date_range.start_iso,
                date_range.end_iso,
                type_filter.storage_filter,
            )
            self._log(
                "info",
                "Deleting already indexed pending messages without a new indexing pass.",
                chat_id=chat_id,
                title=title,
                pending=counts_before.get("pending", 0),
                index_complete=counts_before.get("index_complete"),
            )
            try:
                counts = await self._run_delete_loop(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    source_status="pending",
                    batch_size=batch_size,
                    pause_seconds=pause_seconds,
                    control=control,
                    run_id=run_id,
                    date_range=date_range,
                    type_filter=type_filter,
                )
                terminal = control.terminal_status()
                if terminal:
                    self.storage.update_chat_status(chat_id, terminal, indexed=bool(counts.get("index_complete")))
                    self.storage.finish_run(run_id, terminal, counts)
                    self._log("info", f"Delete indexed only {terminal}.", chat_id=chat_id, title=title)
                    return {"status": terminal, "chat_id": chat_id, "title": title, "counts": counts}

                index_complete = bool(counts.get("index_complete"))
                if counts["pending"] == 0 and counts["failed"] > 0:
                    final_status = "completed_with_failures"
                elif counts["pending"] == 0 and not index_complete:
                    final_status = "partial_deleted_waiting_for_more_indexing"
                else:
                    final_status = "completed"

                self.storage.update_chat_status(chat_id, final_status, indexed=index_complete)
                self.storage.finish_run(run_id, final_status, counts)
                self._log("info", "Delete indexed only finished.", chat_id=chat_id, title=title, status=final_status)
                if counts["pending"] == 0:
                    self.storage.clear_chat_workspace(chat_id)
                    self._log("info", "Main progress workspace cleared after delete indexed only.", chat_id=chat_id, title=title)
                return {"status": final_status, "chat_id": chat_id, "title": title, "counts": counts}
            except Exception:
                error_counts = self.storage.get_status_counts(chat_id)
                self.storage.update_chat_status(chat_id, "error")
                self.storage.finish_run(run_id, "error", error_counts)
                raise

    async def _retry_failed_async(
        self,
        chat_input: str,
        batch_size: int,
        pause_seconds: float,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> dict[str, Any]:
        control.reset()
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")

            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            username = getattr(entity, "username", None)
            chat_type = self._detect_chat_type(entity)
            self.storage.upsert_chat(chat_id, title, username, chat_type, "retrying-failed")
            run_id = self.storage.create_run(chat_id, "retry_failed")
            self.storage.update_chat_status(chat_id, "retrying-failed", indexed=True)
            self.storage.reset_failed_to_pending(
                chat_id,
                date_range.start_iso,
                date_range.end_iso,
                type_filter.storage_filter,
            )
            self._log("info", "Retry failed started.", chat_id=chat_id, title=title)
            try:
                counts = await self._run_delete_loop(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    source_status="pending",
                    batch_size=batch_size,
                    pause_seconds=pause_seconds,
                    control=control,
                    run_id=run_id,
                    date_range=date_range,
                    type_filter=type_filter,
                )
                terminal = control.terminal_status()
                if terminal:
                    self.storage.update_chat_status(chat_id, terminal, indexed=True)
                    self.storage.finish_run(run_id, terminal, counts)
                    self._log("info", f"Retry failed {terminal}.", chat_id=chat_id, title=title)
                    return {"status": terminal, "chat_id": chat_id, "title": title, "counts": counts}

                final_status = "completed_with_failures" if counts["failed"] > 0 else "completed"
                self.storage.update_chat_status(chat_id, final_status, indexed=True)
                self.storage.finish_run(run_id, final_status, counts)
                self._log("info", "Retry failed finished.", chat_id=chat_id, title=title, status=final_status)
                self.storage.clear_chat_workspace(chat_id)
                self._log("info", "Main progress workspace cleared after retry failed.", chat_id=chat_id, title=title)
                return {"status": final_status, "chat_id": chat_id, "title": title, "counts": counts}
            except Exception:
                error_counts = self.storage.get_status_counts(chat_id)
                self.storage.update_chat_status(chat_id, "error")
                self.storage.finish_run(run_id, "error", error_counts)
                raise

    async def _run_indexing(
        self,
        client: TelegramClient,
        my_user_id: int,
        entity: Any,
        chat_id: str,
        title: str,
        control: RunControl,
        run_id: int,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> int:
        self._emit_progress(chat_id, title, "indexing", date_range=date_range, type_filter=type_filter)
        state = self.storage.get_chat_index_state(chat_id)
        indexed_total = 0

        if date_range.is_bounded or not type_filter.is_all:
            self._log(
                "info",
                "Filtered indexing started.",
                chat_id=chat_id,
                title=title,
                date_from=date_range.start_iso or "first",
                date_to=date_range.end_iso or "last",
                message_types="all" if type_filter.is_all else ",".join(sorted(type_filter.selected)),
            )
            indexed_total += await self._index_message_stream(
                client=client,
                entity=entity,
                chat_id=chat_id,
                title=title,
                control=control,
                run_id=run_id,
                from_user=my_user_id,
                update_newest=False,
                update_resume_cursor=False,
                phase_label="indexing-filtered",
                date_range=date_range,
                type_filter=type_filter,
            )
            if control.terminal_status():
                self.storage.update_chat_status(chat_id, "indexing-interrupted", indexed=False)
                return indexed_total
            self.storage.update_chat_status(chat_id, "indexed-filtered", indexed=False)
            counts = self._emit_progress(
                chat_id,
                title,
                "indexing-filtered-complete",
                run_id=run_id,
                date_range=date_range,
                type_filter=type_filter,
            )
            self._log(
                "info",
                "Filtered indexing complete.",
                chat_id=chat_id,
                title=title,
                indexed=counts["indexed"],
                date_from=date_range.start_iso or "first",
                date_to=date_range.end_iso or "last",
                message_types="all" if type_filter.is_all else ",".join(sorted(type_filter.selected)),
            )
            return indexed_total

        newest_message_id = self._as_int_or_none(state.get("newest_indexed_message_id"))
        resume_older_from = self._as_int_or_none(state.get("next_oldest_message_id"))
        index_complete = bool(state.get("index_complete"))

        if newest_message_id is not None:
            indexed_total += await self._index_message_stream(
                client=client,
                entity=entity,
                chat_id=chat_id,
                title=title,
                control=control,
                run_id=run_id,
                from_user=my_user_id,
                min_id=newest_message_id,
                update_newest=True,
                update_resume_cursor=False,
                phase_label="indexing-newer",
                date_range=date_range,
                type_filter=type_filter,
            )
            newest_message_id = self._as_int_or_none(self.storage.get_chat_index_state(chat_id).get("newest_indexed_message_id"))

        if control.terminal_status():
            counts = self._emit_progress(chat_id, title, "indexing-interrupted", date_range=date_range, type_filter=type_filter)
            self.storage.update_chat_status(chat_id, "indexing-interrupted", indexed=False)
            return indexed_total

        if not index_complete:
            indexed_total += await self._index_message_stream(
                client=client,
                entity=entity,
                chat_id=chat_id,
                title=title,
                control=control,
                run_id=run_id,
                from_user=my_user_id,
                max_id=resume_older_from,
                update_newest=newest_message_id is None,
                update_resume_cursor=True,
                phase_label="indexing-history",
                date_range=date_range,
                type_filter=type_filter,
            )

        counts = self._emit_progress(chat_id, title, "indexing", date_range=date_range, type_filter=type_filter)
        current_state = self.storage.get_chat_index_state(chat_id)
        if control.terminal_status():
            self.storage.update_chat_status(chat_id, "indexing-interrupted", indexed=False)
            self._log(
                "info",
                "Indexing interrupted and saved for resume.",
                chat_id=chat_id,
                title=title,
                resume_from_message_id=current_state.get("next_oldest_message_id"),
            )
            return indexed_total

        if bool(current_state.get("index_complete")):
            self.storage.update_chat_status(chat_id, "indexed", indexed=True)
            self._log("info", "Indexing phase complete.", chat_id=chat_id, title=title, indexed=counts["indexed"])
        else:
            self.storage.update_chat_status(chat_id, "indexing-partial", indexed=False)
            self._log(
                "warning",
                "Indexing stopped before the full history was covered, but progress was saved.",
                chat_id=chat_id,
                title=title,
                resume_from_message_id=current_state.get("next_oldest_message_id"),
            )
        return indexed_total

    async def _index_message_stream(
        self,
        client: TelegramClient,
        entity: Any,
        chat_id: str,
        title: str,
        control: RunControl,
        run_id: int,
        from_user: int,
        *,
        min_id: int | None = None,
        max_id: int | None = None,
        update_newest: bool,
        update_resume_cursor: bool,
        phase_label: str,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> int:
        found = 0
        batch: list[tuple[int, str | None, str | None]] = []
        current_newest = self._as_int_or_none(self.storage.get_chat_index_state(chat_id).get("newest_indexed_message_id"))
        current_oldest: int | None = None

        iter_kwargs: dict[str, Any] = {"from_user": from_user}
        if min_id is not None:
            iter_kwargs["min_id"] = min_id
        if max_id is not None:
            iter_kwargs["max_id"] = max_id

        async for message in client.iter_messages(entity, **iter_kwargs):
            if control.terminal_status():
                break

            raw_date = getattr(message, "date", None)
            normalized_date = normalize_message_datetime(raw_date) if raw_date else None
            if date_range.end and normalized_date and normalized_date > date_range.end:
                continue
            if date_range.start and normalized_date and normalized_date < date_range.start:
                break
            if not date_range.contains(normalized_date):
                continue

            message_type = self._detect_message_type(message)
            if not type_filter.contains(message_type):
                continue

            message_id = int(message.id)
            message_date = normalized_date.isoformat() if normalized_date else None
            batch.append((message_id, message_date, message_type))
            found += 1
            current_newest = message_id if current_newest is None else max(current_newest, message_id)
            current_oldest = message_id if current_oldest is None else min(current_oldest, message_id)

            if len(batch) >= 500:
                self.storage.bulk_upsert_messages(chat_id, batch)
                batch.clear()
                state_kwargs: dict[str, Any] = {}
                if update_newest:
                    state_kwargs["newest_indexed_message_id"] = current_newest
                if update_resume_cursor:
                    state_kwargs["next_oldest_message_id"] = current_oldest
                    state_kwargs["index_complete"] = False
                self.storage.update_chat_index_state(chat_id, **state_kwargs)
                counts = self._emit_progress(chat_id, title, phase_label, date_range=date_range, type_filter=type_filter)
                self.storage.set_run_status(run_id, "indexing", counts)
                self._log("info", "Indexing progress.", chat_id=chat_id, title=title, indexed=counts["indexed"])

        if batch:
            self.storage.bulk_upsert_messages(chat_id, batch)

        if current_oldest is not None or current_newest is not None:
            state_kwargs: dict[str, Any] = {}
            if update_newest:
                state_kwargs["newest_indexed_message_id"] = current_newest
            if update_resume_cursor:
                state_kwargs["next_oldest_message_id"] = current_oldest
                state_kwargs["index_complete"] = False
            self.storage.update_chat_index_state(chat_id, **state_kwargs)

        if not control.terminal_status():
            if update_resume_cursor:
                self.storage.update_chat_index_state(chat_id, next_oldest_message_id=None, index_complete=True)
            elif update_newest and current_newest is not None and bool(self.storage.get_chat_index_state(chat_id).get("index_complete")):
                self.storage.update_chat_index_state(chat_id, newest_indexed_message_id=current_newest)

        return found

    def _detect_message_type(self, message: Any) -> str:
        media = getattr(message, "media", None)
        if isinstance(media, getattr(types, "MessageMediaPoll", ())):
            return "poll"
        if getattr(message, "sticker", None):
            return "sticker"
        if getattr(message, "gif", None):
            return "gif"
        if getattr(message, "voice", None):
            return "voice"
        if getattr(message, "video_note", None):
            return "video_note"
        if getattr(message, "video", None):
            return "video"
        if getattr(message, "photo", None):
            return "photo"
        if self._message_has_link(message):
            return "links"
        if getattr(message, "document", None):
            return "file"
        if getattr(message, "message", None):
            return "text"
        return "other"

    def _message_has_link(self, message: Any) -> bool:
        if getattr(message, "web_preview", None):
            return True
        url_entity_types = (
            getattr(types, "MessageEntityUrl", None),
            getattr(types, "MessageEntityTextUrl", None),
            getattr(types, "MessageEntityEmail", None),
        )
        url_entity_types = tuple(entity_type for entity_type in url_entity_types if entity_type is not None)
        if not url_entity_types:
            return False
        return any(isinstance(entity, url_entity_types) for entity in (getattr(message, "entities", None) or []))

    async def _run_delete_loop(
        self,
        client: TelegramClient,
        entity: Any,
        chat_id: str,
        title: str,
        source_status: str,
        batch_size: int,
        pause_seconds: float,
        control: RunControl,
        run_id: int,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> dict[str, Any]:
        batch_number = 0
        run_started_at = time.monotonic()
        initial_counts = self.storage.get_status_counts(
            chat_id,
            date_range.start_iso,
            date_range.end_iso,
            type_filter.storage_filter,
        )
        deleted_at_start = int(initial_counts["deleted"])

        while True:
            current_ids = self.storage.get_message_ids_by_status(
                chat_id,
                source_status,
                limit=batch_size,
                date_from=date_range.start_iso,
                date_to=date_range.end_iso,
                message_types=type_filter.storage_filter,
            )
            if not current_ids:
                break

            batch_number += 1
            self._emit_progress(
                chat_id,
                title,
                "deleting",
                batch_number=batch_number,
                run_started_at=run_started_at,
                deleted_at_start=deleted_at_start,
                date_range=date_range,
                type_filter=type_filter,
            )
            try:
                deleted_ids, remaining_ids = await self._delete_batch_with_verification(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    message_ids=current_ids,
                    batch_number=batch_number,
                    run_started_at=run_started_at,
                    deleted_at_start=deleted_at_start,
                    control=control,
                    date_range=date_range,
                    type_filter=type_filter,
                )

                recovered_ids: list[int] = []
                if remaining_ids:
                    recovered_ids = await self._retry_remaining_messages_individually(
                        client=client,
                        entity=entity,
                        chat_id=chat_id,
                        title=title,
                        message_ids=remaining_ids,
                        batch_number=batch_number,
                        run_started_at=run_started_at,
                        deleted_at_start=deleted_at_start,
                        control=control,
                        date_range=date_range,
                        type_filter=type_filter,
                    )
                    remaining_ids = [message_id for message_id in remaining_ids if message_id not in recovered_ids]

                successful_ids = [*deleted_ids, *recovered_ids]
                if successful_ids:
                    self.storage.mark_messages_deleted(chat_id, successful_ids)

                if remaining_ids:
                    error_message = "Telegram delete request completed, but the messages still exist after verification."
                    dates = self.storage.get_message_dates(chat_id, remaining_ids)
                    self.storage.mark_messages_failed(chat_id, remaining_ids, error_message)
                    self.storage.record_failed_batch(chat_id, remaining_ids, "DeleteVerificationFailed", error_message)
                    self._log(
                        "warning",
                        "Batch partially deleted. Some messages still exist after verification.",
                        chat_id=chat_id,
                        title=title,
                        batch_number=batch_number,
                        deleted_count=len(successful_ids),
                        remaining_count=len(remaining_ids),
                        message_ids=",".join(str(message_id) for message_id in remaining_ids),
                        message_dates=",".join(str(dates.get(message_id)) for message_id in remaining_ids),
                    )
                else:
                    self._log(
                        "info",
                        "Batch deleted and verified.",
                        chat_id=chat_id,
                        title=title,
                        batch_number=batch_number,
                        batch_size=len(current_ids),
                    )
            except Exception as exc:
                error_message = format_exception_message(exc)
                dates = self.storage.get_message_dates(chat_id, current_ids)
                self.storage.mark_messages_failed(chat_id, current_ids, error_message)
                self.storage.record_failed_batch(chat_id, current_ids, exc.__class__.__name__, error_message)
                self._log(
                    "error",
                    "Batch failed.",
                    chat_id=chat_id,
                    title=title,
                    batch_number=batch_number,
                    error=error_message,
                    message_ids=",".join(str(message_id) for message_id in current_ids),
                    message_dates=",".join(str(dates.get(message_id)) for message_id in current_ids),
                )

            counts = self._emit_progress(
                chat_id,
                title,
                "deleting",
                batch_number=batch_number,
                run_started_at=run_started_at,
                deleted_at_start=deleted_at_start,
                date_range=date_range,
                type_filter=type_filter,
            )
            self.storage.set_run_status(run_id, "running", counts)

            terminal = control.terminal_status()
            if terminal:
                return counts

            await self._inter_batch_pause(
                chat_id,
                title,
                pause_seconds,
                batch_number,
                control,
                run_started_at=run_started_at,
                deleted_at_start=deleted_at_start,
                date_range=date_range,
                type_filter=type_filter,
            )

        final_counts = self._emit_progress(
            chat_id,
            title,
            "deleting-complete",
            batch_number=batch_number,
            run_started_at=run_started_at,
            deleted_at_start=deleted_at_start,
            date_range=date_range,
            type_filter=type_filter,
        )
        return final_counts

    async def _delete_batch_with_verification(
        self,
        client: TelegramClient,
        entity: Any,
        chat_id: str,
        title: str,
        message_ids: list[int],
        batch_number: int,
        run_started_at: float,
        deleted_at_start: int,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> tuple[list[int], list[int]]:
        await self._delete_batch_with_flood_wait(
            client=client,
            entity=entity,
            chat_id=chat_id,
            title=title,
            message_ids=message_ids,
            batch_number=batch_number,
            run_started_at=run_started_at,
            deleted_at_start=deleted_at_start,
            control=control,
            date_range=date_range,
            type_filter=type_filter,
        )
        return await self._verify_deleted_message_ids(client, entity, message_ids)

    async def _delete_batch_with_flood_wait(
        self,
        client: TelegramClient,
        entity: Any,
        chat_id: str,
        title: str,
        message_ids: list[int],
        batch_number: int,
        run_started_at: float,
        deleted_at_start: int,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> None:
        while True:
            try:
                await client.delete_messages(entity, message_ids, revoke=True)
                return
            except errors.FloodWaitError as exc:
                wait_seconds = int(exc.seconds) + 5
                self._log(
                    "warning",
                    "Telegram FloodWait encountered. Waiting before retrying the current batch.",
                    chat_id=chat_id,
                    title=title,
                    batch_number=batch_number,
                    wait_seconds=wait_seconds,
                )
                for remaining in range(wait_seconds, 0, -1):
                    self._emit_progress(
                        chat_id,
                        title,
                        "waiting",
                        batch_number=batch_number,
                        run_started_at=run_started_at,
                        deleted_at_start=deleted_at_start,
                        flood_wait_seconds=remaining,
                        date_range=date_range,
                        type_filter=type_filter,
                    )
                    await asyncio.sleep(1)
                continue

    async def _verify_deleted_message_ids(
        self,
        client: TelegramClient,
        entity: Any,
        message_ids: list[int],
    ) -> tuple[list[int], list[int]]:
        messages = await client.get_messages(entity, ids=message_ids)
        if not isinstance(messages, list):
            messages = [messages]

        deleted_ids: list[int] = []
        remaining_ids: list[int] = []
        for expected_id, message in zip(message_ids, messages):
            if message is None or isinstance(message, types.MessageEmpty):
                deleted_ids.append(expected_id)
            else:
                remaining_ids.append(expected_id)
        return deleted_ids, remaining_ids

    async def _retry_remaining_messages_individually(
        self,
        client: TelegramClient,
        entity: Any,
        chat_id: str,
        title: str,
        message_ids: list[int],
        batch_number: int,
        run_started_at: float,
        deleted_at_start: int,
        control: RunControl,
        date_range: MessageDateRange,
        type_filter: MessageTypeFilter,
    ) -> list[int]:
        recovered_ids: list[int] = []
        for message_id in message_ids:
            if control.terminal_status():
                break
            try:
                deleted_ids, remaining_ids = await self._delete_batch_with_verification(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    message_ids=[message_id],
                    batch_number=batch_number,
                    run_started_at=run_started_at,
                    deleted_at_start=deleted_at_start,
                    control=control,
                    date_range=date_range,
                    type_filter=type_filter,
                )
                if deleted_ids and not remaining_ids:
                    recovered_ids.extend(deleted_ids)
                    self._log(
                        "info",
                        "Recovered a message that remained after the batch delete by retrying it individually.",
                        chat_id=chat_id,
                        title=title,
                        batch_number=batch_number,
                        message_id=message_id,
                    )
            except Exception as exc:
                self._log(
                    "warning",
                    "Individual retry for a remaining message failed.",
                    chat_id=chat_id,
                    title=title,
                    batch_number=batch_number,
                    message_id=message_id,
                    error=format_exception_message(exc),
                )
        return recovered_ids

    async def _inter_batch_pause(
        self,
        chat_id: str,
        title: str,
        pause_seconds: float,
        batch_number: int,
        control: RunControl,
        run_started_at: float | None = None,
        deleted_at_start: int = 0,
        date_range: MessageDateRange | None = None,
        type_filter: MessageTypeFilter | None = None,
    ) -> None:
        if pause_seconds <= 0:
            return
        for chunk in safe_sleep_chunks(pause_seconds):
            if control.terminal_status():
                return
            self._emit_progress(
                chat_id,
                title,
                "sleeping",
                batch_number=batch_number,
                run_started_at=run_started_at,
                deleted_at_start=deleted_at_start,
                date_range=date_range,
                type_filter=type_filter,
            )
            await asyncio.sleep(chunk)

    def _emit_progress(
        self,
        chat_id: str,
        title: str,
        phase: str,
        batch_number: int = 0,
        run_started_at: float | None = None,
        deleted_at_start: int = 0,
        flood_wait_seconds: int | None = None,
        run_id: int | None = None,
        date_range: MessageDateRange | None = None,
        type_filter: MessageTypeFilter | None = None,
    ) -> dict[str, Any]:
        active_range = date_range or MessageDateRange()
        active_types = type_filter or MessageTypeFilter()
        counts = self.storage.get_status_counts(
            chat_id,
            active_range.start_iso,
            active_range.end_iso,
            active_types.storage_filter,
        )
        indexed = int(counts["indexed"])
        deleted = int(counts["deleted"])
        pending = int(counts["pending"])
        failed = int(counts["failed"])
        total = max(indexed, pending + deleted + failed)
        processed = max(0, total - pending)
        percentage = round((processed / total) * 100, 2) if total else 0.0

        speed_per_minute: float | None = None
        eta_seconds: float | None = None
        note = None
        index_complete = bool(counts.get("index_complete"))
        if run_started_at is not None:
            elapsed_seconds = max(0.0, time.monotonic() - run_started_at)
            deleted_since_start = max(0, deleted - deleted_at_start)
            if elapsed_seconds > 0 and deleted_since_start > 0:
                speed_per_minute = deleted_since_start / (elapsed_seconds / 60)
                if speed_per_minute > 0:
                    eta_seconds = (pending / speed_per_minute) * 60
            if batch_number <= 3 and phase in {"deleting", "waiting", "sleeping"}:
                note = "ETA may be unstable during the first batches."

        snapshot = {
            "chat_id": chat_id,
            "title": title,
            "phase": phase,
            "indexed": indexed,
            "deleted": deleted,
            "pending": pending,
            "failed": failed,
            "total": total,
            "percentage": percentage,
            "index_complete": index_complete,
            "newest_indexed_message_id": counts.get("newest_indexed_message_id"),
            "next_oldest_message_id": counts.get("next_oldest_message_id"),
            "speed_per_minute": speed_per_minute,
            "speed_text": format_speed(speed_per_minute),
            "eta_seconds": eta_seconds,
            "eta_text": "waiting because of Telegram FloodWait" if phase == "waiting" else format_eta(eta_seconds),
            "batch_number": batch_number,
            "flood_wait_seconds": flood_wait_seconds,
            "last_update": counts.get("last_update"),
            "status": counts.get("status"),
            "note": note,
            "run_id": run_id,
            "date_from": active_range.start_iso,
            "date_to": active_range.end_iso,
            "message_types": "all" if active_types.is_all else ",".join(sorted(active_types.selected)),
        }
        self._emit("progress", snapshot=snapshot)
        return snapshot

    async def _resolve_chat_entity(self, client: TelegramClient, chat_input: str) -> Any:
        value = chat_input.strip()
        if not value:
            raise ValueError("Chat ID is required.")
        lookup: str | int
        if value.lstrip("-").isdigit():
            lookup = int(value)
        else:
            lookup = value
        try:
            return await client.get_entity(lookup)
        except (ValueError, errors.UsernameInvalidError, errors.UsernameNotOccupiedError) as exc:
            raise ValueError(f"Unable to resolve chat: {chat_input}") from exc

    def _as_int_or_none(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _get_entity_title(self, entity: Any) -> str:
        title = getattr(entity, "title", None)
        if title:
            return str(title)
        first_name = getattr(entity, "first_name", "") or ""
        last_name = getattr(entity, "last_name", "") or ""
        combined = f"{first_name} {last_name}".strip()
        if combined:
            return combined
        username = getattr(entity, "username", None)
        if username:
            return f"@{username}"
        return str(utils.get_peer_id(entity))

    def _detect_chat_type(self, entity: Any) -> str:
        if getattr(entity, "megagroup", False):
            return "megagroup"
        if getattr(entity, "broadcast", False):
            return "channel"
        if getattr(entity, "first_name", None) or getattr(entity, "last_name", None):
            return "user"
        return "chat"

    def _serialize_account(self, me: Any) -> dict[str, Any]:
        first_name = getattr(me, "first_name", None)
        last_name = getattr(me, "last_name", None)
        username = getattr(me, "username", None)
        phone = getattr(me, "phone", None)
        if username:
            display = f"@{username}"
        elif phone:
            display = f"+{phone}"
        else:
            display = "authorized user"
        return {
            "display": display,
            "username": username,
            "phone": phone,
            "first_name": first_name,
            "last_name": last_name,
        }


def create_cli_event_printer(logger: logging.Logger | None = None) -> EventCallback:
    def printer(event: dict[str, Any]) -> None:
        if event.get("type") == "log":
            print(event.get("message", ""))
        elif event.get("type") == "progress":
            snapshot = event.get("snapshot", {})
            print(
                "[progress] "
                f"phase={snapshot.get('phase')} "
                f"chat_id={snapshot.get('chat_id')} "
                f"indexed={snapshot.get('indexed')} "
                f"deleted={snapshot.get('deleted')} "
                f"pending={snapshot.get('pending')} "
                f"failed={snapshot.get('failed')} "
                f"eta={snapshot.get('eta_text')}"
            )
    return printer
