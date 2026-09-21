. (Join-Path $PSScriptRoot 'environment.ps1')
& $PythonExe -m pip install -r (Join-Path $ProjectRoot 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build-Abhängigkeiten konnten nicht installiert werden.' }
& $PythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests fehlgeschlagen; kein Build erstellt.' }
& $PythonExe tools/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Symbol konnte nicht erstellt werden.' }
& $PythonExe -m PyInstaller --noconfirm AST-Verwaltung.spec
if ($LASTEXITCODE -ne 0) { throw 'Build fehlgeschlagen.' }
& $PythonExe tools/collect_licenses.py dist/AST-Verwaltung/_internal/licenses
if ($LASTEXITCODE -ne 0) { throw 'Lizenzhinweise konnten nicht kopiert werden.' }
& $PythonExe tools/package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Pakete konnten nicht erstellt werden.' }
Write-Host 'Fertig: dist\AST-Verwaltung\AST-Verwaltung.exe'
