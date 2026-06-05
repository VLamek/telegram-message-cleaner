# Telegram Message Cleaner

Telegram Message Cleaner is a local desktop app for deleting your own Telegram messages from selected chats and groups.

It uses the normal Telegram MTProto user flow through Telethon: API ID, API Hash, phone number, login code, and a 2FA password when Telegram requires one. The app runs locally, stores only local progress metadata, and does not include analytics, telemetry, a backend, or bundled Telegram credentials.

## 1. What The App Does

- Lists Telegram dialogs available to your authorized account.
- Lets you choose one or many chats or groups.
- Lets you choose a date/time range through a modal picker.
- Lets you choose message types such as text, links, photos, videos, files, stickers, polls, and other records.
- Indexes your own messages before deletion so deletion can resume after interruption.
- Deletes your own messages in batches with Telegram `revoke=True` where Telegram allows it.
- Shows progress, ETA, logs, pause/stop state, failed deletions, and retry information.
- Keeps local progress metadata in SQLite so unfinished runs can continue later.

The app does not store message text, captions, media bytes, file names, or raw message payloads.

## 2. Who It Is For

Use this app if you need a local utility to clean up messages sent by your own Telegram account in specific chats or groups.

It is not for automated account farming, hidden background deletion, deleting other people's messages, or bypassing Telegram restrictions.

## 3. What It Deletes And Telegram Limits

Telegram Message Cleaner attempts to delete messages sent by the authorized user account in the selected chats.

Important limits:

- Deletion is irreversible.
- Telegram can refuse or limit deletion depending on chat type, permissions, message age, service-message behavior, FloodWait limits, or API rules.
- Some message IDs can remain failed even after retries.
- The app processes multiple chats sequentially, not in parallel.
- The app does not restore deleted messages.
- The app does not use the Telegram Bot API.

## 4. Download A Ready Release

Open the repository's GitHub Releases page and download the artifact for your platform.

Release artifacts are built by GitHub Actions from this repository:

- Windows 64-bit installer: `TelegramMessageCleaner-windows-x64-setup.exe`
- Windows 32-bit installer: `TelegramMessageCleaner-windows-x86-setup.exe`
- macOS Apple Silicon installer image: `TelegramMessageCleaner-macos-arm64.dmg`

Portable ZIP packages may also be attached for Windows and macOS for users who prefer not to run an installer.

## 5. Which Installer To Choose

- Windows 64-bit: choose `TelegramMessageCleaner-windows-x64-setup.exe` for most Windows 10/11 computers.
- Windows 32-bit: choose `TelegramMessageCleaner-windows-x86-setup.exe` only for a 32-bit Windows installation.
- macOS ARM: choose `TelegramMessageCleaner-macos-arm64.dmg` for Apple Silicon Macs such as M1, M2, M3, or newer.

No Telegram session file, API ID, API Hash, token, or secret is included in release artifacts.

## 6. Get API ID And API Hash

Telegram requires an API ID and API Hash for user-account MTProto applications.

1. Open the official Telegram developer site: `https://my.telegram.org`.
2. Sign in with your Telegram account.
3. Open `API development tools`.
4. Create an application if you do not already have one.
5. Copy the generated `API ID` and `API Hash`.
6. Paste them into Telegram Message Cleaner.

Do not share your API Hash. Do not use someone else's public API ID or API Hash.

VPN, proxy, WARP, datacenter networks, or suspicious IP addresses can prevent Telegram from creating an app or showing API credentials. If Telegram refuses to create an application or behaves strangely, first try again without VPN/proxy, from normal home internet or mobile internet.

## 7. Authorize In The App

The only supported authorization flow is the regular Telegram API login flow.

1. Start the app.
2. Enter `API ID`, `API Hash`, and `Phone number`.
3. Click `Save API credentials`.
4. Click `Send code`.
5. Enter the login code received from Telegram.
6. Click `Sign in`.
7. If Telegram asks for 2FA, enter your 2FA password and click `Submit 2FA password`.

Auth statuses include:

- `not configured`
- `unauthorized`
- `code sent`
- `2FA required`
- `authorized`
- `auth error`

No alternate authorization method is exposed in the app.

## 8. Choose Groups

Click `List groups` to open the chat selection window.

The selector includes:

- a search field;
- a scrollable table of dialogs;
- checkbox-style row selection;
- normal multi-row selection;
- an `All` checkbox with two warning confirmations;
- a confirmation button in the lower-right corner.

Double-clicking a row does not confirm selection. Select the rows you need, then click the lower-right confirmation button. If nothing is selected, the app shows a warning and does not continue.

For many selected chats, the progress panel shows a compact summary instead of a long ID list.

## 9. Start Deletion

Choose:

- `Batch size`;
- `Pause between batches`;
- date/time range through `Select range`;
- message types when the modal opens.

Then click one of:

- `Index only` to collect local message metadata without deleting;
- `Start cleanup` to index and then delete;
- `Delete indexed only` to delete already indexed messages;
- `Retry failed` to retry records from the failed database.

If confirmation is enabled, the app shows the selected chat, known indexed count, date range, message types, and an irreversible deletion warning before deleting.

## 10. If Deletion Was Interrupted

The app stores local progress metadata in SQLite.

- `Pause after current batch` finishes the active batch and pauses safely.
- `Stop after current batch` finishes the active batch and stops safely.
- On the next startup, the app can offer to continue saved progress.
- You can also enter the same chat and run `Start cleanup`, `Delete indexed only`, or `Retry failed` again.

The app does not duplicate already known local records when resuming.

## 11. Common Problems

`API ID` or `API Hash` cannot be created:

- Try without VPN, proxy, WARP, or datacenter IPs.
- Use normal home internet or mobile internet.
- Do not use public API credentials from other people.

Telegram asks for 2FA:

- Enter your Telegram 2FA password in the app and submit it.

FloodWait or rate limits:

- Increase pause between batches.
- Stop and resume later.

Messages remain failed:

- Telegram may refuse those deletions.
- Use `Retry failed` later.
- Check local logs for the exact failure reason.

The app window looks too wide after selecting many groups:

- Current releases use compact multi-chat progress. Details stay in logs instead of the progress ID field.

## 12. Build From Source

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the GUI:

```bash
python telegram_cleanup_gui.py
```

Run basic tests:

```bash
python -m unittest discover -s tests
python -m compileall telegram_cleanup_gui.py telegram_cleanup_core.py telegram_cleanup_i18n.py telegram_cleanup_storage.py telegram_cleanup_cli.py
```

Build a local Windows package:

```powershell
.\scripts\build_windows.ps1 -Arch x64 -AppVersion 1.0.0
```

This creates local artifacts under `release/`. If Inno Setup is installed and available as `iscc`, it also creates a Windows setup executable.

Build macOS ARM on an Apple Silicon Mac:

```bash
APP_VERSION=1.0.0 ./scripts/build_macos_arm.sh
```

To build from an isolated virtual environment, pass its Python explicitly:

```bash
PYTHON=.venv/bin/python APP_VERSION=1.0.0 ./scripts/build_macos_arm.sh
```

## 13. Available Interface Languages

- English: `en`
- Russian: `ru`
- Spanish: `es`
- Simplified Chinese: `zh-CN`
- French: `fr`

The selected language is saved in the local config. Missing translation keys fall back safely to English.

## Release Artifact Automation

The workflow `.github/workflows/release-artifacts.yml` builds:

- Windows x64 installer and portable ZIP;
- Windows x86 installer and portable ZIP;
- macOS ARM DMG and app ZIP.

Run it manually from GitHub Actions or push a `v*` tag. Tag builds publish artifacts to GitHub Releases.

## Local Data And Privacy

When running from source, local data is stored outside the repository by default in the user's local app data directory.

When running as a frozen macOS build, local runtime files are stored in:

- `~/Library/Application Support/TelegramMessageCleaner/`

This lets the app start correctly from a read-only DMG before it is copied elsewhere.

When running as a frozen Windows build, local runtime files are stored next to the executable:

- `telegram_message_cleaner_config.json`
- `telegram_message_cleaner.session`
- `telegram_message_cleaner.sqlite3`
- `telegram_message_cleaner_failed.sqlite3`
- `TelegramMessageCleaner_Logs/latest.log`
- `TelegramMessageCleaner_Logs/history.log`

Do not distribute your session file. Another person must use their own Telegram account, API ID, API Hash, phone number, login code, and 2FA password.
