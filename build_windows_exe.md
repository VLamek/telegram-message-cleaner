# Build Windows Release Artifacts

Windows builds use PyInstaller for the application bundle and Inno Setup for installer `.exe` files.

## Install Dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install Inno Setup if you want a setup executable:

```powershell
choco install innosetup --yes
```

If `iscc` is not available, the build script still creates a portable ZIP.

## Build Windows 64-bit

```powershell
.\scripts\build_windows.ps1 -Arch x64 -AppVersion 1.0.0
```

## Build Windows 32-bit

Use 32-bit Python, then run:

```powershell
.\scripts\build_windows.ps1 -Arch x86 -AppVersion 1.0.0
```

If 32-bit Python is installed side-by-side, pass it explicitly:

```powershell
.\scripts\build_windows.ps1 -Arch x86 -AppVersion 1.0.0 -PythonExe "$env:LOCALAPPDATA\Programs\Python\Python312-32\python.exe"
```

## Outputs

Local output goes to `release/`:

- `TelegramMessageCleaner-windows-x64-portable.zip`
- `TelegramMessageCleaner-windows-x86-portable.zip`
- `windows-x64-installer/TelegramMessageCleaner-windows-x64-setup.exe`
- `windows-x86-installer/TelegramMessageCleaner-windows-x86-setup.exe`

`release/` is ignored by git.

## GitHub Actions

The workflow `.github/workflows/release-artifacts.yml` builds Windows x64, Windows x86, and macOS ARM artifacts. Push a `v*` tag to publish artifacts to GitHub Releases, or run the workflow manually to download artifacts from the workflow run.

## Runtime Files

When the app runs as a frozen executable, local runtime files are stored next to the executable:

- `telegram_message_cleaner_config.json`
- `telegram_message_cleaner.session`
- `telegram_message_cleaner.sqlite3`
- `telegram_message_cleaner_failed.sqlite3`
- `TelegramMessageCleaner_Logs/`

Do not distribute your own session file with a release.
