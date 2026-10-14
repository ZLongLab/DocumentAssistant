param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [Parameter(Mandatory=$true)][string]$Compiler,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$outputPath = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$savedEnvironment = @{}
foreach ($key in @('TEMP','TMP','PYINSTALLER_CONFIG_DIR','PYTHONDONTWRITEBYTECODE')) { $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key,'Process') }
try {
    $env:TEMP = Join-Path $outputPath 'tmp'
    $env:TMP = $env:TEMP
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $outputPath 'cache'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
    & $pythonPath -B -m PyInstaller --noconfirm --distpath (Join-Path $outputPath 'dist') --workpath (Join-Path $outputPath 'build') (Join-Path $PSScriptRoot 'DocumentAssistant.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $bundle = Join-Path $outputPath 'dist\DocumentAssistant'
    & $compilerPath "/DBundleDir=$bundle" "/DOutputDirPath=$outputPath" (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed' }
    $zipPath = Join-Path $outputPath 'DocumentAssistant-0.22.0-Windows-x64-Portable.zip'
    Compress-Archive -LiteralPath $bundle -DestinationPath $zipPath -Force
    $artifacts = @((Join-Path $outputPath 'DocumentAssistant-0.22.0-Windows-x64-Setup.exe'), $zipPath)
    $hashes = foreach ($artifact in $artifacts) { '{0}  {1}' -f (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLower(), (Split-Path $artifact -Leaf) }
    [IO.File]::WriteAllLines((Join-Path $outputPath 'SHA256SUMS.txt'), $hashes, [Text.Encoding]::ASCII)
} finally {
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key,$savedEnvironment[$key],'Process') }
}
