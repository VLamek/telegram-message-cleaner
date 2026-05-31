from __future__ import annotations


TRANSLATIONS = {
    "en": {
        "auth_section": "Auth",
        "cleanup_section": "Chat cleanup",
        "progress_section": "Progress",
        "logs_section": "Logs",
        "settings_section": "Settings / Advanced",
        "api_id": "API ID",
        "api_hash": "API Hash",
        "phone_number": "Phone number",
        "login_code": "Login code",
        "two_fa_password": "2FA password",
        "save_api_credentials": "Save API credentials",
        "send_code": "Send code",
        "sign_in": "Sign in",
        "submit_2fa_password": "Submit 2FA password",
        "logout": "Logout",
        "auth_status": "Auth status",
        "authorized_as": "Authorized as",
        "chat_id": "Chat ID",
        "batch_size": "Batch size",
        "pause_between_batches": "Pause between batches (sec)",
        "list_groups": "List groups",
        "select_chat": "Select chat",
        "search_chats": "Search chats",
        "chat_title_column": "Title",
        "chat_id_column": "Chat ID",
        "chat_username_column": "Username",
        "chat_type_column": "Type",
        "use_selected_chat": "Use selected chat",
        "refresh_chat_list": "Refresh chat list",
        "no_chat_selected": "Please select a chat from the list.",
        "chat_selected_message": "Selected chat {title} ({chat_id})",
        "index_only": "Index only",
        "start_cleanup": "Start cleanup",
        "delete_indexed_only": "Delete indexed only",
        "pause_after_batch": "Pause after current batch",
        "stop_after_batch": "Stop after current batch",
        "retry_failed": "Retry failed",
        "delete_local_db": "Delete local progress database",
        "database_path": "Database path",
        "browse": "Browse",
        "require_confirmation": "Require confirmation before deletion",
        "language": "Language",
        "theme": "Theme",
        "phase": "Phase",
        "selected_chat_title": "Selected chat title",
        "selected_chat_id": "Selected chat ID",
        "indexed_messages": "Indexed messages",
        "deleted_messages": "Deleted messages",
        "pending_messages": "Pending messages",
        "failed_messages": "Failed messages",
        "percentage": "Percentage",
        "speed": "Speed",
        "eta": "ETA",
        "current_batch": "Current batch",
        "flood_wait": "FloodWait",
        "status_not_configured": "not configured",
        "status_unauthorized": "unauthorized",
        "status_code_sent": "code sent",
        "status_2fa_required": "2FA required",
        "status_authorized": "authorized",
        "status_auth_error": "auth error",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "language_en": "English",
        "language_ru": "Russian",
        "progress_idle": "idle",
        "calculating": "calculating...",
        "none": "-",
        "confirm_cleanup_title": "Confirm deletion",
        "confirm_cleanup_message": (
            "Chat: {title}\n"
            "Chat ID: {chat_id}\n"
            "Known messages: {indexed}\n\n"
            "Deletion is irreversible. Continue?"
        ),
        "confirm_delete_db_title": "Delete local database",
        "confirm_delete_db_message": (
            "This deletes only local progress metadata.\n"
            "It does not restore already deleted Telegram messages.\n\n"
            "Delete the local database now?"
        ),
        "info_title": "Information",
        "error_title": "Error",
        "warning_title": "Warning",
        "db_deleted": "Local progress database deleted.",
        "db_delete_blocked": "Stop the active worker before deleting the database.",
        "fill_required_fields": "Please fill in the required fields.",
        "worker_busy": "Another action is already running.",
        "cleanup_finished": "Cleanup finished.",
        "retry_finished": "Retry failed finished.",
        "index_finished": "Indexing finished.",
        "delete_indexed_only_finished": "Deletion of already indexed messages finished.",
    },
    "ru": {
        "auth_section": "Авторизация",
        "cleanup_section": "Очистка чата",
        "progress_section": "Прогресс",
        "logs_section": "Логи",
        "settings_section": "Настройки / Дополнительно",
        "api_id": "API ID",
        "api_hash": "API Hash",
        "phone_number": "Номер телефона",
        "login_code": "Код входа",
        "two_fa_password": "Пароль 2FA",
        "save_api_credentials": "Сохранить API credentials",
        "send_code": "Отправить код",
        "sign_in": "Войти",
        "submit_2fa_password": "Отправить пароль 2FA",
        "logout": "Выйти",
        "auth_status": "Статус авторизации",
        "authorized_as": "Аккаунт",
        "chat_id": "Chat ID",
        "batch_size": "Размер батча",
        "pause_between_batches": "Пауза между батчами (сек)",
        "list_groups": "Список групп",
        "index_only": "Только индексировать",
        "start_cleanup": "Начать очистку",
        "delete_indexed_only": "Удалить уже проиндексированное",
        "pause_after_batch": "Пауза после текущего батча",
        "stop_after_batch": "Остановка после текущего батча",
        "retry_failed": "Повторить failed",
        "delete_local_db": "Удалить локальную базу прогресса",
        "database_path": "Путь к базе данных",
        "browse": "Выбрать",
        "require_confirmation": "Требовать подтверждение перед удалением",
        "language": "Язык",
        "theme": "Тема",
        "phase": "Фаза",
        "selected_chat_title": "Название чата",
        "selected_chat_id": "Chat ID",
        "indexed_messages": "Проиндексировано",
        "deleted_messages": "Удалено",
        "pending_messages": "Осталось",
        "failed_messages": "Failed",
        "percentage": "Процент",
        "speed": "Скорость",
        "eta": "ETA",
        "current_batch": "Текущий батч",
        "flood_wait": "FloodWait",
        "status_not_configured": "не настроено",
        "status_unauthorized": "не авторизован",
        "status_code_sent": "код отправлен",
        "status_2fa_required": "нужен 2FA",
        "status_authorized": "авторизован",
        "status_auth_error": "ошибка авторизации",
        "theme_light": "Светлая",
        "theme_dark": "Тёмная",
        "language_en": "English",
        "language_ru": "Русский",
        "progress_idle": "ожидание",
        "calculating": "расчёт...",
        "none": "-",
        "confirm_cleanup_title": "Подтверждение удаления",
        "confirm_cleanup_message": (
            "Чат: {title}\n"
            "Chat ID: {chat_id}\n"
            "Известно сообщений: {indexed}\n\n"
            "Удаление необратимо. Продолжить?"
        ),
        "confirm_delete_db_title": "Удалить локальную базу",
        "confirm_delete_db_message": (
            "Будут удалены только локальные метаданные прогресса.\n"
            "Это не восстановит уже удалённые Telegram-сообщения.\n\n"
            "Удалить локальную базу сейчас?"
        ),
        "info_title": "Информация",
        "error_title": "Ошибка",
        "warning_title": "Предупреждение",
        "db_deleted": "Локальная база прогресса удалена.",
        "db_delete_blocked": "Сначала остановите активный worker, потом удаляйте базу.",
        "fill_required_fields": "Пожалуйста, заполните обязательные поля.",
        "worker_busy": "Сейчас уже выполняется другое действие.",
        "cleanup_finished": "Очистка завершена.",
        "retry_finished": "Повтор failed завершён.",
        "index_finished": "Индексирование завершено.",
        "delete_indexed_only_finished": "Удаление уже проиндексированных сообщений завершено.",
    },
}


class Translator:
    def __init__(self, language: str = "en") -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def set_language(self, language: str) -> None:
        self.language = language if language in TRANSLATIONS else "en"

    def gettext(self, key: str, **kwargs: object) -> str:
        bundle = TRANSLATIONS.get(self.language, TRANSLATIONS["en"])
        text = bundle.get(key, TRANSLATIONS["en"].get(key, key))
        if kwargs:
            return text.format(**kwargs)
        return text
