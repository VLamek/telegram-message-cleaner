from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    from telethon import TelegramClient, errors, utils
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

from telegram_cleanup_logging import format_exception_message, setup_app_logger
from telegram_cleanup_storage import ProgressStorage


APP_NAME = "Telegram Message Cleaner"
CONFIG_FILE_NAME = "telegram_message_cleaner_config.json"
SESSION_FILE_STEM = "telegram_message_cleaner"
DB_FILE_NAME = "telegram_message_cleaner.sqlite3"
SUPPORTED_LANGUAGES = ("en", "ru")
SUPPORTED_THEMES = ("Light", "Dark")

EventCallback = Callable[[dict[str, Any]], None]


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


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
    def __init__(self, app_dir: Path) -> None:
        self.app_dir = app_dir
        self.config_path = app_dir / CONFIG_FILE_NAME
        load_dotenv(app_dir / ".env")

    def default_config(self) -> dict[str, Any]:
        return {
            "api_id": "",
            "api_hash": "",
            "phone_number": "",
            "language": "en",
            "theme": "Light",
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
            data["theme"] = "Light"
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
        self.event_callback = event_callback
        self.config_store = ConfigStore(self.app_dir)
        self.config = self.config_store.load()
        self.logger, self.log_dir = setup_app_logger(self.app_dir)
        self._db_file_override = db_file_override
        self.storage = ProgressStorage(self.get_database_path())
        self._pending_phone_number: str | None = None
        self._pending_phone_code_hash: str | None = None

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def reload_config(self) -> dict[str, Any]:
        self.config = self.config_store.load()
        self.storage = ProgressStorage(self.get_database_path())
        return self.get_config()

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        data = self.config_store.load()
        data.update(updates)
        self.config_store.save(data)
        self.config = data
        self.storage = ProgressStorage(self.get_database_path())
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
            self.storage = ProgressStorage(self.get_database_path())
        return self.get_database_path()

    def get_database_path(self) -> Path:
        db_value = self._db_file_override or self.config.get("db_file") or DB_FILE_NAME
        candidate = Path(str(db_value))
        if not candidate.is_absolute():
            candidate = self.app_dir / candidate
        return candidate.resolve()

    def get_config_path(self) -> Path:
        return self.config_store.config_path.resolve()

    def get_session_file_path(self) -> Path:
        return (self.app_dir / f"{SESSION_FILE_STEM}.session").resolve()

    def delete_local_progress_database(self) -> None:
        db_path = self.get_database_path()
        wal_path = db_path.with_suffix(f"{db_path.suffix}-wal")
        shm_path = db_path.with_suffix(f"{db_path.suffix}-shm")
        for path in (db_path, wal_path, shm_path):
            if path.exists():
                path.unlink()
        self.storage = ProgressStorage(db_path)
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

    def index_messages(self, chat_input: str, control: RunControl | None = None) -> dict[str, Any]:
        return asyncio.run(self._index_messages_async(chat_input, control or RunControl()))

    def start_cleanup(
        self,
        chat_input: str,
        batch_size: int = 100,
        pause_seconds: float = 2.0,
        control: RunControl | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(
            self._start_cleanup_async(
                chat_input=chat_input,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                control=control or RunControl(),
            )
        )

    def retry_failed(
        self,
        chat_input: str,
        batch_size: int = 100,
        pause_seconds: float = 2.0,
        control: RunControl | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(
            self._retry_failed_async(
                chat_input=chat_input,
                batch_size=batch_size,
                pause_seconds=pause_seconds,
                control=control or RunControl(),
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
        client = TelegramClient(str(session_base), api_id, api_hash)
        await client.connect()
        try:
            yield client
        finally:
            await client.disconnect()

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

    async def _send_code_async(self, phone_number: str | None) -> dict[str, Any]:
        phone = (phone_number or self.config.get("phone_number") or "").strip()
        if not phone:
            raise ValueError("Phone number is required.")

        self.save_config({"phone_number": phone})
        async with self._connected_client() as client:
            try:
                result = await client.send_code_request(phone)
            except errors.ApiIdInvalidError as exc:
                raise ValueError("Invalid API ID or API Hash.") from exc
            except errors.PhoneNumberInvalidError as exc:
                raise ValueError("Invalid phone number.") from exc

        self._pending_phone_number = phone
        self._pending_phone_code_hash = result.phone_code_hash
        self._log("info", "Telegram login code sent.")
        return {"status": "code sent"}

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
                "recent_run": recent_run,
            }
            self._emit("chat_overview", overview=overview)
            return overview

    async def _index_messages_async(self, chat_input: str, control: RunControl) -> dict[str, Any]:
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
            self._log("info", "Indexing started.", chat_id=chat_id, title=title)
            try:
                indexed_count = await self._run_indexing(client, me.id, entity, chat_id, title, control, run_id)
                final_counts = self._emit_progress(chat_id, title, "indexing-complete", run_id=run_id)
                final_status = control.terminal_status() or "completed"
                self.storage.update_chat_status(chat_id, final_status, indexed=True)
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
                await self._run_indexing(client, me.id, entity, chat_id, title, control, run_id)
                terminal = control.terminal_status()
                if terminal:
                    counts = self._emit_progress(chat_id, title, terminal, run_id=run_id)
                    self.storage.update_chat_status(chat_id, terminal, indexed=True)
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
    ) -> dict[str, Any]:
        control.reset()
        async with self._connected_client() as client:
            if not await client.is_user_authorized():
                raise PermissionError("Authorize the Telegram account first.")

            entity = await self._resolve_chat_entity(client, chat_input)
            chat_id = str(utils.get_peer_id(entity))
            title = self._get_entity_title(entity)
            run_id = self.storage.create_run(chat_id, "retry_failed")
            self.storage.update_chat_status(chat_id, "retrying-failed", indexed=True)
            self._log("info", "Retry failed started.", chat_id=chat_id, title=title)
            try:
                counts = await self._run_delete_loop(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    source_status="failed",
                    batch_size=batch_size,
                    pause_seconds=pause_seconds,
                    control=control,
                    run_id=run_id,
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
    ) -> int:
        self._emit_progress(chat_id, title, "indexing")
        found = 0
        batch: list[tuple[int, str | None]] = []
        async for message in client.iter_messages(entity):
            if control.terminal_status():
                break
            sender_id = getattr(message, "sender_id", None)
            if sender_id != my_user_id:
                continue

            message_date = message.date.isoformat() if getattr(message, "date", None) else None
            batch.append((int(message.id), message_date))
            found += 1

            if len(batch) >= 500:
                self.storage.bulk_upsert_messages(chat_id, batch)
                batch.clear()
                counts = self._emit_progress(chat_id, title, "indexing")
                self.storage.set_run_status(run_id, "indexing", counts)
                self._log("info", "Indexing progress.", chat_id=chat_id, title=title, indexed=counts["indexed"])
                if control.terminal_status():
                    break

        if batch:
            self.storage.bulk_upsert_messages(chat_id, batch)
        counts = self._emit_progress(chat_id, title, "indexing")
        self.storage.update_chat_status(chat_id, "indexed", indexed=True)
        self._log("info", "Indexing phase complete.", chat_id=chat_id, title=title, indexed=counts["indexed"])
        return found

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
    ) -> dict[str, Any]:
        batch_number = 0
        run_started_at = time.monotonic()
        initial_counts = self.storage.get_status_counts(chat_id)
        deleted_at_start = int(initial_counts["deleted"])

        while True:
            current_ids = self.storage.get_message_ids_by_status(chat_id, source_status, limit=batch_size)
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
            )
            try:
                await self._delete_batch_with_flood_wait(
                    client=client,
                    entity=entity,
                    chat_id=chat_id,
                    title=title,
                    message_ids=current_ids,
                    batch_number=batch_number,
                    run_started_at=run_started_at,
                    deleted_at_start=deleted_at_start,
                    control=control,
                )
                self.storage.mark_messages_deleted(chat_id, current_ids)
                self._log(
                    "info",
                    "Batch deleted.",
                    chat_id=chat_id,
                    title=title,
                    batch_number=batch_number,
                    batch_size=len(current_ids),
                )
            except Exception as exc:
                error_message = format_exception_message(exc)
                self.storage.mark_messages_failed(chat_id, current_ids, error_message)
                self.storage.record_failed_batch(chat_id, current_ids, exc.__class__.__name__, error_message)
                dates = self.storage.get_message_dates(chat_id, current_ids)
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
            )

        final_counts = self._emit_progress(
            chat_id,
            title,
            "deleting-complete",
            batch_number=batch_number,
            run_started_at=run_started_at,
            deleted_at_start=deleted_at_start,
        )
        return final_counts

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
                    )
                    await asyncio.sleep(1)
                continue

    async def _inter_batch_pause(
        self,
        chat_id: str,
        title: str,
        pause_seconds: float,
        batch_number: int,
        control: RunControl,
        run_started_at: float | None = None,
        deleted_at_start: int = 0,
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
    ) -> dict[str, Any]:
        counts = self.storage.get_status_counts(chat_id)
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
