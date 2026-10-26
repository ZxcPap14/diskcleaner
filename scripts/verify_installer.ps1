# Проверка собранного установщика на этой машине:
# тихая установка → DiskCleaner.exe --self-test → тихое удаление.
#
#   pwsh -File scripts\verify_installer.ps1 -Setup dist\DiskCleaner-Setup-4.10.3.exe
#   powershell -File scripts\verify_installer.ps1 -Setup ... -KeepInstall
param(
    [Parameter(Mandatory = $true)]
    [string]$Setup,

    [string]$InstallDir = (Join-Path $env:TEMP "DiskCleanerVerify"),

    [switch]$KeepInstall
)

$ErrorActionPreference = "Stop"

function Wait-ProcessOrFail {
    param([System.Diagnostics.Process]$Process, [int]$Seconds, [string]$What)

    if (-not $Process.WaitForExit($Seconds * 1000)) {
        try { $Process.Kill() } catch { }
        throw "$What не завершился за $Seconds с"
    }
}

$setupPath = (Resolve-Path -LiteralPath $Setup).Path
if (Test-Path -LiteralPath $InstallDir) {
    Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

Write-Host "1/4 Установка: $setupPath"
$install = Start-Process -FilePath $setupPath `
    -ArgumentList @("/S", "/D=$InstallDir") -PassThru
Wait-ProcessOrFail -Process $install -Seconds 180 -What "Установщик"
if ($install.ExitCode -ne 0) {
    throw "Установщик вернул код $($install.ExitCode)"
}

$exe = Join-Path $InstallDir "DiskCleaner.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "После установки нет $exe"
}

Write-Host "2/4 Самопроверка: $exe --self-test"
$report = Join-Path $env:TEMP "DiskCleaner-selftest.json"
Remove-Item -LiteralPath $report -ErrorAction SilentlyContinue
$test = Start-Process -FilePath $exe -ArgumentList "--self-test" -PassThru
Wait-ProcessOrFail -Process $test -Seconds 120 -What "Самопроверка"
if ($test.ExitCode -ne 0) {
    throw "Самопроверка вернула код $($test.ExitCode); отчёт: $report"
}
if (-not (Test-Path -LiteralPath $report)) {
    throw "Самопроверка не создала отчёт $report"
}

$payload = [IO.File]::ReadAllText($report, [Text.Encoding]::UTF8) | ConvertFrom-Json
if (-not $payload.ok) {
    $failed = $payload.checks.PSObject.Properties |
        Where-Object { $_.Value.critical -and -not $_.Value.ok } |
        ForEach-Object { "$($_.Name): $($_.Value.detail)" }
    throw "Самопроверка не прошла: $($failed -join '; ')"
}
if (-not $payload.frozen) {
    throw "Запущен не exe-сборка: $($payload.executable)"
}
Write-Host "   версия $($payload.version), Python $($payload.python), Tk OK"

if (-not $KeepInstall) {
    Write-Host "3/4 Удаление"
    $uninstaller = Join-Path $InstallDir "Uninstall.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) {
        throw "Нет деинсталлятора $uninstaller"
    }
    $uninstall = Start-Process -FilePath $uninstaller `
        -ArgumentList "/S" -PassThru
    Wait-ProcessOrFail -Process $uninstall -Seconds 120 -What "Деинсталлятор"
    if ($uninstall.ExitCode -ne 0) {
        throw "Деинсталлятор вернул код $($uninstall.ExitCode)"
    }
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $InstallDir) {
        throw "После удаления осталась папка $InstallDir"
    }
} else {
    Write-Host "3/4 Удаление пропущено (-KeepInstall): $InstallDir"
}

Write-Host "4/4 VERIFY OK: установка, запуск и удаление работают"
