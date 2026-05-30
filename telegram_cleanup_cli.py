from __future__ import annotations

import argparse
import json
import sys

from telegram_cleanup_core import DB_FILE_NAME, TelegramCleanupCore, create_cli_event_printer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Message Cleaner CLI")
    parser.add_argument("--db-file", default=DB_FILE_NAME, help="SQLite progress database file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List dialogs available to the authorized account")

    index_parser = subparsers.add_parser("index", help="Index one chat")
    index_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")

    delete_parser = subparsers.add_parser("delete", help="Index and delete pending messages")
    delete_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    delete_parser.add_argument("--batch-size", type=int, default=100, help="Delete batch size")
    delete_parser.add_argument("--pause", type=float, default=2.0, help="Pause between batches in seconds")

    retry_parser = subparsers.add_parser("retry-failed", help="Retry failed deletions for one chat")
    retry_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    retry_parser.add_argument("--batch-size", type=int, default=100, help="Delete batch size")
    retry_parser.add_argument("--pause", type=float, default=2.0, help="Pause between batches in seconds")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    core = TelegramCleanupCore(
        event_callback=create_cli_event_printer(),
        db_file_override=args.db_file,
    )

    try:
        if args.command == "list":
            dialogs = core.list_groups()
            print(json.dumps(dialogs, ensure_ascii=False, indent=2))
            return 0

        if args.command == "index":
            result = core.index_messages(args.chat_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "delete":
            result = core.start_cleanup(
                chat_input=args.chat_id,
                batch_size=args.batch_size,
                pause_seconds=args.pause,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "retry-failed":
            result = core.retry_failed(
                chat_input=args.chat_id,
                batch_size=args.batch_size,
                pause_seconds=args.pause,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        parser.error(f"Unknown command: {args.command}")
        return 2
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
