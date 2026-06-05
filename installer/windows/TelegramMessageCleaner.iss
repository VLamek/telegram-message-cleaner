#define AppName "Telegram Message Cleaner"
#define AppPublisher "Telegram Message Cleaner"
#ifndef AppVersion
#define AppVersion "1.0.0"
#endif
#ifndef AppArch
#define AppArch "x64"
#endif
#ifndef SourceDir
#define SourceDir "..\..\dist\TelegramMessageCleaner"
#endif
#ifndef OutputDir
#define OutputDir "..\..\release\windows-installer"
#endif

[Setup]
AppId={{F0835F0C-5408-49E5-97DA-8C3C72D958A8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Telegram Message Cleaner
DefaultGroupName=Telegram Message Cleaner
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=TelegramMessageCleaner-windows-{#AppArch}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
#if AppArch == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x86compatible
#endif
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\TelegramMessageCleaner.exe

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Telegram Message Cleaner"; Filename: "{app}\TelegramMessageCleaner.exe"
Name: "{autodesktop}\Telegram Message Cleaner"; Filename: "{app}\TelegramMessageCleaner.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\TelegramMessageCleaner.exe"; Description: "Launch Telegram Message Cleaner"; Flags: nowait postinstall skipifsilent
