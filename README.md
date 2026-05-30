# Telegram Message Cleaner

`Telegram Message Cleaner` is a local Windows-first desktop utility for deleting your own Telegram messages from one selected chat at a time.

It authenticates through Telegram MTProto as a user account with `Telethon`, indexes message IDs for one explicit `chat_id`, stores only local progress metadata in SQLite, and then deletes pending message IDs in batches while showing progress, ETA, logs, pause/stop state, and retry information for failed deletions.

## What the app does

- Runs locally on your machine. It is not a SaaS product.
- Authenticates your own Telegram account through GUI fields for API ID, API Hash, phone number, login code, and 2FA password when needed.
- Lets you enter one `chat_id` and clean up only that chat for a given run.
- Indexes your own messages before deletion so the app can resume later and show progress more accurately.
- Deletes your own messages by message ID with `revoke=True` where Telegram allows it.
- Stores local progress metadata only:
  - `chat_id`
  - `message_id`
  - `message_date`
  - `status`
  - `last_error`
  - timestamps and run metadata
- Shows logs in the GUI and in local rotating log files.
- Supports `Pause after current batch`, `Stop after current batch`, resume on the next run, and `Retry failed`.

## What the app does not do

- It does not delete across all groups automatically.
- It does not scan all dialogs and clean everything at once.
- It does not clean multiple groups in parallel.
- It does not use the Telegram Bot API.
- It does not send your data anywhere except normal Telegram API calls needed for your own account operations.
- It does not store message text, captions, media content, file names, or raw message payloads.
- It does not restore deleted messages.

## Important warnings

- Deletion is irreversible.
- Telegram may refuse or limit some deletion operations depending on chat type, permissions, historical limits, service-message behavior, or API restrictions.
- Some message IDs may remain failed even after retries.
- Session files must never be shared with another person.

## Requirements

- Python 3.11+ recommended
- Windows 10/11 first
- Telegram API ID and API Hash from Telegram

Install dependencies:

```bash
pip install -r requirements.txt
```

## How to get Telegram API ID and API Hash

1. Open `https://my.telegram.org`.
2. Sign in with your Telegram account.
3. Open `API development tools`.
4. Create an application if needed.
5. Copy your `api_id` and `api_hash`.

Do not share your API Hash or your session file.

## How to run from Python

GUI:

```bash
python telegram_cleanup_gui.py
```

CLI fallback:

```bash
python telegram_cleanup_cli.py list
python telegram_cleanup_cli.py index --chat-id CHAT_ID
python telegram_cleanup_cli.py delete --chat-id CHAT_ID
python telegram_cleanup_cli.py retry-failed --chat-id CHAT_ID
```

CLI options:

- `--chat-id`
- `--batch-size` default `100`
- `--pause` default `2`
- `--db-file` default `telegram_message_cleaner.sqlite3`

## GUI flow

### 1. Authorize through the GUI

Open the GUI and fill:

- `API ID`
- `API Hash`
- `Phone number`

Then:

1. Click `Save API credentials`.
2. Click `Send code`.
3. Enter the login code from Telegram.
4. Click `Sign in`.
5. If Telegram asks for 2FA, enter the password and click `Submit 2FA password`.

The app shows auth status values:

- `not configured`
- `unauthorized`
- `code sent`
- `2FA required`
- `authorized`
- `auth error`

After successful authorization, the app shows available account information such as username, phone number, and first/last name when Telegram provides them.

### 2. List groups

Click `List groups`.

The GUI log will print dialog metadata such as:

- title
- id
- username when available
- type such as `user`, `chat`, `megagroup`, or `channel`

This action does not delete anything.

### 3. Enter one Chat ID

Paste one explicit Telegram `chat_id` into the `Chat ID` field.

The app is intentionally limited to one chat per cleanup run.

### 4. Start cleanup

Set:

- `Batch size`
- `Pause between batches`

Then click:

- `Index only` if you want only the metadata pass
- `Start cleanup` if you want indexing followed by deletion

If `Require confirmation before deletion` is enabled, the app resolves the chat first and then shows a confirmation dialog with:

- chat title
- chat ID
- currently known indexed count
- an irreversible deletion warning

### 5. How indexing works

Indexing scans the selected chat and records only minimal metadata for messages sent by the authorized user.

It does not store:

- message text
- captions
- media bytes
- file names
- forwarded payload content

It stores only local progress metadata in SQLite so the app can resume later and avoid duplicating already known records.

### 6. Why indexing is needed

Indexing is required because the app needs a known local list of message IDs before deletion can show meaningful:

- total known messages
- remaining pending messages
- deleted count
- failed count
- percentage
- approximate ETA

During indexing, progress is count-based rather than true percentage-based because the total may still be unknown.

### 7. Pause, stop, and resume

- `Pause after current batch` finishes the active batch, saves SQLite state, and pauses safely.
- `Stop after current batch` finishes the active batch, saves SQLite state, and stops safely.
- To resume later, run the app again, enter the same `chat_id`, and click `Start cleanup`.

If new messages appeared in the same chat after a previous run, a new indexing pass adds only new message IDs without duplicating older records.

### 8. Retry failed

`Retry failed` attempts deletion again for message IDs currently marked as failed in the local database.

The app still does not store message content during this process.

## Local database and logs

Default local files are kept next to the Python scripts during development, and next to the `.exe` when running as a frozen Windows build:

- `telegram_message_cleaner_config.json`
- `telegram_message_cleaner.session`
- `telegram_message_cleaner.sqlite3`
- `TelegramMessageCleaner_Logs/latest.log`
- `TelegramMessageCleaner_Logs/history.log`

You can delete the local progress database with `Delete local progress database`.

That action:

- deletes only local progress metadata
- does not restore already deleted Telegram messages

## Simple light/dark theme

The GUI supports `Light` and `Dark`.

The dark theme is intentionally simple and utilitarian. The goal is readability and comfort, not a polished design system.

## Windows packaging

See [build_windows_exe.md](build_windows_exe.md) for packaging instructions.

Recommended stable build:

```bash
pyinstaller --onedir --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

Optional single-file build:

```bash
pyinstaller --onefile --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

## Security and privacy notes

- The app runs locally.
- It does not have analytics, telemetry, or a backend.
- It does not upload stored metadata anywhere.
- It does not store message content.
- It should never ship with someone else's Telegram session file.

## Sharing the app with another person

Another trusted person can use the app locally, but they must use:

- their own Telegram account
- their own API ID
- their own API Hash
- their own phone number
- their own login code
- their own 2FA password if enabled

Do not give them your own `telegram_message_cleaner.session` file.
