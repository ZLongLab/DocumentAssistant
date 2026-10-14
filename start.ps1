param([switch]$Windowed)
$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$runtimeDirectory = Join-Path (Split-Path $projectDirectory -Parent) 'DocumentAssistant-local'
if (-not $env:DOCUMENTASSISTANT_HOME) { $env:DOCUMENTASSISTANT_HOME = $runtimeDirectory }
$temporaryDirectory = Join-Path $env:DOCUMENTASSISTANT_HOME 'tmp'
New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
$env:TEMP = $temporaryDirectory
$env:TMP = $temporaryDirectory
$env:PYTHONUTF8 = '1'
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if ($Windowed) { $pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\pythonw.exe' }
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw '找不到独立虚拟环境，请先运行 setup.ps1。' }
if ($Windowed) {
    Start-Process -FilePath $pythonExecutable -ArgumentList @('-m', 'document_assistant') -WorkingDirectory $projectDirectory -WindowStyle Hidden | Out-Null
    exit 0
}
Push-Location $projectDirectory
try {
    & $pythonExecutable -m document_assistant
    $applicationExitCode = $LASTEXITCODE
}
finally { Pop-Location }
exit $applicationExitCode
