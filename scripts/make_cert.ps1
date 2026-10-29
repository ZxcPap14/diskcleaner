# Самоподписанный сертификат подписи кода для локальных сборок.
#
#   pwsh -File scripts\make_cert.ps1
#   pwsh -File scripts\make_cert.ps1 -Subject "CN=ZCode" -Years 3
#
# Печатает SHA-1 отпечаток для build_installer.py --sign-cert.
# Файлы: certs\diskcleaner.pfx (резервная копия), certs\diskcleaner.cer.
# Сертификат кладётся в Cert:\CurrentUser\My и, если не указан -NoTrust,
# в Root/TrustedPublisher — иначе signtool verify не пройдёт.
# SmartScreen такой подписи всё равно не доверяет: нужен платный
# сертификат с репутацией, это только имя издателя в свойствах файла.
param(
    [string]$Subject = "CN=ZCode, O=ZCode, C=RU",
    [string]$OutDir = (Join-Path $PSScriptRoot "..\certs"),
    [int]$Years = 3,
    [string]$PfxPassword = "diskcleaner",
    [switch]$NoTrust
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$pfxPath = Join-Path $OutDir "diskcleaner.pfx"
$cerPath = Join-Path $OutDir "diskcleaner.cer"

$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyUsage DigitalSignature `
    -KeyExportPolicy Exportable `
    -KeyLength 2048 `
    -KeyAlgorithm RSA `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears($Years) `
    -CertStoreLocation Cert:\CurrentUser\My

# Пароль к PFX задан параметром по умолчанию: ключ локальный и
# самоподписанный, но резервная копия должна переноситься на другую машину.
# shortcut: пароль в скрипте, убрать перед публикацией ключа.
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password (
    ConvertTo-SecureString -String $PfxPassword -AsPlainText -Force
) | Out-Null
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

if (-not $NoTrust) {
    foreach ($store in "Root", "TrustedPublisher") {
        Import-Certificate -FilePath $cerPath `
            -CertStoreLocation "Cert:\CurrentUser\$store" | Out-Null
    }
}

Write-Host "Сертификат: $($cert.Subject)"
Write-Host "Действует до: $($cert.NotAfter.ToString('yyyy-MM-dd'))"
Write-Host "SHA-1: $($cert.Thumbprint)"
Write-Host ""
Write-Host "Подпись сборки:"
Write-Host "  python build_installer.py --web --sign-cert $($cert.Thumbprint)"
