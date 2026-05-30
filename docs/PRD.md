# PRD: Telegram Message Cleaner

## 1. Product Summary

**Product name:** Telegram Message Cleaner

**Product type:** Local desktop utility

**Primary platform:** Windows 10/11

**Future platform:** macOS, after the Windows version is stable

**Primary user:** The owner of the local Telegram account

**Secondary user:** Another trusted person who receives the app and runs it locally on their own computer with their own Telegram account and credentials

Telegram Message Cleaner is a local desktop application that lets a user delete all of their own messages from a selected Telegram group by entering one `chat_id`. The app authenticates the user through Telegram MTProto via Telethon, indexes all messages sent by the authenticated user in the selected chat, then deletes those messages in batches while showing progress, speed, ETA, logs, and recovery state.

The app is not a public App Store-style product. It is intended for personal use and trusted sharing.

The first implementation target is a stable, functional Windows version. Visual polish is secondary. The app should be simple, reliable, understandable, and safe to use locally.

---

## 2. Core Goal

The user should be able to:

1. Launch the app by double-clicking an `.exe` file on Windows.
2. Authorize their Telegram account inside the GUI.
3. Enter one Telegram `chat_id`.
4. Start cleanup.
5. Let the app autonomously delete all of their own messages from that chat.
6. Track progress, remaining message count, speed, ETA, errors, and Telegram waiting periods.
7. Stop, pause, close, or restart the app without losing progress.
8. Resume the same cleanup later.
9. Repeat the process for another group by entering another `chat_id`.

---

## 3. Non-Goals

The app must not:

1. Delete messages from all Telegram groups automatically.
2. Search all groups and delete messages from them automatically.
3. Delete messages from multiple groups simultaneously.
4. Store message text.
5. Upload Telegram data, session files, logs, message metadata, or credentials anywhere.
6. Act as a Telegram bot.
7. Require a server.
8. Require cloud infrastructure.
9. Require the user to manually edit `.env` files for normal GUI usage.
10. Be polished as a public commercial release in the first version.
11. Over-engineer the graphical interface.
12. Spend excessive effort on visual styling, animations, or a complex design system.

---

## 4. User Scenarios

### 4.1 First-time setup

The user launches the app.

The app shows a setup/authentication screen:

- API ID field
- API Hash field
- Phone number field
- Send code button
- Login code field
- Sign in button
- 2FA password field, shown only when needed
- Authorization status label

The user enters Telegram API credentials, phone number, receives a login code, enters it, and completes authorization.

The app stores local configuration for local personal use:

- API ID and API Hash in a local config file
- Telegram session file next to the app
- no secrets printed in logs

For development, `.env` may still be supported as fallback, but normal GUI usage should not require `.env`.

---

### 4.2 Regular cleanup

The user opens the app.

The app shows:

- Authorized account label, for example: `Authorized as @username` or `Authorized as +phone`
- Chat ID input
- Start cleanup button
- Index only button
- Pause after current batch button
- Stop after current batch button
- Retry failed button
- Delete local progress database button
- List groups button
- Progress bar
- Stats panel
- GUI log panel

The user enters one `chat_id` and clicks Start cleanup.

The app:

1. Resolves the chat.
2. Shows the selected chat title.
3. Checks whether there is already progress for this `chat_id`.
4. Shows the existing state when applicable:
   - indexed messages
   - deleted messages
   - pending messages
   - failed messages
   - last run status
5. Indexes missing messages.
6. Deletes pending messages in batches.
7. Updates SQLite state after every batch.
8. Shows progress and ETA.
9. Handles Telegram rate limits by waiting automatically.
10. Completes and shows final summary.

---

### 4.3 Interrupted cleanup

The app may be closed, stopped, paused, or interrupted.

After restart, the user enters the same `chat_id`.

The app detects existing unfinished progress and shows:

- existing cleanup found for this chat
- indexed count
- deleted count
- pending count
- failed count
- last update time

The user can continue the cleanup.

The app should not re-delete messages already marked as deleted.

---

### 4.4 New messages after previous cleanup

The user may return to the same group later after writing new messages.

The app must allow running cleanup again for the same `chat_id`.

Expected behavior:

1. Existing SQLite state is reused.
2. Already known deleted messages are not processed again.
3. The app performs a new indexing pass.
4. New messages from the authenticated user are added as `pending`.
5. Pending messages are deleted.

---

### 4.5 Sharing with another person

The user may give the app to another trusted person.

That person runs the app locally on their own computer.

They must use their own:

- Telegram API ID
- Telegram API Hash
- Telegram account
- Telegram login code
- Telegram 2FA password, when enabled

No shared Telegram session or credentials should be bundled into the app.

---

## 5. Functional Requirements

## 5.1 Authentication

The app must support GUI-based Telegram authentication.

Required fields and actions:

- API ID
- API Hash
- Phone number
- Send code
- Login code
- Sign in
- 2FA password
- Submit 2FA password
- Logout

The app must show the current authorization state:

- Not configured
- Unauthorized
- Code sent
- 2FA required
- Authorized
- Auth error

When authorized, the GUI must show the current account:

- username, when available
- phone, when available
- first name / last name, when available

Logout must:

1. Disconnect the client.
2. Remove or invalidate the local Telegram session file.
3. Clear the authorized account label.
4. Keep app settings unless the user explicitly clears them.

The app must never print or log:

- API Hash
- Telegram login code
- 2FA password
- session string
- raw session file contents

---

## 5.2 Chat Selection

The app works with exactly one explicitly entered `chat_id` per cleanup run.

The GUI must contain one Chat ID field.

The app must not provide a mode for deleting from every group.

The app must not provide a mode for deleting from all dialogs.

The app may provide a `List groups` button only to help the user find the correct `chat_id`.

`List groups` must output to the GUI log:

- title
- id
- username, when available
- type: user / chat / megagroup / channel

`List groups` must never delete anything.

---

## 5.3 Message Scope

The app must delete all message types sent by the authenticated user in the selected chat.

This includes, where Telegram API permits deletion:

- text messages
- stickers
- photos
- videos
- voice messages
- video messages
- files
- GIFs
- polls sent by the user
- forwarded messages sent by the user
- replies sent by the user
- media messages sent by the user

The app deletes messages by message ID. It does not need to inspect or store message content.

The app should use Telethon message iteration filtered by the authenticated user.

The app must attempt to delete messages with `revoke=True`, so deletion is attempted for all chat participants where Telegram allows it.

The app should be explicit in README:

- Telegram may not allow deleting every historical message in every situation.
- Some messages may fail because of Telegram restrictions, permissions, service-message behavior, or API errors.
- Failed messages should be logged by metadata only.

---

## 5.4 Indexing

The app must support an indexing phase.

Indexing means:

1. Resolve the selected chat.
2. Iterate through messages in the selected chat where sender is the authenticated user.
3. Store message metadata in SQLite.

Stored message metadata:

- `chat_id`
- `message_id`
- `message_date`
- `status`
- `last_error`
- `updated_at`

The app must not store:

- message text
- media content
- file names from messages
- captions
- sender names from message bodies
- any private message payload

Indexing is needed for accurate progress and ETA.

During indexing:

- progress bar may be indeterminate
- GUI should show count of indexed messages found so far
- GUI must remain responsive
- stop/pause should be handled safely

After indexing:

- total count becomes known
- progress bar switches to determinate mode
- ETA during deletion becomes possible

---

## 5.5 Deletion

Deletion must run in batches.

Default batch size: `100`

Default pause between batches: `2 seconds`

Both values should be editable in the GUI.

Deletion must:

1. Read pending message IDs from SQLite.
2. Delete them via Telethon in batches.
3. Use `revoke=True`.
4. Mark successfully deleted messages as `deleted`.
5. Mark failed messages or failed batches as `failed`.
6. Save progress after every batch.
7. Continue after recoverable errors.
8. Handle Telegram FloodWait automatically.
9. Keep GUI responsive.

The app should not crash the whole cleanup because one batch failed.

The app should produce a final summary:

- chat title
- chat ID
- indexed count
- deleted count
- pending count
- failed count
- elapsed time
- average deletion speed
- final status

---

## 5.6 Confirmation Behavior

The app must provide a user setting:

**Require confirmation before deletion**

Default value: enabled.

When enabled:

- clicking Start cleanup shows a confirmation dialog after chat resolution and before deletion
- dialog must show:
  - chat title
  - chat ID
  - indexed / estimated message count, when available
  - warning that deletion is irreversible
- user must confirm before deletion starts

When disabled:

- clicking Start cleanup starts indexing and deletion without extra confirmation

The user personally may disable this setting.

The app should remember the setting locally.

---

## 5.7 Pause, Stop, and Resume

The app must support:

1. Pause after current batch
2. Stop after current batch
3. Resume later

Pause behavior:

- does not kill the worker immediately
- finishes the current batch
- saves SQLite state
- sets run state to `paused`
- keeps app open
- allows continuing from the same screen

Stop behavior:

- does not kill the worker immediately
- finishes the current batch
- saves SQLite state
- sets run state to `stopped`
- allows app closure
- allows resuming later

Resume behavior:

- user enters same `chat_id`
- app detects existing state
- app shows unfinished cleanup state
- app can continue pending messages

The app must not lose progress on normal stop, pause, close, or restart.

---

## 5.8 Failed Messages and Retry

The app must track failed deletions.

For failed messages or failed batches, store:

- `chat_id`
- `message_id` or batch message IDs
- `message_date`, when known
- error type
- error message
- timestamp

The app must not store message text.

The GUI must show failed count.

The app should provide:

- Retry failed button
- CLI retry-failed command

Retry failed should:

1. Move failed messages back to pending, or directly retry failed messages.
2. Attempt deletion again.
3. Update statuses.

---

## 5.9 Progress and ETA

The app must show progress during deletion.

After indexing, total is known:

```text
total = pending + deleted + failed
```

Deletion stats:

```text
deleted = count(status = "deleted")
pending = count(status = "pending")
failed = count(status = "failed")
remaining = pending
```

Speed:

```text
speed = deleted_since_run_start / elapsed_minutes
```

ETA:

```text
eta = remaining / speed
```

ETA must be displayed as approximate.

Example formats:

- `~ 4 min`
- `~ 1 h 20 min`
- `calculating...`
- `waiting because of Telegram FloodWait`

The GUI should warn that ETA is unstable during the first few batches.

The stats panel should show:

- current phase
- selected chat title
- selected chat ID
- indexed messages
- deleted messages
- pending messages
- failed messages
- percentage
- speed, messages per minute
- approximate ETA
- current batch number
- FloodWait countdown when applicable

---

## 5.10 Logging

The app must log to:

1. GUI log panel
2. Local log files

Log folder should be placed next to the app.

Recommended folder:

```text
TelegramMessageCleaner_Logs/
```

Recommended files:

```text
TelegramMessageCleaner_Logs/latest.log
TelegramMessageCleaner_Logs/history.log
```

`latest.log`:

- easier for debugging the current or last run
- may rotate around 5 MB

`history.log`:

- stores broader history
- may rotate around 100 MB

The exact rotation implementation can be simple and practical.

Logs may contain:

- timestamps
- phase
- chat ID
- chat title
- indexed count
- deleted count
- pending count
- failed count
- batch number
- speed
- ETA
- FloodWait duration
- error type
- error text
- message IDs for failed messages
- message dates for failed messages

Logs must not contain:

- message text
- message media
- API Hash
- login code
- 2FA password
- session string
- raw session content

---

## 5.11 Local Database

Use SQLite for progress storage.

The user does not need to install SQLite separately. Use Python standard library `sqlite3`.

Default database file:

```text
telegram_message_cleaner.sqlite3
```

The database should be stored next to the app.

The GUI must show the database path.

The GUI should allow selecting another database file in Advanced settings.

The GUI must provide:

- Delete local progress database button

When deleting the local database:

- ask for confirmation
- explain that this only deletes local progress metadata
- explain that it does not restore deleted Telegram messages
- disconnect safely from active runs first, or disable the button during active runs

---

## 6. SQLite Schema

Minimum schema:

```sql
CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    title TEXT,
    username TEXT,
    chat_type TEXT,
    indexed_at TEXT,
    status TEXT,
    updated_at TEXT
);
```

```sql
CREATE TABLE IF NOT EXISTS messages (
    chat_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    message_date TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'deleted', 'failed')),
    last_error TEXT,
    updated_at TEXT,
    PRIMARY KEY(chat_id, message_id)
);
```

```sql
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    phase TEXT,
    started_at TEXT,
    finished_at TEXT,
    indexed_count INTEGER DEFAULT 0,
    deleted_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    status TEXT
);
```

```sql
CREATE TABLE IF NOT EXISTS failed_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    message_ids TEXT NOT NULL,
    error TEXT,
    created_at TEXT
);
```

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## 7. GUI Requirements

Use Tkinter and ttk.

The GUI should be clean, simple, stable, and functional.

No complex visual design is required for MVP.

The interface should not be over-engineered.

Main window title:

```text
Telegram Message Cleaner
```

Main sections:

1. Auth
2. Chat cleanup
3. Progress
4. Logs
5. Settings / Advanced

---

## 7.1 Auth Section

Fields:

- API ID
- API Hash
- Phone number
- Login code
- 2FA password

Buttons:

- Save API credentials
- Send code
- Sign in
- Submit 2FA password
- Logout

Labels:

- Authorization status
- Authorized as

Requirements:

- API Hash field should be hidden by default or maskable.
- 2FA password field must use hidden input.
- Login code must not be logged.
- 2FA password must not be logged.
- API Hash must not be logged.

---

## 7.2 Chat Cleanup Section

Fields:

- Chat ID
- Batch size
- Pause between batches
- Database path

Buttons:

- List groups
- Index only
- Start cleanup
- Pause after current batch
- Stop after current batch
- Retry failed
- Delete local progress database

Checkboxes / selectors:

- Require confirmation before deletion
- Theme selector
- Language selector

Language selector:

- English
- Russian

Default language:

- English

The app must support UI text switching at least between English and Russian.

---

## 7.3 Progress Section

Show:

- phase
- selected chat title
- selected chat ID
- indexed count
- deleted count
- pending count
- failed count
- percentage
- speed
- ETA
- current batch
- FloodWait countdown

Progress bar behavior:

- indexing: indeterminate or count-only progress
- deleting: determinate progress
- waiting: keep visible and show waiting status
- completed: 100%
- error: keep last known state visible

---

## 7.4 Logs Section

Read-only text area.

Must show human-readable events:

- app started
- auth status
- chat resolved
- indexing started
- indexing count updates
- indexing completed
- deletion started
- batch deleted
- FloodWait waiting
- pause requested
- stop requested
- cleanup paused
- cleanup stopped
- cleanup completed
- failed batch
- retry failed started
- retry failed completed
- database deleted
- logout completed

The log area must not show message text.

---

## 7.5 Theme

The app must support a simple light/dark theme toggle.

Theme is not a design-heavy feature.

The goal of dark theme is practical comfort only:

- if the user works in a dark OS environment, the app should not be painfully bright;
- the app does not need a polished premium dark design;
- the app does not need complex custom widgets;
- the app does not need advanced styling or animations.

For MVP, implement dark theme in the simplest reliable way:

- dark window background;
- light text;
- readable input fields;
- readable buttons;
- readable log area;
- readable progress/status labels.

It is acceptable if some native Tkinter/ttk elements keep a simple system look, as long as the interface remains usable and not blindingly white.

Theme options:

- Light
- Dark

Optional later:

- System

Default theme:

- Light, unless a saved user setting exists.

Theme preference must be saved locally.

Do not spend excessive implementation effort on visual polish. Functionality, stability, progress tracking, and safe deletion behavior are more important than theme aesthetics.

---

## 8. Threading and Async Requirements

Telethon is async.

Tkinter must not be updated directly from background threads.

Recommended architecture:

- Core logic uses asyncio.
- GUI starts core tasks in a background thread.
- Communication from worker to GUI happens via `queue.Queue`.
- GUI polls queue via `root.after`.
- Stop/pause flags are thread-safe.

The GUI must remain responsive during:

- authorization
- indexing
- deletion
- FloodWait waiting
- retry failed
- logging

---

## 9. Core Architecture

Files:

```text
telegram_cleanup_core.py
telegram_cleanup_gui.py
telegram_cleanup_cli.py
docs/PRD.md
README.md
build_windows_exe.md
requirements.txt
.gitignore
```

Optional later files:

```text
telegram_cleanup_i18n.py
telegram_cleanup_storage.py
telegram_cleanup_logging.py
```

For MVP, avoid over-engineering.

Core module responsibilities:

- app directory resolution
- config loading/saving
- Telethon client creation
- login flow
- logout
- list dialogs
- resolve chat
- index messages
- delete pending messages
- retry failed messages
- database operations
- progress calculation
- logging events
- FloodWait handling
- pause/stop handling

GUI module responsibilities:

- Tkinter layout
- user input
- displaying status
- displaying progress
- displaying logs
- starting/stopping worker threads
- reading worker queue
- applying language/theme settings

CLI module responsibilities:

- technical fallback
- development/debugging
- list dialogs
- index
- delete
- retry failed

---

## 10. CLI Requirements

Keep CLI as a fallback mode.

Commands:

```bash
python telegram_cleanup_cli.py list
```

```bash
python telegram_cleanup_cli.py index --chat-id CHAT_ID
```

```bash
python telegram_cleanup_cli.py delete --chat-id CHAT_ID
```

```bash
python telegram_cleanup_cli.py retry-failed --chat-id CHAT_ID
```

Parameters:

- `--chat-id`
- `--batch-size`, default `100`
- `--pause`, default `2`
- `--db-file`, default `telegram_message_cleaner.sqlite3`

CLI must reuse the same core logic as GUI.

CLI must not duplicate business logic.

---

## 11. Packaging Requirements

The Windows app should be buildable as an `.exe`.

Use PyInstaller.

Create:

```text
build_windows_exe.md
```

Required build instructions:

```bash
pip install -r requirements.txt
```

Recommended stable build:

```bash
pyinstaller --onedir --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

Optional single-file build:

```bash
pyinstaller --onefile --windowed --name TelegramMessageCleaner telegram_cleanup_gui.py
```

The first reliable target should be `--onedir`.

Reason:

- easier to keep config, database, session file, and logs near the app
- easier debugging
- fewer issues with temporary PyInstaller folders

The app must store user data next to the executable when frozen.

Implement helper:

```python
def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
```

Data stored next to app:

```text
telegram_message_cleaner_config.json
telegram_message_cleaner.session
telegram_message_cleaner.sqlite3
TelegramMessageCleaner_Logs/
```

Never store persistent user data inside PyInstaller temporary extraction folders.

---

## 12. Requirements.txt

Required dependencies:

```text
telethon
python-dotenv
pyinstaller
```

Do not add standard library modules:

- tkinter
- sqlite3
- asyncio
- threading
- queue
- pathlib
- datetime
- time
- sys
- logging
- argparse
- json

---

## 13. Gitignore Requirements

`.gitignore` must include:

```text
.env
*.session
*.session-journal
*.sqlite3
telegram_message_cleaner_config.json
TelegramMessageCleaner_Logs/
logs/
build/
dist/
*.spec
__pycache__/
.venv/
venv/
```

---

## 14. README Requirements

README must explain:

1. What the app does.
2. What the app does not do.
3. That the app runs locally.
4. That no message content is stored.
5. That deletion is irreversible.
6. That Telegram may refuse or limit some deletion operations.
7. How to get Telegram API ID and API Hash.
8. How to run from Python.
9. How to authorize through GUI.
10. How to list groups.
11. How to enter one Chat ID.
12. How to start cleanup.
13. How indexing works.
14. Why indexing is needed for accurate progress and ETA.
15. How pause/stop/resume works.
16. How retry failed works.
17. How to delete local progress database.
18. How to build Windows `.exe`.
19. Where config/session/database/log files are stored.
20. Why session files must never be shared.
21. How another person can use the app locally with their own Telegram account.
22. That the dark theme is intentionally simple and practical, not a polished visual design feature.

---

## 15. Privacy and Safety

The app must be local-first.

The app must not send user data anywhere except Telegram API calls necessary for the user's own account operations.

The app must not collect analytics.

The app must not phone home.

The app must not have telemetry.

The app must not store message content.

The app must only store minimal metadata required for progress:

- chat ID
- message ID
- message date
- deletion status
- error metadata

The app must not bundle the developer's personal Telegram credentials or session.

---

## 16. Error Handling

Handle at least:

- invalid API ID
- invalid API Hash
- invalid phone
- invalid login code
- 2FA required
- incorrect 2FA password
- unauthorized session
- invalid chat ID
- no access to chat
- chat not found
- no messages found
- FloodWait
- network interruption
- SQLite locked or write error
- failed deletion batch
- user pause
- user stop
- app close during active run

All errors should produce:

- GUI-readable message
- file log entry
- safe recovery path where practical

---

## 17. FloodWait Behavior

When Telegram returns FloodWait:

1. Show phase: `waiting`
2. Show wait duration
3. Show countdown in GUI when practical
4. Log the wait event
5. Sleep for `seconds + 5`
6. Resume automatically

The GUI must remain responsive during waiting.

Pause/stop requests during waiting should be honored as soon as safe.

---

## 18. Open UX Decisions Resolved

### Product audience

Personal use first, trusted sharing second.

### Platform

Windows first. macOS later.

### Auth

GUI-based API ID/API Hash + Telegram login flow.

`.env` may exist for developer fallback, but normal users should not need it.

### Deletion unit

One chat at a time.

### Multiple groups

Not simultaneous.

### Confirmation

User setting.

Default: confirmation enabled.

Power user can disable it.

### Progress

Indexing before deletion for accurate total and ETA.

### Pause/stop

Pause and stop should happen after current batch.

### Failed messages

Track metadata only.

Add retry failed.

### Local database

SQLite file next to app.

No separate SQLite installation required.

### Logs

GUI logs + local rotating logs.

### Theme

Light and dark theme support.

Dark theme is intentionally simple and utilitarian.

The goal is not visual beauty, but basic comfort: dark background, light text, readable controls, and no bright white window when the user prefers a dark environment.

Do not over-engineer theme implementation.

### Language

English and Russian UI support.

Default: English.

### Documentation

PRD lives in:

```text
docs/PRD.md
```

---

## 19. Acceptance Criteria

The app is acceptable when:

1. It launches on Windows as a Python script.
2. It can be packaged into a Windows `.exe`.
3. It allows GUI-based Telegram authentication.
4. It shows the authorized Telegram account.
5. It can list groups and show their IDs.
6. It accepts one `chat_id`.
7. It indexes all messages sent by the authenticated user in that chat.
8. It stores only message metadata, not message content.
9. It deletes text and media messages by message ID.
10. It deletes in batches.
11. It shows progress after indexing.
12. It shows approximate ETA during deletion.
13. It handles FloodWait without freezing the GUI.
14. It can pause after current batch.
15. It can stop after current batch.
16. It can resume after restart.
17. It tracks failed deletions.
18. It can retry failed deletions.
19. It writes safe logs without secrets or message content.
20. It lets the user clear the local progress database.
21. It supports English and Russian UI text.
22. It supports a simple light/dark theme.
23. Its dark theme is readable and not blindingly bright, without requiring advanced styling.
24. It has README and build instructions.
25. It does not implement deletion across all groups.
26. It does not upload data anywhere except normal Telegram API calls.

---

## 20. Implementation Guidance for Codex

Implement the app in a simple, maintainable way.

Avoid unnecessary abstractions.

Prefer clarity over cleverness.

Keep core deletion logic independent from GUI.

Do not put Telegram cleanup logic directly into Tkinter callbacks.

Use a background worker for long-running operations.

Use queue-based GUI updates.

Do not update Tkinter widgets directly from worker threads.

Do not store message text.

Do not print secrets.

Do not add commit or push instructions.

Prioritize a stable Windows version first.

macOS support is a later phase.

Do not over-engineer the GUI.

The interface should be functional, stable, and understandable.

Do not build a complex design system.

Do not spend much effort on making the dark theme beautiful. The dark theme only needs to be dark enough and readable enough so that the app is comfortable to use in a dark environment.

Prioritize:

1. stable Telegram authorization;
2. correct one-chat cleanup behavior;
3. indexing;
4. progress and ETA;
5. pause/stop/resume;
6. safe local storage;
7. useful logs.

UI aesthetics are secondary.

---

## 21. Recommended First Codex Task

Before implementing the full application, Codex should first create the project skeleton and documentation.

Suggested first task:

1. Create `docs/PRD.md` with this PRD.
2. Create the basic project files:
   - `telegram_cleanup_core.py`
   - `telegram_cleanup_gui.py`
   - `telegram_cleanup_cli.py`
   - `README.md`
   - `build_windows_exe.md`
   - `requirements.txt`
   - `.gitignore`
3. Add placeholder module structure without implementing all deletion logic at once.
4. Ensure business logic is planned for `telegram_cleanup_core.py`, not directly inside GUI callbacks.
5. Do not implement commit or push steps.

The next implementation steps should be incremental:

1. local config and app directory handling;
2. Telegram authorization;
3. group listing;
4. SQLite schema and storage layer;
5. indexing;
6. deletion;
7. progress and ETA;
8. pause/stop/resume;
9. failed retry;
10. packaging.
