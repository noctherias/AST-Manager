param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AppArguments)
. (Join-Path $PSScriptRoot 'environment.ps1')
& $PythonExe (Join-Path $ProjectRoot 'main.py') @AppArguments
exit $LASTEXITCODE
