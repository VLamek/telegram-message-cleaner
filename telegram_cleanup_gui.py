from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from telegram_cleanup_core import APP_NAME, DB_FILE_NAME, RunControl, TelegramCleanupCore
from telegram_cleanup_i18n import Translator
from telegram_cleanup_qr import create_qr_photoimage


class TelegramCleanupGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1120x860")
        self.root.minsize(980, 760)

        self.event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.core = TelegramCleanupCore(event_callback=self.event_queue.put)
        self.translator = Translator(self.core.get_config().get("language", "en"))

        self.localized_widgets: list[tuple[Any, str, str]] = []
        self.active_worker: threading.Thread | None = None
        self.active_action: str | None = None
        self.current_control: RunControl | None = None
        self.pending_cleanup_request: dict[str, Any] | None = None
        self.current_auth_status = "not configured"
        self.chat_selector_window: tk.Toplevel | None = None
        self.chat_selector_search_var = tk.StringVar()
        self.chat_selector_dialogs: list[dict[str, Any]] = []
        self.chat_selector_filtered_dialogs: list[dict[str, Any]] = []
        self.qr_login_window: tk.Toplevel | None = None
        self.qr_photoimage: tk.PhotoImage | None = None
        self.qr_url_var = tk.StringVar()
        self.qr_status_var = tk.StringVar()
        self.qr_expires_var = tk.StringVar()
        self.qr_expires_at: datetime | None = None
        self.qr_countdown_job: str | None = None

        self._create_variables()
        self._build_layout()
        self._setup_clipboard_support()
        self._apply_saved_config()
        self._apply_theme()
        self._refresh_translations()
        self._append_log(
            f"App started. Config={self.core.get_config_path()} | "
            f"Session={self.core.get_session_file_path()} | "
            f"DB={self.core.get_database_path()} | Logs={self.core.log_dir}"
        )

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._process_event_queue)
        self._launch_worker("refresh_auth_status", self.core.get_auth_status)

    def _create_variables(self) -> None:
        config = self.core.get_config()

        self.api_id_var = tk.StringVar(value=str(config.get("api_id", "")))
        self.api_hash_var = tk.StringVar(value=str(config.get("api_hash", "")))
        self.phone_number_var = tk.StringVar(value=str(config.get("phone_number", "")))
        self.login_code_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.chat_id_var = tk.StringVar()
        self.batch_size_var = tk.StringVar(value="100")
        self.pause_seconds_var = tk.StringVar(value="2")
        self.db_path_var = tk.StringVar(value=str(self.core.get_database_path()))
        self.require_confirmation_var = tk.BooleanVar(
            value=bool(config.get("require_confirmation_before_deletion", True))
        )
        self.language_var = tk.StringVar(value=config.get("language", "en"))
        self.theme_var = tk.StringVar(value=config.get("theme", "Light"))

        self.auth_status_var = tk.StringVar(value=self.translator.gettext("status_not_configured"))
        self.authorized_as_var = tk.StringVar(value=self.translator.gettext("none"))

        self.phase_value_var = tk.StringVar(value=self.translator.gettext("progress_idle"))
        self.chat_title_value_var = tk.StringVar(value=self.translator.gettext("none"))
        self.chat_id_value_var = tk.StringVar(value=self.translator.gettext("none"))
        self.indexed_value_var = tk.StringVar(value="0")
        self.deleted_value_var = tk.StringVar(value="0")
        self.pending_value_var = tk.StringVar(value="0")
        self.failed_value_var = tk.StringVar(value="0")
        self.percentage_value_var = tk.StringVar(value="0%")
        self.speed_value_var = tk.StringVar(value=self.translator.gettext("calculating"))
        self.eta_value_var = tk.StringVar(value=self.translator.gettext("calculating"))
        self.batch_value_var = tk.StringVar(value="0")
        self.flood_wait_value_var = tk.StringVar(value=self.translator.gettext("none"))

    def _register_widget_text(self, widget: Any, key: str, option: str = "text") -> None:
        self.localized_widgets.append((widget, option, key))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        self.auth_frame = ttk.LabelFrame(self.root)
        self.cleanup_frame = ttk.LabelFrame(self.root)
        self.progress_frame = ttk.LabelFrame(self.root)
        self.logs_frame = ttk.LabelFrame(self.root)
        self.settings_frame = ttk.LabelFrame(self.root)

        self.auth_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        self.cleanup_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self.progress_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        self.logs_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        self.settings_frame.grid(row=4, column=0, sticky="nsew", padx=12, pady=(6, 12))

        self.root.rowconfigure(3, weight=1)
        self.logs_frame.rowconfigure(0, weight=1)
        self.logs_frame.columnconfigure(0, weight=1)

        self._build_auth_section()
        self._build_cleanup_section()
        self._build_progress_section()
        self._build_logs_section()
        self._build_settings_section()

    def _build_auth_section(self) -> None:
        for column in range(6):
            self.auth_frame.columnconfigure(column, weight=1)

        auth_labels = [
            ("api_id_label", 0, 0, "api_id"),
            ("api_hash_label", 0, 2, "api_hash"),
            ("phone_label", 1, 0, "phone_number"),
            ("code_label", 1, 2, "login_code"),
            ("password_label", 1, 4, "two_fa_password"),
        ]

        for attr_name, row, column, key in auth_labels:
            label = ttk.Label(self.auth_frame)
            setattr(self, attr_name, label)
            label.grid(row=row, column=column, sticky="w", padx=6, pady=4)
            self._register_widget_text(label, key)

        self.api_id_entry = ttk.Entry(self.auth_frame, textvariable=self.api_id_var)
        self.api_hash_entry = ttk.Entry(self.auth_frame, textvariable=self.api_hash_var, show="*")
        self.phone_entry = ttk.Entry(self.auth_frame, textvariable=self.phone_number_var)
        self.login_code_entry = ttk.Entry(self.auth_frame, textvariable=self.login_code_var)
        self.password_entry = ttk.Entry(self.auth_frame, textvariable=self.password_var, show="*")

        self.api_id_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        self.api_hash_entry.grid(row=0, column=3, sticky="ew", padx=6, pady=4)
        self.phone_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        self.login_code_entry.grid(row=1, column=3, sticky="ew", padx=6, pady=4)
        self.password_entry.grid(row=1, column=5, sticky="ew", padx=6, pady=4)

        self.save_credentials_button = ttk.Button(self.auth_frame, command=self._save_credentials)
        self.send_code_button = ttk.Button(self.auth_frame, command=self._send_code)
        self.qr_login_button = ttk.Button(self.auth_frame, command=self._start_qr_login)
        self.sign_in_button = ttk.Button(self.auth_frame, command=self._sign_in)
        self.submit_password_button = ttk.Button(self.auth_frame, command=self._submit_password)
        self.logout_button = ttk.Button(self.auth_frame, command=self._logout)

        self.save_credentials_button.grid(row=2, column=0, sticky="ew", padx=6, pady=8)
        self.send_code_button.grid(row=2, column=1, sticky="ew", padx=6, pady=8)
        self.qr_login_button.grid(row=2, column=2, sticky="ew", padx=6, pady=8)
        self.sign_in_button.grid(row=2, column=3, sticky="ew", padx=6, pady=8)
        self.submit_password_button.grid(row=2, column=4, sticky="ew", padx=6, pady=8)
        self.logout_button.grid(row=2, column=5, sticky="ew", padx=6, pady=8)

        self._register_widget_text(self.save_credentials_button, "save_api_credentials")
        self._register_widget_text(self.send_code_button, "send_code")
        self._register_widget_text(self.qr_login_button, "qr_login")
        self._register_widget_text(self.sign_in_button, "sign_in")
        self._register_widget_text(self.submit_password_button, "submit_2fa_password")
        self._register_widget_text(self.logout_button, "logout")

        self.auth_status_label = ttk.Label(self.auth_frame)
        self.authorized_as_label = ttk.Label(self.auth_frame)
        self.auth_status_value_label = ttk.Label(self.auth_frame, textvariable=self.auth_status_var)
        self.authorized_as_value_label = ttk.Label(self.auth_frame, textvariable=self.authorized_as_var)

        self.auth_status_label.grid(row=3, column=0, sticky="w", padx=6, pady=(4, 8))
        self.auth_status_value_label.grid(row=3, column=1, columnspan=2, sticky="w", padx=6, pady=(4, 8))
        self.authorized_as_label.grid(row=3, column=3, sticky="w", padx=6, pady=(4, 8))
        self.authorized_as_value_label.grid(row=3, column=4, columnspan=2, sticky="w", padx=6, pady=(4, 8))

        self._register_widget_text(self.auth_status_label, "auth_status")
        self._register_widget_text(self.authorized_as_label, "authorized_as")

    def _build_cleanup_section(self) -> None:
        for column in range(6):
            self.cleanup_frame.columnconfigure(column, weight=1)

        self.chat_id_label = ttk.Label(self.cleanup_frame)
        self.batch_size_label = ttk.Label(self.cleanup_frame)
        self.pause_label = ttk.Label(self.cleanup_frame)

        self.chat_id_label.grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.batch_size_label.grid(row=0, column=2, sticky="w", padx=6, pady=4)
        self.pause_label.grid(row=0, column=4, sticky="w", padx=6, pady=4)

        self._register_widget_text(self.chat_id_label, "chat_id")
        self._register_widget_text(self.batch_size_label, "batch_size")
        self._register_widget_text(self.pause_label, "pause_between_batches")

        self.chat_id_entry = ttk.Entry(self.cleanup_frame, textvariable=self.chat_id_var)
        self.batch_size_entry = ttk.Entry(self.cleanup_frame, textvariable=self.batch_size_var, width=10)
        self.pause_entry = ttk.Entry(self.cleanup_frame, textvariable=self.pause_seconds_var, width=10)

        self.chat_id_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        self.batch_size_entry.grid(row=0, column=3, sticky="ew", padx=6, pady=4)
        self.pause_entry.grid(row=0, column=5, sticky="ew", padx=6, pady=4)

        self.chat_id_entry.bind("<FocusOut>", lambda _event: self._load_local_chat_state())
        self.chat_id_entry.bind("<Return>", lambda _event: self._load_local_chat_state())

        self.list_groups_button = ttk.Button(self.cleanup_frame, command=self._list_groups)
        self.index_only_button = ttk.Button(self.cleanup_frame, command=self._index_only)
        self.start_cleanup_button = ttk.Button(self.cleanup_frame, command=self._start_cleanup)
        self.delete_indexed_only_button = ttk.Button(self.cleanup_frame, command=self._delete_indexed_only)
        self.pause_after_batch_button = ttk.Button(self.cleanup_frame, command=self._pause_after_batch)
        self.stop_after_batch_button = ttk.Button(self.cleanup_frame, command=self._stop_after_batch)
        self.retry_failed_button = ttk.Button(self.cleanup_frame, command=self._retry_failed)
        self.delete_local_db_button = ttk.Button(self.cleanup_frame, command=self._delete_local_db)

        self.list_groups_button.grid(row=1, column=0, sticky="ew", padx=6, pady=8)
        self.index_only_button.grid(row=1, column=1, sticky="ew", padx=6, pady=8)
        self.start_cleanup_button.grid(row=1, column=2, sticky="ew", padx=6, pady=8)
        self.pause_after_batch_button.grid(row=1, column=3, sticky="ew", padx=6, pady=8)
        self.stop_after_batch_button.grid(row=1, column=4, sticky="ew", padx=6, pady=8)
        self.delete_indexed_only_button.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 8))
        self.retry_failed_button.grid(row=2, column=1, sticky="ew", padx=6, pady=(0, 8))
        self.delete_local_db_button.grid(row=2, column=2, columnspan=2, sticky="ew", padx=6, pady=(0, 8))

        self._register_widget_text(self.list_groups_button, "list_groups")
        self._register_widget_text(self.index_only_button, "index_only")
        self._register_widget_text(self.start_cleanup_button, "start_cleanup")
        self._register_widget_text(self.delete_indexed_only_button, "delete_indexed_only")
        self._register_widget_text(self.pause_after_batch_button, "pause_after_batch")
        self._register_widget_text(self.stop_after_batch_button, "stop_after_batch")
        self._register_widget_text(self.retry_failed_button, "retry_failed")
        self._register_widget_text(self.delete_local_db_button, "delete_local_db")

    def _build_progress_section(self) -> None:
        for column in range(4):
            self.progress_frame.columnconfigure(column, weight=1)

        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="determinate", maximum=100)
        self.progress_bar.grid(row=0, column=0, columnspan=4, sticky="ew", padx=8, pady=(8, 12))

        rows = [
            ("phase", self.phase_value_var, 1, 0),
            ("selected_chat_title", self.chat_title_value_var, 1, 2),
            ("selected_chat_id", self.chat_id_value_var, 2, 0),
            ("indexed_messages", self.indexed_value_var, 2, 2),
            ("deleted_messages", self.deleted_value_var, 3, 0),
            ("pending_messages", self.pending_value_var, 3, 2),
            ("failed_messages", self.failed_value_var, 4, 0),
            ("percentage", self.percentage_value_var, 4, 2),
            ("speed", self.speed_value_var, 5, 0),
            ("eta", self.eta_value_var, 5, 2),
            ("current_batch", self.batch_value_var, 6, 0),
            ("flood_wait", self.flood_wait_value_var, 6, 2),
        ]

        self.progress_value_labels: list[ttk.Label] = []
        for key, var, row, column in rows:
            label = ttk.Label(self.progress_frame)
            value_label = ttk.Label(self.progress_frame, textvariable=var)
            label.grid(row=row, column=column, sticky="w", padx=8, pady=3)
            value_label.grid(row=row, column=column + 1, sticky="w", padx=8, pady=3)
            self._register_widget_text(label, key)
            self.progress_value_labels.append(value_label)

    def _build_logs_section(self) -> None:
        self.log_text = tk.Text(self.logs_frame, wrap="word", height=18, state="disabled")
        scrollbar = ttk.Scrollbar(self.logs_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)

    def _build_settings_section(self) -> None:
        for column in range(6):
            self.settings_frame.columnconfigure(column, weight=1)

        self.db_path_label = ttk.Label(self.settings_frame)
        self.require_confirmation_checkbox = ttk.Checkbutton(
            self.settings_frame,
            variable=self.require_confirmation_var,
            command=self._toggle_confirmation_setting,
        )
        self.language_label = ttk.Label(self.settings_frame)
        self.theme_label = ttk.Label(self.settings_frame)

        self.db_path_label.grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.language_label.grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.theme_label.grid(row=1, column=2, sticky="w", padx=6, pady=4)
        self.require_confirmation_checkbox.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=8)

        self._register_widget_text(self.db_path_label, "database_path")
        self._register_widget_text(self.require_confirmation_checkbox, "require_confirmation")
        self._register_widget_text(self.language_label, "language")
        self._register_widget_text(self.theme_label, "theme")

        self.db_path_entry = ttk.Entry(self.settings_frame, textvariable=self.db_path_var)
        self.browse_db_button = ttk.Button(self.settings_frame, command=self._browse_db_file)
        self.language_combo = ttk.Combobox(
            self.settings_frame,
            state="readonly",
            values=["en", "ru"],
            textvariable=self.language_var,
        )
        self.theme_combo = ttk.Combobox(
            self.settings_frame,
            state="readonly",
            values=["Light", "Dark"],
            textvariable=self.theme_var,
        )

        self.db_path_entry.grid(row=0, column=1, columnspan=4, sticky="ew", padx=6, pady=4)
        self.browse_db_button.grid(row=0, column=5, sticky="ew", padx=6, pady=4)
        self.language_combo.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        self.theme_combo.grid(row=1, column=3, sticky="ew", padx=6, pady=4)

        self._register_widget_text(self.browse_db_button, "browse")

        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_changed)

    def _setup_clipboard_support(self) -> None:
        self.entry_context_menu = tk.Menu(self.root, tearoff=0)
        self.entry_context_menu.add_command(label="Cut", command=lambda: self._entry_context_action("cut"))
        self.entry_context_menu.add_command(label="Copy", command=lambda: self._entry_context_action("copy"))
        self.entry_context_menu.add_command(label="Paste", command=lambda: self._entry_context_action("paste"))
        self.entry_context_menu.add_separator()
        self.entry_context_menu.add_command(
            label="Select all",
            command=lambda: self._entry_context_action("select_all"),
        )
        self._context_menu_target: tk.Widget | None = None

        self.root.bind_class("TEntry", "<Control-v>", self._handle_entry_paste, add="+")
        self.root.bind_class("TEntry", "<Control-V>", self._handle_entry_paste, add="+")
        self.root.bind_class("TEntry", "<Shift-Insert>", self._handle_entry_paste, add="+")
        self.root.bind_class("TEntry", "<<Paste>>", self._handle_entry_paste, add="+")
        self.root.bind_class("TEntry", "<Button-3>", self._show_entry_context_menu, add="+")
        self.root.bind_class("TEntry", "<Control-a>", self._select_all_entry_text, add="+")
        self.root.bind_class("TEntry", "<Control-A>", self._select_all_entry_text, add="+")

        # On Windows, Ctrl+V with a non-English keyboard layout may not trigger <Control-v>.
        self.root.bind_all("<Control-KeyPress>", self._handle_control_keypress, add="+")

    def _handle_control_keypress(self, event: tk.Event) -> str | None:
        widget = self._get_editable_entry_widget(event.widget)
        if not widget:
            return None
        if event.keycode == 86:
            return self._paste_into_entry(widget)
        if event.keycode == 65:
            return self._select_all_entry_widget(widget)
        return None

    def _handle_entry_paste(self, event: tk.Event) -> str | None:
        widget = self._get_editable_entry_widget(event.widget)
        if not widget:
            return None
        return self._paste_into_entry(widget)

    def _show_entry_context_menu(self, event: tk.Event) -> str | None:
        widget = self._get_editable_entry_widget(event.widget)
        if not widget:
            return None
        self._context_menu_target = widget
        try:
            self.entry_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.entry_context_menu.grab_release()
        return "break"

    def _entry_context_action(self, action: str) -> None:
        widget = self._get_editable_entry_widget(self._context_menu_target)
        if not widget:
            return
        widget.focus_set()
        if action == "cut":
            widget.event_generate("<<Cut>>")
            return
        if action == "copy":
            widget.event_generate("<<Copy>>")
            return
        if action == "paste":
            self._paste_into_entry(widget)
            return
        if action == "select_all":
            self._select_all_entry_widget(widget)

    def _select_all_entry_text(self, event: tk.Event) -> str | None:
        widget = self._get_editable_entry_widget(event.widget)
        if not widget:
            return None
        return self._select_all_entry_widget(widget)

    def _select_all_entry_widget(self, widget: tk.Widget) -> str | None:
        try:
            widget.selection_range(0, "end")
            widget.icursor("end")
        except tk.TclError:
            return None
        return "break"

    def _paste_into_entry(self, widget: tk.Widget) -> str | None:
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            return "break"

        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

        try:
            insert_at = widget.index("insert")
            widget.insert(insert_at, clipboard_text)
        except tk.TclError:
            return None
        return "break"

    def _get_editable_entry_widget(self, widget: Any) -> tk.Widget | None:
        if not isinstance(widget, tk.Widget):
            return None
        if widget.winfo_class() not in {"Entry", "TEntry"}:
            return None
        try:
            if str(widget.cget("state")) == "disabled":
                return None
        except tk.TclError:
            return None
        return widget

    def _apply_saved_config(self) -> None:
        self.language_var.set(self.core.get_config().get("language", "en"))
        self.theme_var.set(self.core.get_config().get("theme", "Light"))
        self.db_path_var.set(str(self.core.get_database_path()))
        self.require_confirmation_var.set(
            bool(self.core.get_config().get("require_confirmation_before_deletion", True))
        )
        self._update_button_states()

    def _refresh_translations(self) -> None:
        self._register_widget_text(self.auth_frame, "auth_section")
        self._register_widget_text(self.cleanup_frame, "cleanup_section")
        self._register_widget_text(self.progress_frame, "progress_section")
        self._register_widget_text(self.logs_frame, "logs_section")
        self._register_widget_text(self.settings_frame, "settings_section")

        seen: set[tuple[int, str, str]] = set()
        for widget, option, key in self.localized_widgets:
            marker = (id(widget), option, key)
            if marker in seen:
                continue
            seen.add(marker)
            widget.configure(**{option: self.translator.gettext(key)})

        if self.chat_selector_window and self.chat_selector_window.winfo_exists():
            self.chat_selector_window.title(self.translator.gettext("select_chat"))
            self.chat_selector_tree.heading("title", text=self.translator.gettext("chat_title_column"))
            self.chat_selector_tree.heading("id", text=self.translator.gettext("chat_id_column"))
            self.chat_selector_tree.heading("username", text=self.translator.gettext("chat_username_column"))
            self.chat_selector_tree.heading("type", text=self.translator.gettext("chat_type_column"))
        if self.qr_login_window and self.qr_login_window.winfo_exists():
            self.qr_login_window.title(self.translator.gettext("qr_login"))

        self._set_auth_status_text(self.current_auth_status)

    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        theme = self.theme_var.get()
        if theme == "Dark":
            bg = "#1f2329"
            fg = "#f2f4f8"
            field_bg = "#2c313a"
            border = "#3a4452"
            text_bg = "#171a1f"
            button_bg = "#394150"
        else:
            bg = "#f3f5f7"
            fg = "#111111"
            field_bg = "#ffffff"
            border = "#c9d0d8"
            text_bg = "#ffffff"
            button_bg = "#e8edf2"

        self.root.configure(bg=bg)
        style.configure(".", background=bg, foreground=fg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)
        style.configure("TButton", background=button_bg, foreground=fg, borderwidth=1)
        style.map("TButton", background=[("active", button_bg), ("disabled", border)])
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.configure("TEntry", fieldbackground=field_bg, foreground=fg, insertcolor=fg)
        style.configure("TCombobox", fieldbackground=field_bg, foreground=fg)
        style.map("TCombobox", fieldbackground=[("readonly", field_bg)])
        style.configure("ChatSelector.Treeview", background=field_bg, fieldbackground=field_bg, foreground=fg)
        style.configure("ChatSelector.Treeview.Heading", background=button_bg, foreground=fg)
        style.map(
            "ChatSelector.Treeview",
            background=[("selected", "#4e8dd6")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=field_bg,
            background="#4e8dd6",
            bordercolor=border,
            lightcolor="#4e8dd6",
            darkcolor="#4e8dd6",
        )
        self.log_text.configure(
            background=text_bg,
            foreground=fg,
            insertbackground=fg,
            selectbackground="#4e8dd6",
            selectforeground="#ffffff",
        )
        if self.chat_selector_window and self.chat_selector_window.winfo_exists():
            self.chat_selector_window.configure(bg=bg)

    def _save_credentials(self) -> None:
        api_id = self.api_id_var.get().strip()
        api_hash = self.api_hash_var.get().strip()
        phone_number = self.phone_number_var.get().strip()
        if not api_id or not api_hash:
            messagebox.showwarning(
                self.translator.gettext("warning_title"),
                self.translator.gettext("fill_required_fields"),
            )
            return
        try:
            self.core.save_api_credentials(api_id, api_hash, phone_number)
            self._append_log("API credentials saved locally.")
        except Exception as exc:
            self._show_error(str(exc))

    def _send_code(self) -> None:
        self._launch_worker("send_code", self.core.send_code, self.phone_number_var.get().strip())

    def _start_qr_login(self) -> None:
        control = RunControl()
        self._open_qr_login_window()
        self._launch_worker("qr_login", self.core.start_qr_login, control=control)

    def _sign_in(self) -> None:
        self._launch_worker(
            "sign_in",
            self.core.sign_in,
            self.login_code_var.get().strip(),
            self.phone_number_var.get().strip(),
        )

    def _submit_password(self) -> None:
        self._launch_worker("submit_password", self.core.submit_password, self.password_var.get())

    def _logout(self) -> None:
        self._launch_worker("logout", self.core.logout)

    def _list_groups(self) -> None:
        self._launch_worker("list_groups", self.core.list_groups)

    def _refresh_chat_list(self) -> None:
        self._list_groups()

    def _index_only(self) -> None:
        chat_id = self._require_chat_id()
        if not chat_id:
            return
        control = RunControl()
        self._launch_worker("index", self.core.index_messages, chat_id, control=control)

    def _start_cleanup(self) -> None:
        chat_id = self._require_chat_id()
        if not chat_id:
            return
        batch_size, pause_seconds = self._get_batch_settings()
        if batch_size is None or pause_seconds is None:
            return

        if self.require_confirmation_var.get():
            self.pending_cleanup_request = {
                "mode": "cleanup",
                "chat_id": chat_id,
                "batch_size": batch_size,
                "pause_seconds": pause_seconds,
            }
            self._launch_worker("prepare_cleanup", self.core.get_chat_overview, chat_id)
            return

        self._launch_cleanup_worker(chat_id, batch_size, pause_seconds)

    def _delete_indexed_only(self) -> None:
        chat_id = self._require_chat_id()
        if not chat_id:
            return
        batch_size, pause_seconds = self._get_batch_settings()
        if batch_size is None or pause_seconds is None:
            return

        if self.require_confirmation_var.get():
            self.pending_cleanup_request = {
                "mode": "delete_indexed_only",
                "chat_id": chat_id,
                "batch_size": batch_size,
                "pause_seconds": pause_seconds,
            }
            self._launch_worker("prepare_cleanup", self.core.get_chat_overview, chat_id)
            return

        self._launch_delete_indexed_only_worker(chat_id, batch_size, pause_seconds)

    def _launch_cleanup_worker(self, chat_id: str, batch_size: int, pause_seconds: float) -> None:
        control = RunControl()
        self._launch_worker(
            "cleanup",
            self.core.start_cleanup,
            chat_id,
            batch_size,
            pause_seconds,
            control=control,
        )

    def _launch_delete_indexed_only_worker(self, chat_id: str, batch_size: int, pause_seconds: float) -> None:
        control = RunControl()
        self._launch_worker(
            "delete_indexed_only",
            self.core.delete_indexed_only,
            chat_id,
            batch_size,
            pause_seconds,
            control=control,
        )

    def _pause_after_batch(self) -> None:
        if not self.current_control:
            return
        self.core.request_pause(self.current_control)

    def _stop_after_batch(self) -> None:
        if not self.current_control:
            return
        self.core.request_stop(self.current_control)

    def _retry_failed(self) -> None:
        chat_id = self._require_chat_id()
        if not chat_id:
            return
        batch_size, pause_seconds = self._get_batch_settings()
        if batch_size is None or pause_seconds is None:
            return
        control = RunControl()
        self._launch_worker(
            "retry_failed",
            self.core.retry_failed,
            chat_id,
            batch_size,
            pause_seconds,
            control=control,
        )

    def _delete_local_db(self) -> None:
        if self.active_worker and self.active_worker.is_alive():
            messagebox.showwarning(
                self.translator.gettext("warning_title"),
                self.translator.gettext("db_delete_blocked"),
            )
            return
        confirmed = messagebox.askyesno(
            self.translator.gettext("confirm_delete_db_title"),
            self.translator.gettext("confirm_delete_db_message"),
        )
        if not confirmed:
            return
        try:
            self.core.delete_local_progress_database()
            self.db_path_var.set(str(self.core.get_database_path()))
            self._reset_progress_panel()
            self._append_log("Local progress database deleted.")
            messagebox.showinfo(
                self.translator.gettext("info_title"),
                self.translator.gettext("db_deleted"),
            )
        except Exception as exc:
            self._show_error(str(exc))

    def _toggle_confirmation_setting(self) -> None:
        try:
            self.core.set_require_confirmation(self.require_confirmation_var.get())
        except Exception as exc:
            self._show_error(str(exc))

    def _browse_db_file(self) -> None:
        selected = filedialog.asksaveasfilename(
            title=self.translator.gettext("database_path"),
            initialdir=str(self.core.get_database_path().parent),
            initialfile=self.core.get_database_path().name,
            defaultextension=".sqlite3",
            filetypes=[("SQLite database", "*.sqlite3"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            path = self.core.set_db_file(selected, persist=True)
            self.db_path_var.set(str(path))
            self._append_log(f"Database path changed to {path}")
        except Exception as exc:
            self._show_error(str(exc))

    def _on_language_changed(self, _event: Any) -> None:
        language = self.language_var.get()
        try:
            self.core.set_language(language)
            self.translator.set_language(language)
            self._refresh_translations()
        except Exception as exc:
            self._show_error(str(exc))

    def _on_theme_changed(self, _event: Any) -> None:
        theme = self.theme_var.get()
        try:
            self.core.set_theme(theme)
            self._apply_theme()
        except Exception as exc:
            self._show_error(str(exc))

    def _launch_worker(self, action: str, func: Callable[..., Any], *args: Any, control: RunControl | None = None) -> None:
        if self.active_worker and self.active_worker.is_alive():
            messagebox.showwarning(
                self.translator.gettext("warning_title"),
                self.translator.gettext("worker_busy"),
            )
            return

        self.current_control = control
        self.active_action = action
        self._update_button_states()

        def worker() -> None:
            result: Any = None
            error: str | None = None
            try:
                result = func(*args)
            except Exception as exc:
                error = str(exc)
            finally:
                self.event_queue.put({"type": "worker_done", "action": action})
                if error is not None:
                    self.event_queue.put({"type": "worker_error", "action": action, "error": error})
                else:
                    self.event_queue.put({"type": "worker_result", "action": action, "result": result})

        self.active_worker = threading.Thread(target=worker, daemon=True)
        self.active_worker.start()

    def _process_event_queue(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self.root.after(100, self._process_event_queue)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "log":
            self._handle_log_event(event)
            return
        if event_type == "progress":
            self._render_progress(event.get("snapshot", {}))
            return
        if event_type == "qr_login_ready":
            self._render_qr_login(event)
            return
        if event_type == "qr_login_expired":
            self.qr_status_var.set(self.translator.gettext("qr_code_expired"))
            return
        if event_type == "worker_result":
            self._handle_worker_result(event.get("action"), event.get("result"))
            return
        if event_type == "worker_error":
            self._append_log(f"{event.get('action')}: {event.get('error')}")
            if event.get("action") in {"send_code", "sign_in", "submit_password", "refresh_auth_status", "qr_login"}:
                self._set_auth_status_text("auth error")
            if event.get("action") == "qr_login":
                self._close_qr_login_window()
            self._show_error(str(event.get("error")))
            return
        if event_type == "worker_done":
            self.active_action = None
            self.current_control = None
            self._update_button_states()
            return
        if event_type == "chat_overview":
            overview = event.get("overview", {})
            counts = overview.get("counts", {})
            self._render_progress(
                {
                    "phase": counts.get("status") or "ready",
                    "title": overview.get("title") or self.translator.gettext("none"),
                    "chat_id": overview.get("chat_id") or self.translator.gettext("none"),
                    "indexed": counts.get("indexed", 0),
                    "deleted": counts.get("deleted", 0),
                    "pending": counts.get("pending", 0),
                    "failed": counts.get("failed", 0),
                    "percentage": 0,
                    "speed_text": self.translator.gettext("calculating"),
                    "eta_text": self.translator.gettext("calculating"),
                    "batch_number": 0,
                    "flood_wait_seconds": None,
                }
            )

    def _handle_log_event(self, event: dict[str, Any]) -> None:
        message = event.get("message", "")
        details = []
        for key in ("chat_id", "title", "phase", "batch_number", "wait_seconds", "indexed", "error"):
            value = event.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")
        suffix = f" | {' | '.join(details)}" if details else ""
        self._append_log(f"{message}{suffix}")

    def _handle_worker_result(self, action: str | None, result: Any) -> None:
        if action in {"refresh_auth_status", "send_code", "sign_in", "submit_password", "logout", "qr_login"}:
            status = result.get("status", "auth error")
            self._set_auth_status_text(status)
            account = result.get("account")
            self.authorized_as_var.set(self._format_account_label(account))
            info_message = result.get("info_message")
            if info_message:
                self._append_log(info_message)
            if action == "logout":
                self.login_code_var.set("")
                self.password_var.set("")
                self._close_qr_login_window()
            if action == "qr_login":
                self._close_qr_login_window()
            return

        if action == "prepare_cleanup":
            self._handle_prepare_cleanup_result(result)
            return

        if action == "list_groups":
            self.chat_selector_dialogs = list(result or [])
            self.chat_selector_filtered_dialogs = list(self.chat_selector_dialogs)
            self._append_log(f"Loaded {len(self.chat_selector_dialogs)} dialogs for chat selection.")
            self._open_chat_selector()
            return

        if action in {"index", "cleanup", "delete_indexed_only", "retry_failed"}:
            chat_id = result.get("chat_id")
            title = result.get("title")
            counts = result.get("counts", {})
            status = result.get("status")
            self._render_progress(
                {
                    "phase": status,
                    "title": title,
                    "chat_id": chat_id,
                    "indexed": counts.get("indexed", 0),
                    "deleted": counts.get("deleted", 0),
                    "pending": counts.get("pending", 0),
                    "failed": counts.get("failed", 0),
                    "percentage": counts.get("percentage", 100 if status == "completed" else 0),
                    "speed_text": counts.get("speed_text", self.translator.gettext("calculating")),
                    "eta_text": counts.get("eta_text", self.translator.gettext("calculating")),
                    "batch_number": counts.get("batch_number", 0),
                    "flood_wait_seconds": None,
                }
            )
            return

    def _handle_prepare_cleanup_result(self, result: dict[str, Any]) -> None:
        request = self.pending_cleanup_request
        self.pending_cleanup_request = None
        if not request:
            return

        known_count = result.get("counts", {}).get("indexed", 0)
        confirmed = messagebox.askyesno(
            self.translator.gettext("confirm_cleanup_title"),
            self.translator.gettext(
                "confirm_cleanup_message",
                title=result.get("title") or self.translator.gettext("none"),
                chat_id=result.get("chat_id") or request["chat_id"],
                indexed=known_count,
            ),
        )
        if not confirmed:
            self._append_log("Cleanup cancelled by user before deletion.")
            return

        if request.get("mode") == "delete_indexed_only":
            self._launch_delete_indexed_only_worker(
                request["chat_id"],
                request["batch_size"],
                request["pause_seconds"],
            )
        else:
            self._launch_cleanup_worker(
                request["chat_id"],
                request["batch_size"],
                request["pause_seconds"],
            )

    def _open_chat_selector(self) -> None:
        if self.chat_selector_window and self.chat_selector_window.winfo_exists():
            self.chat_selector_window.deiconify()
            self.chat_selector_window.lift()
            self._populate_chat_selector_tree()
            return

        window = tk.Toplevel(self.root)
        self.chat_selector_window = window
        window.title(self.translator.gettext("select_chat"))
        window.geometry("900x520")
        window.minsize(760, 420)
        window.transient(self.root)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        window.protocol("WM_DELETE_WINDOW", self._close_chat_selector)

        top_frame = ttk.Frame(window)
        top_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top_frame.columnconfigure(1, weight=1)

        self.chat_selector_search_label = ttk.Label(top_frame)
        self.chat_selector_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_widget_text(self.chat_selector_search_label, "search_chats")

        self.chat_selector_search_entry = ttk.Entry(top_frame, textvariable=self.chat_selector_search_var)
        self.chat_selector_search_entry.grid(row=0, column=1, sticky="ew")
        self.chat_selector_search_entry.bind("<KeyRelease>", lambda _event: self._filter_chat_selector())

        self.chat_selector_refresh_button = ttk.Button(top_frame, command=self._refresh_chat_list)
        self.chat_selector_refresh_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._register_widget_text(self.chat_selector_refresh_button, "refresh_chat_list")

        tree_frame = ttk.Frame(window)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.chat_selector_tree = ttk.Treeview(
            tree_frame,
            columns=("title", "id", "username", "type"),
            show="headings",
            style="ChatSelector.Treeview",
        )
        self.chat_selector_tree.heading("title", text=self.translator.gettext("chat_title_column"))
        self.chat_selector_tree.heading("id", text=self.translator.gettext("chat_id_column"))
        self.chat_selector_tree.heading("username", text=self.translator.gettext("chat_username_column"))
        self.chat_selector_tree.heading("type", text=self.translator.gettext("chat_type_column"))
        self.chat_selector_tree.column("title", width=330, anchor="w")
        self.chat_selector_tree.column("id", width=170, anchor="w")
        self.chat_selector_tree.column("username", width=170, anchor="w")
        self.chat_selector_tree.column("type", width=120, anchor="w")
        self.chat_selector_tree.grid(row=0, column=0, sticky="nsew")
        self.chat_selector_tree.bind("<Double-1>", lambda _event: self._use_selected_chat())

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.chat_selector_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat_selector_tree.configure(yscrollcommand=scrollbar.set)

        bottom_frame = ttk.Frame(window)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
        bottom_frame.columnconfigure(0, weight=1)

        self.chat_selector_use_button = ttk.Button(bottom_frame, command=self._use_selected_chat)
        self.chat_selector_use_button.grid(row=0, column=1, sticky="e")
        self._register_widget_text(self.chat_selector_use_button, "use_selected_chat")

        self._apply_theme()
        self._refresh_translations()
        self._populate_chat_selector_tree()
        self.chat_selector_search_entry.focus_set()

    def _close_chat_selector(self) -> None:
        if self.chat_selector_window and self.chat_selector_window.winfo_exists():
            self.chat_selector_window.destroy()
        self.chat_selector_window = None

    def _filter_chat_selector(self) -> None:
        query = self.chat_selector_search_var.get().strip().lower()
        if not query:
            self.chat_selector_filtered_dialogs = list(self.chat_selector_dialogs)
        else:
            self.chat_selector_filtered_dialogs = [
                dialog
                for dialog in self.chat_selector_dialogs
                if query in str(dialog.get("title", "")).lower()
                or query in str(dialog.get("id", "")).lower()
                or query in str(dialog.get("username", "")).lower()
                or query in str(dialog.get("type", "")).lower()
            ]
        self._populate_chat_selector_tree()

    def _populate_chat_selector_tree(self) -> None:
        if not self.chat_selector_window or not self.chat_selector_window.winfo_exists():
            return
        for item_id in self.chat_selector_tree.get_children():
            self.chat_selector_tree.delete(item_id)

        for index, dialog in enumerate(self.chat_selector_filtered_dialogs):
            self.chat_selector_tree.insert(
                "",
                "end",
                iid=f"dialog-{index}",
                values=(
                    str(dialog.get("title") or ""),
                    str(dialog.get("id") or ""),
                    str(dialog.get("username") or ""),
                    str(dialog.get("type") or ""),
                ),
            )

        children = self.chat_selector_tree.get_children()
        if children:
            self.chat_selector_tree.selection_set(children[0])
            self.chat_selector_tree.focus(children[0])

    def _use_selected_chat(self) -> None:
        if not self.chat_selector_window or not self.chat_selector_window.winfo_exists():
            return

        selection = self.chat_selector_tree.selection()
        if not selection:
            messagebox.showwarning(
                self.translator.gettext("warning_title"),
                self.translator.gettext("no_chat_selected"),
            )
            return

        values = self.chat_selector_tree.item(selection[0], "values")
        title = str(values[0])
        chat_id = str(values[1])
        self.chat_id_var.set(chat_id)
        self._load_local_chat_state()
        self._append_log(self.translator.gettext("chat_selected_message", title=title, chat_id=chat_id))
        self._close_chat_selector()

    def _open_qr_login_window(self) -> None:
        if self.qr_login_window and self.qr_login_window.winfo_exists():
            self.qr_login_window.deiconify()
            self.qr_login_window.lift()
            return

        window = tk.Toplevel(self.root)
        self.qr_login_window = window
        window.title(self.translator.gettext("qr_login"))
        window.geometry("470x650")
        window.minsize(420, 560)
        window.transient(self.root)
        window.columnconfigure(0, weight=1)
        window.protocol("WM_DELETE_WINDOW", self._cancel_qr_login)

        top_frame = ttk.Frame(window)
        top_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top_frame.columnconfigure(0, weight=1)

        self.qr_help_label = ttk.Label(top_frame, wraplength=420, justify="left")
        self.qr_help_label.grid(row=0, column=0, sticky="w")
        self._register_widget_text(self.qr_help_label, "qr_login_help")

        self.qr_status_label = ttk.Label(top_frame, textvariable=self.qr_status_var, wraplength=420, justify="left")
        self.qr_status_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.qr_image_label = ttk.Label(window)
        self.qr_image_label.grid(row=1, column=0, padx=12, pady=8)

        details_frame = ttk.Frame(window)
        details_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        details_frame.columnconfigure(1, weight=1)

        self.qr_expires_label = ttk.Label(details_frame)
        self.qr_expires_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._register_widget_text(self.qr_expires_label, "qr_expires_in")
        self.qr_expires_value_label = ttk.Label(details_frame, textvariable=self.qr_expires_var)
        self.qr_expires_value_label.grid(row=0, column=1, sticky="w")

        self.qr_url_label = ttk.Label(details_frame)
        self.qr_url_label.grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(8, 0))
        self._register_widget_text(self.qr_url_label, "qr_login_link")
        self.qr_url_entry = ttk.Entry(details_frame, textvariable=self.qr_url_var)
        self.qr_url_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        button_frame = ttk.Frame(window)
        button_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 12))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        self.qr_copy_link_button = ttk.Button(button_frame, command=self._copy_qr_login_link)
        self.qr_copy_link_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._register_widget_text(self.qr_copy_link_button, "copy_qr_link")

        self.qr_cancel_button = ttk.Button(button_frame, command=self._cancel_qr_login)
        self.qr_cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._register_widget_text(self.qr_cancel_button, "cancel_qr_login")

        self.qr_status_var.set(self.translator.gettext("qr_waiting"))
        self.qr_expires_var.set(self.translator.gettext("calculating"))
        self._apply_theme()
        self._refresh_translations()

    def _render_qr_login(self, event: dict[str, Any]) -> None:
        self._open_qr_login_window()
        url = str(event.get("url") or "")
        expires_at_raw = str(event.get("expires_at") or "")
        self.qr_url_var.set(url)
        self.qr_status_var.set(self.translator.gettext("qr_waiting"))
        self.qr_photoimage = create_qr_photoimage(url, scale=6)
        self.qr_image_label.configure(image=self.qr_photoimage)
        self.qr_image_label.image = self.qr_photoimage

        self.qr_expires_at = None
        if expires_at_raw:
            try:
                self.qr_expires_at = datetime.fromisoformat(expires_at_raw)
            except ValueError:
                self.qr_expires_at = None
        self._schedule_qr_countdown()

    def _schedule_qr_countdown(self) -> None:
        if self.qr_countdown_job:
            self.root.after_cancel(self.qr_countdown_job)
            self.qr_countdown_job = None
        self._update_qr_countdown()

    def _update_qr_countdown(self) -> None:
        if not self.qr_login_window or not self.qr_login_window.winfo_exists():
            self.qr_countdown_job = None
            return
        if not self.qr_expires_at:
            self.qr_expires_var.set(self.translator.gettext("calculating"))
            self.qr_countdown_job = self.root.after(1000, self._update_qr_countdown)
            return

        remaining = int((self.qr_expires_at - datetime.now(self.qr_expires_at.tzinfo)).total_seconds())
        if remaining <= 0:
            self.qr_expires_var.set(self.translator.gettext("qr_code_expired"))
        else:
            self.qr_expires_var.set(f"{remaining} sec")
        self.qr_countdown_job = self.root.after(1000, self._update_qr_countdown)

    def _copy_qr_login_link(self) -> None:
        url = self.qr_url_var.get().strip()
        if not url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self._append_log(self.translator.gettext("qr_link_copied"))

    def _cancel_qr_login(self) -> None:
        if self.active_action == "qr_login" and self.current_control:
            self.core.request_stop(self.current_control)
        self._close_qr_login_window()

    def _close_qr_login_window(self) -> None:
        if self.qr_countdown_job:
            self.root.after_cancel(self.qr_countdown_job)
            self.qr_countdown_job = None
        if self.qr_login_window and self.qr_login_window.winfo_exists():
            self.qr_login_window.destroy()
        self.qr_login_window = None
        self.qr_photoimage = None
        self.qr_expires_at = None

    def _render_progress(self, snapshot: dict[str, Any]) -> None:
        phase = snapshot.get("phase") or self.translator.gettext("progress_idle")
        title = snapshot.get("title") or self.translator.gettext("none")
        chat_id = snapshot.get("chat_id") or self.translator.gettext("none")
        indexed = snapshot.get("indexed", 0)
        deleted = snapshot.get("deleted", 0)
        pending = snapshot.get("pending", 0)
        failed = snapshot.get("failed", 0)
        percentage = snapshot.get("percentage", 0)
        batch_number = snapshot.get("batch_number", 0)
        flood_wait_seconds = snapshot.get("flood_wait_seconds")

        self.phase_value_var.set(str(phase))
        self.chat_title_value_var.set(str(title))
        self.chat_id_value_var.set(str(chat_id))
        self.indexed_value_var.set(str(indexed))
        self.deleted_value_var.set(str(deleted))
        self.pending_value_var.set(str(pending))
        self.failed_value_var.set(str(failed))
        self.percentage_value_var.set(f"{percentage}%")
        self.speed_value_var.set(str(snapshot.get("speed_text", self.translator.gettext("calculating"))))
        self.eta_value_var.set(str(snapshot.get("eta_text", self.translator.gettext("calculating"))))
        self.batch_value_var.set(str(batch_number))
        self.flood_wait_value_var.set(
            str(flood_wait_seconds) if flood_wait_seconds not in (None, "") else self.translator.gettext("none")
        )

        if str(phase).startswith("indexing"):
            self._set_progressbar_mode("indeterminate")
        else:
            self._set_progressbar_mode("determinate")
            try:
                self.progress_bar["value"] = max(0.0, min(100.0, float(percentage)))
            except (TypeError, ValueError):
                self.progress_bar["value"] = 0

    def _set_progressbar_mode(self, mode: str) -> None:
        current_mode = str(self.progress_bar.cget("mode"))
        if current_mode == mode:
            if mode == "indeterminate":
                self.progress_bar.start(10)
            return
        self.progress_bar.stop()
        self.progress_bar.configure(mode=mode)
        if mode == "indeterminate":
            self.progress_bar.start(10)

    def _load_local_chat_state(self) -> None:
        chat_id = self.chat_id_var.get().strip()
        if not chat_id:
            return
        try:
            counts = self.core.storage.get_status_counts(chat_id)
            if counts.get("indexed", 0) or counts.get("title"):
                recent_run = self.core.storage.get_recent_run(chat_id)
                self._render_progress(
                    {
                        "phase": counts.get("status") or (recent_run or {}).get("status") or "stored-state",
                        "title": counts.get("title") or self.translator.gettext("none"),
                        "chat_id": chat_id,
                        "indexed": counts.get("indexed", 0),
                        "deleted": counts.get("deleted", 0),
                        "pending": counts.get("pending", 0),
                        "failed": counts.get("failed", 0),
                        "percentage": round(
                            ((counts.get("deleted", 0) + counts.get("failed", 0)) / max(counts.get("indexed", 1), 1)) * 100,
                            2,
                        )
                        if counts.get("indexed", 0)
                        else 0,
                        "speed_text": self.translator.gettext("calculating"),
                        "eta_text": self.translator.gettext("calculating"),
                        "batch_number": 0,
                        "flood_wait_seconds": None,
                    }
                )
        except Exception as exc:
            self._append_log(f"Unable to read local state for {chat_id}: {exc}")

    def _set_auth_status_text(self, status: str) -> None:
        self.current_auth_status = status
        status_map = {
            "not configured": "status_not_configured",
            "unauthorized": "status_unauthorized",
            "code sent": "status_code_sent",
            "2FA required": "status_2fa_required",
            "authorized": "status_authorized",
            "auth error": "status_auth_error",
        }
        key = status_map.get(status, status)
        self.auth_status_var.set(self.translator.gettext(key))

    def _format_account_label(self, account: dict[str, Any] | None) -> str:
        if not account:
            return self.translator.gettext("none")
        parts = []
        if account.get("display"):
            parts.append(str(account["display"]))
        full_name = " ".join(
            part for part in [account.get("first_name"), account.get("last_name")] if part
        ).strip()
        if full_name:
            parts.append(full_name)
        if account.get("phone"):
            parts.append(f"+{account['phone']}")
        return " | ".join(parts) if parts else self.translator.gettext("none")

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _show_error(self, message: str) -> None:
        messagebox.showerror(self.translator.gettext("error_title"), message)

    def _require_chat_id(self) -> str | None:
        chat_id = self.chat_id_var.get().strip()
        if chat_id:
            return chat_id
        messagebox.showwarning(
            self.translator.gettext("warning_title"),
            self.translator.gettext("fill_required_fields"),
        )
        return None

    def _get_batch_settings(self) -> tuple[int | None, float | None]:
        try:
            batch_size = int(self.batch_size_var.get().strip())
            pause_seconds = float(self.pause_seconds_var.get().strip())
        except ValueError:
            self._show_error("Batch size must be an integer and pause must be a number.")
            return None, None
        if batch_size <= 0:
            self._show_error("Batch size must be greater than zero.")
            return None, None
        if pause_seconds < 0:
            self._show_error("Pause must be zero or greater.")
            return None, None
        return batch_size, pause_seconds

    def _update_button_states(self) -> None:
        is_busy = bool(self.active_worker and self.active_worker.is_alive())
        control_available = self.current_control is not None and self.active_action in {
            "index",
            "cleanup",
            "delete_indexed_only",
            "retry_failed",
        }

        normal_buttons = [
            self.save_credentials_button,
            self.send_code_button,
            self.qr_login_button,
            self.sign_in_button,
            self.submit_password_button,
            self.logout_button,
            self.list_groups_button,
            self.index_only_button,
            self.start_cleanup_button,
            self.delete_indexed_only_button,
            self.retry_failed_button,
            self.delete_local_db_button,
            self.browse_db_button,
        ]
        for button in normal_buttons:
            button.configure(state="disabled" if is_busy else "normal")

        self.pause_after_batch_button.configure(state="normal" if control_available else "disabled")
        self.stop_after_batch_button.configure(state="normal" if control_available else "disabled")

    def _reset_progress_panel(self) -> None:
        self.phase_value_var.set(self.translator.gettext("progress_idle"))
        self.chat_title_value_var.set(self.translator.gettext("none"))
        self.chat_id_value_var.set(self.translator.gettext("none"))
        self.indexed_value_var.set("0")
        self.deleted_value_var.set("0")
        self.pending_value_var.set("0")
        self.failed_value_var.set("0")
        self.percentage_value_var.set("0%")
        self.speed_value_var.set(self.translator.gettext("calculating"))
        self.eta_value_var.set(self.translator.gettext("calculating"))
        self.batch_value_var.set("0")
        self.flood_wait_value_var.set(self.translator.gettext("none"))
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", value=0)

    def _on_close(self) -> None:
        if self.active_worker and self.active_worker.is_alive() and self.current_control:
            self.core.request_stop(self.current_control)
            messagebox.showinfo(
                self.translator.gettext("info_title"),
                "Stop requested. Wait for the current batch to finish, then close the window again.",
            )
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = TelegramCleanupGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
