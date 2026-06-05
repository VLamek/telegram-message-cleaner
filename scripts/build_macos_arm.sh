#!/usr/bin/env bash
set -euo pipefail

APP_VERSION="${APP_VERSION:-1.0.0}"
PYTHON="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_ROOT="$ROOT/release"
DIST_PATH="$RELEASE_ROOT/macos-arm64"
WORK_PATH="$ROOT/build/macos-arm64"

cd "$ROOT"
mkdir -p "$RELEASE_ROOT"
rm -rf "$DIST_PATH" "$WORK_PATH"

"$PYTHON" -m PyInstaller --clean --noconfirm --windowed \
  --name TelegramMessageCleaner \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  telegram_cleanup_gui.py

APP_PATH="$DIST_PATH/TelegramMessageCleaner.app"
DMG_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64.dmg"
ZIP_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64-app.zip"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Expected app bundle was not created: $APP_PATH" >&2
  exit 1
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP_PATH/Contents/Info.plist"
if /usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$APP_PATH/Contents/Info.plist" >/dev/null 2>&1; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$APP_PATH/Contents/Info.plist"
else
  /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$APP_PATH/Contents/Info.plist"
fi
codesign --force --deep --sign - "$APP_PATH"

rm -f "$DMG_PATH" "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
hdiutil create -volname "Telegram Message Cleaner $APP_VERSION" \
  -srcfolder "$APP_PATH" \
  -ov -format UDZO "$DMG_PATH"

echo "macOS ARM app zip: $ZIP_PATH"
echo "macOS ARM DMG: $DMG_PATH"
