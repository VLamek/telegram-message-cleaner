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
        "qr_login": "QR login",
        "sign_in": "Sign in",
        "submit_2fa_password": "Submit 2FA password",
        "logout": "Logout",
        "auth_status": "Auth status",
        "authorized_as": "Authorized as",
        "chat_id": "Chat ID",
        "batch_size": "Batch size",
        "pause_between_batches": "Pause between batches (sec)",
        "date_from": "From date/time",
        "date_to": "To date/time",
        "date_format_hint": "Use YYYY-MM-DD HH:MM, or first/last",
        "message_types": "Message types",
        "message_type_all": "All message types",
        "message_type_text": "Text",
        "message_type_links": "Links",
        "message_type_photo": "Photos",
        "message_type_video": "Videos",
        "message_type_gif": "GIFs",
        "message_type_voice": "Voice",
        "message_type_video_note": "Video circles",
        "message_type_file": "Files",
        "message_type_sticker": "Stickers",
        "message_type_poll": "Polls",
        "message_type_other": "Other",
        "list_groups": "List groups",
        "select_chat": "Select chat",
        "search_chats": "Search chats",
        "chat_selected_column": "Select",
        "chat_title_column": "Title",
        "chat_id_column": "Chat ID",
        "chat_username_column": "Username",
        "chat_type_column": "Type",
        "use_selected_chat": "Use selected chat(s)",
        "refresh_chat_list": "Refresh chat list",
        "no_chat_selected": "Please select a chat from the list.",
        "chat_selected_message": "Selected chat {title} ({chat_id})",
        "multi_chat_selected_message": "Selected {count} chats.",
        "select_all_chats": "All",
        "all_chats_warning_title": "Select all chats",
        "all_chats_warning_first": (
            "You are about to select all {count} loaded chats.\n\n"
            "This can affect many chats if you start cleanup afterwards. Continue?"
        ),
        "all_chats_warning_second": (
            "Final warning: selecting all chats is broad and risky.\n\n"
            "The app will still wait for you to click a cleanup button, but any deletion action will run for every selected chat. Select all chats?"
        ),
        "all_chats_selected_message": "All loaded chats selected: {count}.",
        "multi_chat_title": "{count} selected chats",
        "confirm_multi_cleanup_message": (
            "Selected chats: {count}\n\n"
            "Date/time range: {date_range}\n\n"
            "Message types: {message_types}\n\n"
            "The app will process them one by one. Deletion is irreversible and Telegram may refuse or limit some deletions.\n\n"
            "Continue?"
        ),
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
            "Date/time range: {date_range}\n\n"
            "Message types: {message_types}\n\n"
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
        "qr_login_help": "Scan this QR code with Telegram on a device where your account is already logged in.",
        "qr_waiting": "Waiting for Telegram to confirm the QR scan...",
        "qr_expires_in": "QR expires in",
        "qr_login_link": "QR link",
        "copy_qr_link": "Copy QR link",
        "cancel_qr_login": "Cancel QR login",
        "qr_code_expired": "QR code expired. A new one will be generated automatically.",
        "qr_link_copied": "QR login link copied to clipboard.",
        "resume_prompt_title": "Continue saved progress?",
        "resume_prompt_heading": "Saved cleanup progress was found.",
        "resume_prompt_message": (
            "Chat: {title}\n"
            "Chat ID: {chat_id}\n"
            "Last phase: {phase}\n"
            "Indexed: {indexed}\n"
            "Deleted: {deleted}\n"
            "Pending: {pending}\n"
            "Failed: {failed}\n"
            "Last update: {last_update}\n\n"
            "Continue from the locally saved state?"
        ),
        "resume_continue": "Continue",
        "resume_review": "Review progress",
        "resume_dismiss": "Dismiss",
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
        "qr_login": "Вход по QR",
        "sign_in": "Войти",
        "submit_2fa_password": "Отправить пароль 2FA",
        "logout": "Выйти",
        "auth_status": "Статус авторизации",
        "authorized_as": "Аккаунт",
        "chat_id": "Chat ID",
        "batch_size": "Размер батча",
        "pause_between_batches": "Пауза между батчами (сек)",
        "date_from": "С даты/времени",
        "date_to": "По дату/время",
        "date_format_hint": "Формат YYYY-MM-DD HH:MM или first/last",
        "message_types": "Типы сообщений",
        "message_type_all": "Все типы сообщений",
        "message_type_text": "Текст",
        "message_type_links": "Ссылки",
        "message_type_photo": "Фото",
        "message_type_video": "Видео",
        "message_type_gif": "GIF",
        "message_type_voice": "Голосовые",
        "message_type_video_note": "Кружки",
        "message_type_file": "Файлы",
        "message_type_sticker": "Стикеры",
        "message_type_poll": "Опросы",
        "message_type_other": "Прочее",
        "list_groups": "Список групп",
        "select_chat": "Выбор чатов",
        "search_chats": "Поиск чатов",
        "chat_selected_column": "Выбор",
        "chat_title_column": "Название",
        "chat_id_column": "Chat ID",
        "chat_username_column": "Username",
        "chat_type_column": "Тип",
        "use_selected_chat": "Использовать выбранные чаты",
        "refresh_chat_list": "Обновить список",
        "no_chat_selected": "Выберите хотя бы один чат из списка.",
        "chat_selected_message": "Выбран чат {title} ({chat_id})",
        "multi_chat_selected_message": "Выбрано чатов: {count}.",
        "select_all_chats": "Все",
        "all_chats_warning_title": "Выбор всех чатов",
        "all_chats_warning_first": (
            "Вы собираетесь выбрать все загруженные чаты: {count}.\n\n"
            "Если потом запустить очистку, она затронет много чатов. Продолжить?"
        ),
        "all_chats_warning_second": (
            "Финальное предупреждение: выбор всех чатов - широкое и рискованное действие.\n\n"
            "Приложение все равно будет ждать нажатия кнопки очистки, но операция удаления пройдет по каждому выбранному чату. Выбрать все чаты?"
        ),
        "all_chats_selected_message": "Выбраны все загруженные чаты: {count}.",
        "multi_chat_title": "Выбрано чатов: {count}",
        "confirm_multi_cleanup_message": (
            "Выбрано чатов: {count}\n\n"
            "Диапазон дат/времени: {date_range}\n\n"
            "Типы сообщений: {message_types}\n\n"
            "Приложение обработает их по очереди. Удаление необратимо, а Telegram может отказать или ограничить часть удалений.\n\n"
            "Продолжить?"
        ),
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
            "Диапазон дат/времени: {date_range}\n\n"
            "Типы сообщений: {message_types}\n\n"
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
        "qr_login_help": "Отсканируйте этот QR-код в Telegram на устройстве, где ваш аккаунт уже авторизован.",
        "qr_waiting": "Ожидание подтверждения QR-входа от Telegram...",
        "qr_expires_in": "QR истекает через",
        "qr_login_link": "QR-ссылка",
        "copy_qr_link": "Скопировать QR-ссылку",
        "cancel_qr_login": "Отменить QR-вход",
        "qr_code_expired": "Срок действия QR-кода истёк. Новый код будет создан автоматически.",
        "qr_link_copied": "QR-ссылка скопирована в буфер обмена.",
        "resume_prompt_title": "Продолжить сохранённый прогресс?",
        "resume_prompt_heading": "Найден незавершённый прогресс очистки.",
        "resume_prompt_message": (
            "Чат: {title}\n"
            "Chat ID: {chat_id}\n"
            "Последняя фаза: {phase}\n"
            "Проиндексировано: {indexed}\n"
            "Удалено: {deleted}\n"
            "Осталось: {pending}\n"
            "Failed: {failed}\n"
            "Последнее обновление: {last_update}\n\n"
            "Продолжить с локально сохранённого состояния?"
        ),
        "resume_continue": "Продолжить",
        "resume_review": "Посмотреть прогресс",
        "resume_dismiss": "Пропустить",
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
