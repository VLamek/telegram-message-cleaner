param(
    [ValidateSet("x64", "x86")]
    [string]$Arch = "x64",
    [string]$AppVersion = "1.0.0",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$releaseRoot = Join-Path $root "release"
$distPath = Join-Path $releaseRoot "windows-$Arch"
$workPath = Join-Path $root "build\windows-$Arch"

Set-Location $root
if (Test-Path -LiteralPath $distPath) {
    Remove-Item -LiteralPath $distPath -Recurse -Force
}
if (Test-Path -LiteralPath $workPath) {
    Remove-Item -LiteralPath $workPath -Recurse -Force
}

& $PythonExe -m PyInstaller --clean --noconfirm --windowed `
    --name TelegramMessageCleaner `
    --distpath $distPath `
    --workpath $workPath `
    (Join-Path $root "telegram_cleanup_gui.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$appDir = Join-Path $distPath "TelegramMessageCleaner"
if (-not (Test-Path -LiteralPath $appDir -PathType Container)) {
    throw "Expected PyInstaller output directory was not created: $appDir"
}

$zipPath = Join-Path $releaseRoot "TelegramMessageCleaner-windows-$Arch-portable.zip"
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Compress-Archive -Path (Join-Path $appDir "*") -DestinationPath $zipPath -Force
        break
    } catch {
        if ($attempt -eq 5) {
            throw
        }
        Start-Sleep -Seconds 2
    }
}

$isccCommand = Get-Command iscc -ErrorAction SilentlyContinue
$isccPath = $null
if ($isccCommand) {
    if ($isccCommand.Source) {
        $isccPath = $isccCommand.Source
    } elseif ($isccCommand.Path) {
        $isccPath = $isccCommand.Path
    } elseif ($isccCommand.Definition) {
        $isccPath = $isccCommand.Definition
    }
}
if (-not $isccPath) {
    $knownIsccPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $knownIsccPaths) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $isccPath = $candidate
            break
        }
    }
}
if ($isccPath) {
    $installerOut = Join-Path $releaseRoot "windows-$Arch-installer"
    $cleanInstallerOut = Join-Path $releaseRoot "installers"
    New-Item -ItemType Directory -Force -Path $installerOut | Out-Null
    New-Item -ItemType Directory -Force -Path $cleanInstallerOut | Out-Null
    & $isccPath `
        "/DAppVersion=$AppVersion" `
        "/DAppArch=$Arch" `
        "/DSourceDir=$appDir" `
        "/DOutputDir=$installerOut" `
        (Join-Path $root "installer\windows\TelegramMessageCleaner.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
    $installerPath = Join-Path $installerOut "TelegramMessageCleaner-windows-$Arch-setup.exe"
    if (Test-Path -LiteralPath $installerPath) {
        Copy-Item -LiteralPath $installerPath -Destination (Join-Path $cleanInstallerOut (Split-Path -Leaf $installerPath)) -Force
    } else {
        throw "Expected installer was not created: $installerPath"
    }
}

Write-Host "Windows $Arch portable package: $zipPath"
if ($isccPath) {
    Write-Host "Windows $Arch installer output: $installerOut"
    Write-Host "Windows $Arch ready-to-run installer: $(Join-Path $releaseRoot "installers\TelegramMessageCleaner-windows-$Arch-setup.exe")"
} else {
    Write-Host "Inno Setup is not installed; skipped installer .exe generation."
}
