#!/usr/bin/env bash
set -euo pipefail

APP_VERSION="${APP_VERSION:-1.0.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_ROOT="$ROOT/release"
DIST_PATH="$RELEASE_ROOT/macos-arm64"
WORK_PATH="$ROOT/build/macos-arm64"

cd "$ROOT"
python -m PyInstaller --clean --noconfirm --windowed \
  --name TelegramMessageCleaner \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  telegram_cleanup_gui.py

APP_PATH="$DIST_PATH/TelegramMessageCleaner.app"
DMG_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64.dmg"
ZIP_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64-app.zip"

rm -f "$DMG_PATH" "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
hdiutil create -volname "Telegram Message Cleaner $APP_VERSION" \
  -srcfolder "$APP_PATH" \
  -ov -format UDZO "$DMG_PATH"

echo "macOS ARM app zip: $ZIP_PATH"
echo "macOS ARM DMG: $DMG_PATH"
