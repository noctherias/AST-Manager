. (Join-Path $PSScriptRoot 'environment.ps1')
& $PythonExe -m pip install -r (Join-Path $ProjectRoot 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw 'Test-Abhängigkeiten konnten nicht installiert werden.' }
& $PythonExe -m unittest discover -s tests -v
exit $LASTEXITCODE
