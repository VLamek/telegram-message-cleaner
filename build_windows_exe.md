# Build Windows EXE

## Goal

The first stable packaging target is a Windows `--onedir` PyInstaller build for `Telegram Message Cleaner`.

This mode is recommended because it keeps the executable and persistent local files together more predictably.

## Install dependencies

```bash
pip install -r requirements.txt
```

## Recommended build

```bash
pyinstaller --onedir --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

## Optional single-file build

```bash
pyinstaller --onefile --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

## Output

After a successful build, PyInstaller creates output under `dist/`.

Recommended executable path for the `--onedir` build:

```text
dist/TelegramMessageCleaner/TelegramMessageCleaner.exe
```

## Persistent local files

When the app runs as a frozen executable, it stores persistent local files next to the executable, not inside a temporary PyInstaller extraction folder.

Expected files:

- `telegram_message_cleaner_config.json`
- `telegram_message_cleaner.session`
- `telegram_message_cleaner.sqlite3`
- `TelegramMessageCleaner_Logs/`

## Notes

- `--onedir` is the safer first target.
- `--onefile` is supported but can be less convenient for debugging.
- Do not distribute your own session file with the build.
- Another person should run the EXE locally and authorize with their own Telegram account and credentials.
