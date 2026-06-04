# Telegram Message Cleaner

`Telegram Message Cleaner` is a local Windows-first desktop utility for deleting your own Telegram messages from selected Telegram chats.

It authenticates through Telegram MTProto as a user account with `Telethon`, indexes message IDs for explicit `chat_id` values, stores only local progress metadata in SQLite, and then deletes pending message IDs in batches while showing progress, ETA, logs, pause/stop state, and retry information for failed deletions.

## What the app does

- Runs locally on your machine. It is not a SaaS product.
- Authenticates your own Telegram account through GUI fields for API ID, API Hash, phone number, login code, and 2FA password when needed.
- Supports QR login from the GUI as an alternative to manual code entry when Telegram prefers in-app authorization.
- Lets you enter one `chat_id`, or select multiple chats in the GUI picker for sequential processing.
- Lets you limit the current indexing/deletion run to a custom date/time range.
- Lets you choose which message types to delete in the current run.
- Indexes your own messages before deletion so the app can resume later and show progress more accurately.
- Deletes your own messages by message ID with `revoke=True` where Telegram allows it.
- Uses the main SQLite database as a local work queue. Confirmed deleted messages are removed from that queue after verification.
- Moves failed deletion metadata into a separate failed SQLite database so retry can work without leaving completed work in the main database.
- Stores local progress metadata only:
  - `chat_id`
  - `message_id`
  - `message_date`
  - `status`
  - `last_error`
  - timestamps and run metadata
- Shows logs in the GUI and in local rotating log files.
- Supports `Pause after current batch`, `Stop after current batch`, resume on the next run, and `Retry failed`.
- On startup, offers to continue locally saved unfinished progress in a visible dialog.

## What the app does not do

- It does not delete across all groups automatically without explicit selection and warnings.
- It does not scan all dialogs and clean everything in the background.
- It does not clean multiple groups in parallel.
- It does not use the Telegram Bot API.
- It does not send your data anywhere except normal Telegram API calls needed for your own account operations.
- It does not store message text, captions, media content, file names, or raw message payloads.
- It does not restore deleted messages.

## Important warnings

- Deletion is irreversible.
- Telegram may refuse or limit some deletion operations depending on chat type, permissions, historical limits, service-message behavior, or API restrictions.
- Some message IDs may remain failed even after retries.
- The app now verifies after each delete request whether the target `message_id` actually disappeared. If Telegram leaves some items behind, they are moved to the separate failed database instead of being reported as deleted.
- Poll messages sent by the user can be deleted when Telegram allows it, but resetting poll votes themselves is not guaranteed by Telegram.
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

## Local safety against git commits

When you run the app from source inside a git repository, the app now keeps its persistent local data outside the repository by default, in the current user's local application data directory.

This is done so values entered into the GUI, such as API credentials, phone number, local session state, database progress, and logs, do not end up as normal files inside the repo and do not get committed accidentally.

If you explicitly choose a custom database path inside the repository, the app also adds that runtime path to the local git exclude file when possible.

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
python telegram_cleanup_cli.py delete-indexed --chat-id CHAT_ID
python telegram_cleanup_cli.py retry-failed --chat-id CHAT_ID
```

CLI options:

- `--chat-id`
- `--batch-size` default `100`
- `--pause` default `2`
- `--from-date` default `first`
- `--to-date` default `last`
- `--message-types` default `all`
- `--db-file` default `telegram_message_cleaner.sqlite3`

## GUI flow

### 1. Authorize through the GUI

Open the GUI and fill:

- `API ID`
- `API Hash`
- `Phone number`

Then:

1. Click `Save API credentials`.
2. Either click `Send code` and enter the login code from Telegram, or click `QR login` and scan the QR code with Telegram on a device where the account is already logged in.
3. If you used the code flow, click `Sign in`.
4. If Telegram asks for 2FA, enter the password and click `Submit 2FA password`.

The app shows auth status values:

- `not configured`
- `unauthorized`
- `code sent`
- `2FA required`
- `authorized`
- `auth error`

After successful authorization, the app shows available account information such as username, phone number, and first/last name when Telegram provides them.

### QR login notes

- `QR login` opens a separate QR window inside the app.
- The QR code is generated locally; the app does not send it to any external QR service.
- While the QR is shown, the app keeps the Telethon `qr_login().wait()` flow active in the background.
- If the QR token expires before you scan it, the app automatically generates a fresh QR token.
- If the QR scan is accepted but Telegram requires 2FA, enter the password in the main window and click `Submit 2FA password`.

### 2. List groups

Click `List groups`.

The app opens a separate chat selection window with:

- a search field
- a scrollable table of dialogs
- checkbox-style row selection
- an `All` checkbox that requires two separate warning confirmations before it selects every loaded chat
- automatic filling of the chosen `chat_id` values back into the main window

The GUI log will also print dialog metadata such as:

- title
- id
- username when available
- type such as `user`, `chat`, `megagroup`, or `channel`

This action does not delete anything.

### 3. Enter Chat IDs

Paste one explicit Telegram `chat_id` into the `Chat ID` field, paste multiple IDs separated by commas, or select chats from the graphical chat picker opened by `List groups`.

When multiple chats are selected, the app processes them sequentially, one chat at a time. It does not run parallel cleanup across chats.

### 4. Start cleanup

Set:

- `Batch size`
- `Pause between batches`

Then click:

- `Index only` if you want only the metadata pass
- `Start cleanup` if you want indexing followed by deletion
- `Delete indexed only` if you want to delete the already indexed subset immediately without waiting for a full indexing pass

By default, the date/time range fields are:

- `From date/time`: `first`
- `To date/time`: `last`

That means the app covers the full available chat history, like before. To limit the current run, replace those values with a local date/time such as `2026-01-01 00:00` and `2026-01-31 23:59`. A date without time, such as `2026-01-01`, means start of that day in `From` and end of that day in `To`.

When you start a deletion action, the app opens a modal message type selector. By default, all message types are enabled. You can limit the current run to types such as text, links, photos, videos, GIFs, voice messages, video circles, files, stickers, polls, or other message records.

If `Require confirmation before deletion` is enabled for one selected chat, the app resolves the chat first and then shows a confirmation dialog with:

- chat title
- chat ID
- currently known indexed count
- selected date/time range
- selected message types
- an irreversible deletion warning

If multiple chats are selected, the app shows a multi-chat confirmation warning before deletion starts. Chats are still processed one by one.

### 5. How indexing works

Indexing scans the selected chat and records only minimal metadata for messages sent by the authorized user inside the selected date/time range and selected message types.

It does not store:

- message text
- captions
- media bytes
- file names
- forwarded payload content

It stores only local progress metadata in SQLite so the app can resume later and avoid duplicating already known records.

If indexing is interrupted, the app now saves its local resume cursor and the next indexing run continues from the saved point in the older history direction while also checking for newer messages that appeared later.

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
- If the app finds unfinished local progress on startup, it shows a dialog over the main window so you can continue, review the saved progress, or dismiss it.
- If you only want to delete the already discovered subset first, use `Delete indexed only` in the GUI or `delete-indexed` in the CLI.

If new messages appeared in the same chat after a previous run, a new indexing pass adds only new message IDs without duplicating older records.

### 8. Retry failed

`Retry failed` attempts deletion again for message IDs stored in the separate failed database.

The app still does not store message content during this process.

After a deletion run finishes from start to end, the main progress database is cleared for that chat. Failed message metadata, if any, remains in the failed database for retry.

## Local database and logs

When running from source during development, local runtime files are stored in the current user's local app data folder, typically under:

- `%LOCALAPPDATA%\\TelegramMessageCleaner\\`

When running as a frozen Windows build, local runtime files are kept next to the `.exe`:

- `telegram_message_cleaner_config.json`
- `telegram_message_cleaner.session`
- `telegram_message_cleaner.sqlite3`
- `telegram_message_cleaner_failed.sqlite3`
- `TelegramMessageCleaner_Logs/latest.log`
- `TelegramMessageCleaner_Logs/history.log`

You can delete the local progress database with `Delete local progress database`.

That action:

- deletes only local progress metadata
- deletes both the main progress database and the failed retry database
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
