#!/usr/bin/env bash
set -euo pipefail

export COPYFILE_DISABLE=1

APP_VERSION="${APP_VERSION:-1.0.0}"
PYTHON="${PYTHON:-python3}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RELEASE_ROOT="$ROOT/release"
DIST_PATH="$RELEASE_ROOT/macos-arm64"
WORK_PATH="$ROOT/build/macos-arm64"
DMG_STAGING="$WORK_PATH/dmg-staging"
DMG_RW_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64.rw.dmg"
DMG_VOLUME_NAME="Telegram Message Cleaner $APP_VERSION"

clean_macos_metadata() {
  local target="$1"
  if [[ -e "$target" ]]; then
    find "$target" \( -name ".DS_Store" -o -name "._*" \) -exec rm -rf {} +
  fi
}

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
CHECKSUM_PATH="$RELEASE_ROOT/TelegramMessageCleaner-macos-arm64-sha256.txt"
DMG_BACKGROUND_NAME="dmg-background.png"

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
clean_macos_metadata "$APP_PATH"
codesign --force --deep --sign - "$APP_PATH"

rm -f "$DMG_PATH" "$ZIP_PATH"
clean_macos_metadata "$APP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

rm -rf "$DMG_STAGING"
mkdir -p "$DMG_STAGING/.background"
ditto "$APP_PATH" "$DMG_STAGING/TelegramMessageCleaner.app"
ln -s /Applications "$DMG_STAGING/Applications"
"$PYTHON" "$ROOT/scripts/create_macos_dmg_background.py" "$DMG_STAGING/.background/$DMG_BACKGROUND_NAME"
clean_macos_metadata "$DMG_STAGING"

rm -f "$DMG_RW_PATH" "$DMG_PATH"
hdiutil create -volname "$DMG_VOLUME_NAME" \
  -srcfolder "$DMG_STAGING" \
  -fs HFS+ \
  -ov -format UDRW "$DMG_RW_PATH"

DMG_DEVICE=""
cleanup_mount() {
  if [[ -n "$DMG_DEVICE" ]]; then
    hdiutil detach "$DMG_DEVICE" >/dev/null 2>&1 || true
  fi
}
trap cleanup_mount EXIT

if [[ -d "/Volumes/$DMG_VOLUME_NAME" ]]; then
  hdiutil detach "/Volumes/$DMG_VOLUME_NAME" >/dev/null 2>&1 || true
fi

ATTACH_OUTPUT="$(hdiutil attach "$DMG_RW_PATH" -readwrite -noverify -noautoopen)"
DMG_DEVICE="$(printf '%s\n' "$ATTACH_OUTPUT" | awk '/Apple_HFS/ { print $1; exit }')"
osascript <<OSA
tell application "Finder"
  tell disk "$DMG_VOLUME_NAME"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {200, 120, 840, 540}
    set theViewOptions to icon view options of container window
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 112
    set backgroundPicture to alias "$DMG_VOLUME_NAME:.background:$DMG_BACKGROUND_NAME"
    set background picture of theViewOptions to backgroundPicture
    set position of item "TelegramMessageCleaner.app" of container window to {170, 210}
    set position of item "Applications" of container window to {470, 210}
    set extension hidden of item "TelegramMessageCleaner.app" to true
    close
  end tell
end tell
OSA
sync
sleep 1
cleanup_mount
trap - EXIT

hdiutil convert "$DMG_RW_PATH" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
rm -f "$DMG_RW_PATH"
shasum -a 256 "$ZIP_PATH" "$DMG_PATH" > "$CHECKSUM_PATH"

echo "macOS ARM app zip: $ZIP_PATH"
echo "macOS ARM DMG: $DMG_PATH"
echo "macOS ARM SHA-256 checksums: $CHECKSUM_PATH"
