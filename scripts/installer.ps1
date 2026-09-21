param([string]$Compiler = '')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
if (-not $Compiler) {
    $candidates = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler)) {
    throw 'Inno Setup 6 fehlt. Von https://jrsoftware.org/isdl.php installieren oder -Compiler C:\Pfad\ISCC.exe angeben.'
}
if (-not (Test-Path -LiteralPath 'dist/AST-Verwaltung/AST-Verwaltung.exe')) { throw 'Zuerst build.bat ausführen.' }
$version = [regex]::Match((Get-Content ast_app/__init__.py -Raw), '"([0-9]+\.[0-9]+\.[0-9]+)"').Groups[1].Value
& $Compiler "/DAppVersion=$version" installer/AST-Manager.iss
if ($LASTEXITCODE -ne 0) { throw 'Setup-Build fehlgeschlagen.' }
Write-Host 'Setup: installer-output\AST-Verwaltung-Setup-x64.exe'
