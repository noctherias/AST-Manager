$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host 'Python-Umgebung wird eingerichtet ...'
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        & py.exe -3.12 -m venv (Join-Path $ProjectRoot '.venv')
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        & python.exe -m venv (Join-Path $ProjectRoot '.venv')
    } else {
        throw 'Python fehlt. Bitte Python 3.12 (64 Bit) installieren und danach erneut starten.'
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $PythonExe)) { throw 'Python-Umgebung konnte nicht erstellt werden.' }
}
& $PythonExe -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 oder neuer erforderlich"'
if ($LASTEXITCODE -ne 0) { throw 'Python-Version nicht unterstützt.' }
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$RequirementsHash = (Get-FileHash -LiteralPath $RequirementsPath -Algorithm SHA256).Hash
$StampPath = Join-Path $ProjectRoot '.venv\ast-requirements.sha256'
if (-not (Test-Path -LiteralPath $StampPath) -or (Get-Content -LiteralPath $StampPath -Raw).Trim() -ne $RequirementsHash) {
    & $PythonExe -m pip install -r $RequirementsPath
    if ($LASTEXITCODE -ne 0) { throw 'Installation fehlgeschlagen. Bitte Internetverbindung prüfen und erneut starten.' }
    Set-Content -LiteralPath $StampPath -Value $RequirementsHash
}
