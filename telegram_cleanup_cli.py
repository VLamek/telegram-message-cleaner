from __future__ import annotations

import argparse
import json
import sys

from telegram_cleanup_core import DB_FILE_NAME, TelegramCleanupCore, create_cli_event_printer


def add_date_range_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--from-date",
        default="first",
        help="Start date/time, e.g. '2026-01-01 00:00'. Use 'first' for no lower bound.",
    )
    parser.add_argument(
        "--to-date",
        default="last",
        help="End date/time, e.g. '2026-01-31 23:59'. Use 'last' for no upper bound.",
    )


def add_message_type_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--message-types",
        default="all",
        help=(
            "Comma-separated message types to include, or 'all'. "
            "Supported: text,links,photo,video,gif,voice,video_note,file,sticker,poll,other."
        ),
    )


def add_destructive_confirmation_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm this destructive Telegram deletion command without an interactive prompt.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Message Cleaner CLI")
    parser.add_argument("--db-file", default=DB_FILE_NAME, help="SQLite progress database file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List dialogs available to the authorized account")

    index_parser = subparsers.add_parser("index", help="Index one chat")
    index_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    add_date_range_arguments(index_parser)
    add_message_type_arguments(index_parser)

    delete_parser = subparsers.add_parser("delete", help="Index and delete pending messages")
    delete_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    delete_parser.add_argument("--batch-size", type=int, default=100, help="Delete batch size")
    delete_parser.add_argument("--pause", type=float, default=2.0, help="Pause between batches in seconds")
    add_destructive_confirmation_argument(delete_parser)
    add_date_range_arguments(delete_parser)
    add_message_type_arguments(delete_parser)

    delete_indexed_parser = subparsers.add_parser(
        "delete-indexed",
        help="Delete already indexed pending messages without a new indexing pass",
    )
    delete_indexed_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    delete_indexed_parser.add_argument("--batch-size", type=int, default=100, help="Delete batch size")
    delete_indexed_parser.add_argument("--pause", type=float, default=2.0, help="Pause between batches in seconds")
    add_destructive_confirmation_argument(delete_indexed_parser)
    add_date_range_arguments(delete_indexed_parser)
    add_message_type_arguments(delete_indexed_parser)

    retry_parser = subparsers.add_parser("retry-failed", help="Retry failed deletions for one chat")
    retry_parser.add_argument("--chat-id", required=True, help="Telegram chat ID")
    retry_parser.add_argument("--batch-size", type=int, default=100, help="Delete batch size")
    retry_parser.add_argument("--pause", type=float, default=2.0, help="Pause between batches in seconds")
    add_destructive_confirmation_argument(retry_parser)
    add_date_range_arguments(retry_parser)
    add_message_type_arguments(retry_parser)

    return parser


def confirm_destructive_command(args: argparse.Namespace) -> None:
    if getattr(args, "yes", False):
        return
    command = str(args.command)
    chat_id = str(getattr(args, "chat_id", ""))
    details = (
        f"Command '{command}' will delete Telegram messages for chat '{chat_id}'.\n"
        f"Date range: {getattr(args, 'from_date', 'first')} -> {getattr(args, 'to_date', 'last')}\n"
        f"Message types: {getattr(args, 'message_types', 'all')}\n"
        "Type DELETE to continue: "
    )
    if not sys.stdin.isatty():
        raise RuntimeError(f"Refusing to run destructive '{command}' without --yes in a non-interactive shell.")
    answer = input(details)
    if answer.strip() != "DELETE":
        raise RuntimeError("Deletion cancelled.")


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
            result = core.index_messages(
                args.chat_id,
                date_from=args.from_date,
                date_to=args.to_date,
                message_types=args.message_types,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "delete":
            confirm_destructive_command(args)
            result = core.start_cleanup(
                chat_input=args.chat_id,
                batch_size=args.batch_size,
                pause_seconds=args.pause,
                date_from=args.from_date,
                date_to=args.to_date,
                message_types=args.message_types,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "delete-indexed":
            confirm_destructive_command(args)
            result = core.delete_indexed_only(
                chat_input=args.chat_id,
                batch_size=args.batch_size,
                pause_seconds=args.pause,
                date_from=args.from_date,
                date_to=args.to_date,
                message_types=args.message_types,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "retry-failed":
            confirm_destructive_command(args)
            result = core.retry_failed(
                chat_input=args.chat_id,
                batch_size=args.batch_size,
                pause_seconds=args.pause,
                date_from=args.from_date,
                date_to=args.to_date,
                message_types=args.message_types,
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
