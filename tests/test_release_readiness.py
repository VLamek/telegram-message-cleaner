from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from telegram_cleanup_cli import build_parser  # noqa: E402
from telegram_cleanup_core import (  # noqa: E402
    ConfigStore,
    SUPPORTED_LANGUAGES,
    TelegramCleanupCore,
    get_runtime_data_dir,
    parse_message_date_range,
)
from telegram_cleanup_i18n import TRANSLATIONS  # noqa: E402


class ReleaseReadinessTests(unittest.TestCase):
    def test_translation_keys_match_english(self) -> None:
        english_keys = set(TRANSLATIONS["en"])
        for language, bundle in TRANSLATIONS.items():
            self.assertEqual(english_keys, set(bundle), language)

    def test_release_languages_are_supported(self) -> None:
        self.assertEqual(("en", "ru", "es", "zh-CN", "fr"), SUPPORTED_LANGUAGES)

    def test_default_theme_is_dark(self) -> None:
        store = ConfigStore(ROOT, ROOT)
        self.assertEqual("Dark", store.default_config()["theme"])

    def test_qr_login_removed_from_runtime_files(self) -> None:
        runtime_files = [
            ROOT / "telegram_cleanup_gui.py",
            ROOT / "telegram_cleanup_core.py",
            ROOT / "telegram_cleanup_i18n.py",
            ROOT / "requirements.txt",
        ]
        for path in runtime_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("qr_login", text.lower(), str(path))
            self.assertNotIn("qrcode", text.lower(), str(path))

    def test_date_range_validation_accepts_full_history_and_ranges(self) -> None:
        full = parse_message_date_range("first", "last")
        self.assertIsNone(full.start)
        self.assertIsNone(full.end)

        bounded = parse_message_date_range("2026-01-01 00:00", "2026-01-31 23:59")
        self.assertIsNotNone(bounded.start)
        self.assertIsNotNone(bounded.end)

    def test_all_gui_toplevel_modals_apply_shared_theme(self) -> None:
        gui_source = (ROOT / "telegram_cleanup_gui.py").read_text(encoding="utf-8")
        self.assertEqual(
            gui_source.count("tk.Toplevel(self.root)"),
            gui_source.count("self._prepare_modal_window(window)"),
        )

    def test_macos_frozen_runtime_files_use_application_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir)
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "platform", "darwin"),
                patch("telegram_cleanup_core.Path.home", return_value=home),
            ):
                data_dir = get_runtime_data_dir()
                self.assertEqual(home / "Library" / "Application Support" / "TelegramMessageCleaner", data_dir)
                self.assertTrue(data_dir.exists())

    def test_macos_frozen_session_uses_application_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            home = Path(tmp_dir) / "home"
            app_dir = Path(tmp_dir) / "TelegramMessageCleaner.app" / "Contents" / "MacOS"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "platform", "darwin"),
                patch("telegram_cleanup_core.Path.home", return_value=home),
            ):
                core = TelegramCleanupCore(app_dir=app_dir)
                expected_dir = (home / "Library" / "Application Support" / "TelegramMessageCleaner").resolve()
                self.assertEqual(expected_dir / "telegram_message_cleaner.session", core.get_session_file_path())
                self.assertEqual(expected_dir / "telegram_message_cleaner", core.get_session_base_path())

    def test_database_path_rejects_relative_traversal_and_non_sqlite_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            with patch("telegram_cleanup_core.get_runtime_data_dir", return_value=data_dir):
                core = TelegramCleanupCore(app_dir=Path(tmp_dir))
                with self.assertRaises(ValueError):
                    core.set_db_file("../outside.sqlite3")
                with self.assertRaises(ValueError):
                    core.set_db_file("telegram_message_cleaner_config.json")

                db_path = core.set_db_file("custom.sqlite3", persist=False)
                self.assertEqual((data_dir / "custom.sqlite3").resolve(), db_path)

    def test_destructive_cli_commands_have_explicit_yes_flag(self) -> None:
        parser = build_parser()
        for command in ("delete", "delete-indexed", "retry-failed"):
            args = parser.parse_args([command, "--chat-id", "-100123", "--yes"])
            self.assertTrue(args.yes, command)


if __name__ == "__main__":
    unittest.main()
